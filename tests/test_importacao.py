"""Importação de membros da plataforma (Firebase) — RF-001 / RN-010 / RNF-004."""

from __future__ import annotations

from sqlalchemy import func, select

from oraculo.db.models import Membro, RegistroAuditoria
from oraculo.domain.hierarchy import CAVALARIA, CONSELHEIRO, LORDE, MEMBRO
from oraculo.integrations.plataforma import FonteEmMemoria, normalizar
from oraculo.services.importacao_service import ImportacaoService, PoliticaImportacao

DOCS = [
    {"id": "u1", "nome": "Perseu", "discordId": "1001", "email": "perseu@tyto.example", "xp": 700},
    {"id": "u2", "nome": "Medeia", "discordId": 1002, "cargo": "conselheiro", "xp": 4000},
    {"id": "u3", "nome": "Só na plataforma", "xp": 10},
]


def servico(documentos=DOCS, **kwargs) -> ImportacaoService:
    return ImportacaoService(FonteEmMemoria(documentos), **kwargs)


# --- Normalização -----------------------------------------------------------


def test_normaliza_tipos_tolerantes():
    """A plataforma pode mandar número como string — não pode virar erro."""
    externo = normalizar({"id": "x", "nome": " Perseu ", "discordId": "1001", "xp": "700"})

    assert externo.id_externo == "x"
    assert externo.nome == "Perseu"
    assert externo.discord_id == 1001
    assert externo.xp == 700
    assert externo.ativo is True


def test_mapa_de_campos_configuravel():
    """Nome de campo diferente se resolve por ambiente, sem tocar no código."""
    documento = {"uid": "abc", "displayName": "Atena", "discord": {"id": 55}, "pontos": 900}

    externo = normalizar(
        documento,
        mapa={
            "id_externo": "uid",
            "nome": "displayName",
            "discord_id": "discord.id",
            "xp": "pontos",
        },
    )

    assert (externo.id_externo, externo.nome, externo.discord_id, externo.xp) == (
        "abc",
        "Atena",
        55,
        900,
    )


def test_documento_sem_identidade_e_descartado():
    assert normalizar({"nome": "Fantasma"}) is None


def test_projecao_pede_apenas_os_campos_usados():
    """Documentos do clube trazem foto em base64: nunca baixar o documento todo."""
    from oraculo.config import Settings
    from oraculo.integrations.plataforma import FirestoreMembros

    cfg = Settings(
        _env_file=None,
        firebase_project_id="clube-tyto",
        firebase_campos={"nome": "name", "xp": "pontos"},
    )

    campos = FirestoreMembros(cfg)._campos_necessarios()

    assert "name" in campos and "pontos" in campos
    assert "photoUrl" not in campos, "a foto em base64 não pode entrar na projeção"


def test_foto_em_base64_nao_e_carregada_para_a_memoria():
    """Mesmo se vier no documento, a foto não deve sobreviver à normalização."""
    documento = {
        "id": "u1",
        "name": "Dayvid Santana",
        "photoUrl": "data:image/png;base64," + "A" * 50_000,
    }

    externo = normalizar(documento, mapa={"nome": "name"})

    assert externo.nome == "Dayvid Santana"
    # A chave permanece para diagnóstico, mas sem o conteúdo.
    assert "base64" not in externo.bruto["photoUrl"]
    assert len(str(externo.bruto)) < 500


# --- Importação -------------------------------------------------------------


async def test_primeira_carga_cria_membros(session):
    relatorio = await servico().importar(session)

    assert relatorio.criados == 3
    assert relatorio.atualizados == 0
    assert relatorio.sem_discord == 1
    assert await session.scalar(select(func.count()).select_from(Membro)) == 3


async def test_membro_sem_discord_e_importado_e_contabilizado(session):
    """A plataforma é a fonte do cadastro; o vínculo com o Discord vem depois."""
    await servico().importar(session)

    membro = await session.scalar(select(Membro).where(Membro.id_externo == "u3"))
    assert membro.discord_id is None
    assert membro.nome_exibicao == "Só na plataforma"


async def test_importacao_e_idempotente(session):
    await servico().importar(session)
    relatorio = await servico().importar(session)

    assert relatorio.criados == 0
    assert relatorio.inalterados == 3
    assert await session.scalar(select(func.count()).select_from(Membro)) == 3


async def test_politica_padrao_nao_toca_em_xp_nem_cargo(session):
    """Padrão `cadastro`: a plataforma manda no cadastro, o bot no XP (RN-002)."""
    await servico().importar(session)

    medeia = await session.scalar(select(Membro).where(Membro.id_externo == "u2"))
    assert medeia.xp == 0
    assert medeia.cargo_slug == MEMBRO.slug


async def test_espelho_preserva_membros_ausentes(session):
    """Decisão do clube: quem sumiu da plataforma continua ativo no bot."""
    await servico(politica=PoliticaImportacao.ESPELHO).importar(session)

    await servico([DOCS[0]], politica=PoliticaImportacao.ESPELHO).importar(session)

    medeia = await session.scalar(select(Membro).where(Membro.id_externo == "u2"))
    assert medeia.ativo is True


async def test_carga_inicial_traz_xp_e_cargo_apenas_de_novos(session):
    await servico(politica=PoliticaImportacao.CARGA_INICIAL).importar(session)

    medeia = await session.scalar(select(Membro).where(Membro.id_externo == "u2"))
    assert medeia.xp == 4000
    assert medeia.cargo_slug == CONSELHEIRO.slug

    # Segunda rodada com XP diferente não pode sobrescrever o que o bot registrou.
    novos_docs = [{**DOCS[1], "xp": 99}]
    await servico(novos_docs, politica=PoliticaImportacao.CARGA_INICIAL).importar(session)
    assert medeia.xp == 4000


async def test_espelho_traz_o_xp_da_plataforma(session):
    """Modo escolhido pelo clube: o XP do bot é um reflexo da plataforma."""
    await servico(politica=PoliticaImportacao.ESPELHO).importar(session)

    perseu = await session.scalar(select(Membro).where(Membro.id_externo == "u1"))
    assert perseu.xp == 700

    # A mudança de cargo passa pelo fluxo normal e entra no histórico (RN-003).
    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "promocao.aplicada")
    )
    assert registro is not None


async def test_espelho_atualiza_xp_a_cada_sincronizacao(session):
    await servico(politica=PoliticaImportacao.ESPELHO).importar(session)

    await servico([{**DOCS[0], "xp": 1600}], politica=PoliticaImportacao.ESPELHO).importar(
        session
    )

    perseu = await session.scalar(select(Membro).where(Membro.id_externo == "u1"))
    assert perseu.xp == 1600
    assert perseu.cargo_slug == LORDE.slug, "o cargo acompanha o XP (RN-002)"


async def test_espelho_deriva_cargo_do_xp_quando_a_plataforma_nao_informa(session):
    """Sem campo `cargo` no Firestore, a hierarquia decide — RN-002."""
    documentos = [{"id": "u7", "nome": "Sem cargo", "discordId": 7, "xp": 3600}]

    await servico(documentos, politica=PoliticaImportacao.ESPELHO).importar(session)

    membro = await session.scalar(select(Membro).where(Membro.id_externo == "u7"))
    assert membro.cargo_slug == CONSELHEIRO.slug


async def test_campo_cargo_ausente_nunca_rebaixa(session):
    """A armadilha do espelho: campo faltando não pode zerar a hierarquia."""
    documentos = [{"id": "u8", "nome": "Veterano", "discordId": 8, "xp": 4000}]
    await servico(documentos, politica=PoliticaImportacao.ESPELHO).importar(session)

    membro = await session.scalar(select(Membro).where(Membro.id_externo == "u8"))
    assert membro.cargo_slug == CONSELHEIRO.slug

    # Segunda leitura, ainda sem campo de cargo: o cargo tem de se manter.
    await servico(documentos, politica=PoliticaImportacao.ESPELHO).importar(session)
    assert membro.cargo_slug == CONSELHEIRO.slug


async def test_vincula_membro_ja_existente_pelo_discord_id(session):
    """Quem já usava o bot não vira duplicata ao ser importado."""
    session.add(
        Membro(discord_id=1001, nome_exibicao="Perseu", cargo_slug=CAVALARIA.slug, xp=600)
    )
    await session.flush()

    relatorio = await servico().importar(session)

    assert relatorio.criados == 2
    perseu = await session.scalar(select(Membro).where(Membro.discord_id == 1001))
    assert perseu.id_externo == "u1"
    assert perseu.xp == 600, "o XP acumulado no bot não pode ser perdido"
    assert perseu.cargo_slug == CAVALARIA.slug


async def test_ensaio_nao_grava_nada(session):
    relatorio = await servico().importar(session, dry_run=True)

    assert relatorio.criados == 3
    assert relatorio.dry_run is True
    assert await session.scalar(select(func.count()).select_from(Membro)) == 0


async def test_ausentes_sao_desativados_e_nao_apagados(session):
    """RN-010 — sair da plataforma não apaga histórico."""
    await servico().importar(session)

    relatorio = await servico([DOCS[0]]).importar(session, desativar_ausentes=True)

    assert relatorio.desativados == 2
    assert await session.scalar(select(func.count()).select_from(Membro)) == 3
    inativo = await session.scalar(select(Membro).where(Membro.id_externo == "u2"))
    assert inativo.ativo is False
    assert inativo.desativado_em is not None


async def test_execucao_e_registrada_na_auditoria(session):
    await servico().importar(session)

    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "importacao.executada")
    )
    assert registro is not None
    assert registro.dados["criados"] == 3
    assert registro.dados["politica"] == "cadastro"


async def test_documento_invalido_nao_aborta_a_carga(session):
    documentos = [DOCS[0], {"nome": "sem id"}, DOCS[1]]

    relatorio = await servico(documentos).importar(session)

    assert relatorio.criados == 2
    assert relatorio.invalidos == 1
    assert relatorio.erros == []


async def test_cargo_desconhecido_cai_no_inicial(session):
    documentos = [{"id": "u9", "nome": "Estranho", "discordId": 9, "cargo": "novice", "xp": 10}]

    await servico(documentos, politica=PoliticaImportacao.CARGA_INICIAL).importar(session)

    membro = await session.scalar(select(Membro).where(Membro.id_externo == "u9"))
    assert membro.cargo_slug == MEMBRO.slug


async def test_dados_do_cadastro_sao_atualizados(session):
    await servico().importar(session)

    atualizados = [{**DOCS[0], "nome": "Perseu de Argos", "email": "novo@tyto.example"}]
    relatorio = await servico(atualizados).importar(session)

    assert relatorio.atualizados == 1
    perseu = await session.scalar(select(Membro).where(Membro.id_externo == "u1"))
    assert perseu.nome_exibicao == "Perseu de Argos"
    assert perseu.email == "novo@tyto.example"
    assert perseu.sincronizado_em is not None
