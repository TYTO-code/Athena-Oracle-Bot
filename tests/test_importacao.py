"""Espelho dos membros da TYTO.club — RF-001 / RN-010 / RN-020 / RN-021."""

from __future__ import annotations

from sqlalchemy import func, select

from oraculo.db.models import Membro, MovimentacaoXp, RegistroAuditoria
from oraculo.domain.hierarchy import ARMEIRO, OFICIAL, VETERANO
from oraculo.integrations.plataforma import FonteEmMemoria, normalizar
from oraculo.services.importacao_service import ImportacaoService

DOCS = [
    {"id": "u1", "name": "Perseu", "discordId": "1001", "email": "perseu@tyto.example", "xp": 700},
    {"id": "u2", "name": "Medeia", "discordId": 1002, "tier": "Centurião", "xp": 4000},
    {"id": "u3", "name": "Sem Discord", "xp": 10},
]


def servico(documentos=DOCS, **kwargs) -> ImportacaoService:
    return ImportacaoService(FonteEmMemoria(documentos), **kwargs)


# --- Normalização -----------------------------------------------------------


def test_normaliza_tipos_tolerantes():
    """A plataforma pode mandar número como string — não pode virar erro."""
    externo = normalizar({"id": "x", "name": " Perseu ", "discordId": "1001", "xp": "700"})

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


def test_patente_vem_do_campo_tier_da_plataforma():
    externo = normalizar({"id": "x", "tier": "Centurião"})
    assert externo.patente == "Centurião"


def test_chave_legada_cargo_continua_aceita_no_mapa():
    """Configurações anteriores a TD-007 mapeavam `cargo`; vira sinônimo de `patente`."""
    externo = normalizar({"id": "x", "posto": "Oficial"}, mapa={"cargo": "posto"})
    assert externo.patente == "Oficial"


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
        "name": "Maria Souza",
        "photoUrl": "data:image/png;base64," + "A" * 50_000,
    }

    externo = normalizar(documento, mapa={"nome": "name"})

    assert externo.nome == "Maria Souza"
    # A chave permanece para diagnóstico, mas sem o conteúdo.
    assert "base64" not in externo.bruto["photoUrl"]
    assert len(str(externo.bruto)) < 500


def test_campos_padrao_sao_os_da_colecao_users_da_plataforma():
    externo = normalizar(
        {
            "id": "uid1",
            "name": "Atena",
            "discordId": "55",
            "tier": "Oficial",
            "suspended": True,
            "accountType": "merchant",
            "conselheiro": True,
            "admin": True,
        }
    )

    assert (externo.nome, externo.discord_id, externo.patente) == ("Atena", 55, "Oficial")
    assert externo.suspenso is True
    assert externo.tipo_conta == "merchant"
    assert externo.conselheiro is True
    assert externo.administrador is True


def test_elegibilidade_exige_conta_de_clube_ativa_e_discord():
    """RN-020 — suspensa, mercador, desativada ou sem Discord: sem acesso."""
    base = {"id": "x", "name": "N", "discordId": "9"}

    assert normalizar(base).elegivel is True
    assert normalizar({**base, "suspended": True}).elegivel is False
    assert normalizar({**base, "accountType": "merchant"}).elegivel is False
    assert normalizar({**base, "ativo": False}).elegivel is False
    assert normalizar({"id": "x", "name": "N"}).elegivel is False
    assert normalizar({**base, "discordId": "não-é-número"}).elegivel is False



# --- Importação -------------------------------------------------------------


async def test_primeira_carga_cria_so_membros_elegiveis(session):
    relatorio = await servico().importar(session)

    assert relatorio.criados == 2
    assert relatorio.nao_elegiveis == 1, "sem Discord informado: fora do bot (RN-020)"
    assert relatorio.sem_discord == 1
    assert await session.scalar(select(func.count()).select_from(Membro)) == 2
    assert await session.scalar(select(Membro).where(Membro.id_externo == "u3")) is None


async def test_conta_suspensa_ou_de_mercador_nao_entra(session):
    documentos = [
        {"id": "s1", "name": "Suspenso", "discordId": 21, "suspended": True},
        {"id": "m1", "name": "Mercador", "discordId": 22, "accountType": "merchant"},
        {"id": "ok", "name": "Membro", "discordId": 23},
    ]

    relatorio = await servico(documentos).importar(session)

    assert relatorio.criados == 1
    assert relatorio.nao_elegiveis == 2


async def test_importacao_e_idempotente(session):
    await servico().importar(session)
    relatorio = await servico().importar(session)

    assert relatorio.criados == 0
    assert relatorio.inalterados == 2
    assert await session.scalar(select(func.count()).select_from(Membro)) == 2


async def test_traz_xp_e_patente_da_plataforma(session):
    await servico().importar(session)

    perseu = await session.scalar(select(Membro).where(Membro.id_externo == "u1"))
    assert perseu.xp == 700
    assert perseu.patente_slug == ARMEIRO.slug

    # A mudança de patente passa pelo fluxo normal e entra no histórico (RN-003).
    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "promocao.aplicada")
    )
    assert registro is not None


async def test_patente_declarada_alta_e_aplicada_sem_confirmacao_manual(session):
    """Não há `/confirmar-patente`: o bot só espelha (RN-021)."""
    await servico().importar(session)

    medeia = await session.scalar(select(Membro).where(Membro.id_externo == "u2"))
    assert medeia.xp == 4000
    assert medeia.patente_slug == "centuriao"


async def test_sobe_xp_a_cada_sincronizacao_e_registra_na_trilha(session):
    await servico().importar(session)

    await servico([{**DOCS[0], "xp": 2_000}]).importar(session)

    perseu = await session.scalar(select(Membro).where(Membro.id_externo == "u1"))
    assert perseu.xp == 2_000
    assert perseu.patente_slug == VETERANO.slug, "a patente acompanha o XP (RN-002)"
    movimentacao = await session.scalar(
        select(MovimentacaoXp).where(MovimentacaoXp.membro_id == perseu.id)
    )
    assert movimentacao.quantidade == 1_300, "só a subida entra; a carga inicial não é 'da semana'"


async def test_nunca_diminui_xp(session):
    """XP é irrevogável (XP.md Art. 1º §1º): XP menor na plataforma vai para a auditoria."""
    await servico([{**DOCS[0], "xp": 2_000}]).importar(session)
    await servico([{**DOCS[0], "xp": 50}]).importar(session)

    perseu = await session.scalar(select(Membro).where(Membro.id_externo == "u1"))
    assert perseu.xp == 2_000
    assert perseu.patente_slug == VETERANO.slug
    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "importacao.xp_menor_ignorado")
    )
    assert registro.dados == {"xp_bot": 2_000, "xp_plataforma": 50}


async def test_deriva_patente_do_xp_quando_a_plataforma_nao_informa(session):
    documentos = [{"id": "u7", "name": "Sem tier", "discordId": 7, "xp": 2_000}]

    await servico(documentos).importar(session)

    membro = await session.scalar(select(Membro).where(Membro.id_externo == "u7"))
    assert membro.patente_slug == VETERANO.slug


async def test_patente_ausente_ou_menor_nunca_rebaixa(session):
    """XP.md Art. 1º §3º — nem campo faltando nem patente menor rebaixam ninguém."""
    # 106.000 XP ficou abaixo do novo limiar de Oficial (106.496, escala 4×): a patente já alcançada
    # é irrevogável (XP.md Art. 1º §3º), então a importação não pode rebaixar nem reter a patente.
    session.add(
        Membro(
            discord_id=8,
            id_externo="u8",
            nome_exibicao="Veterana",
            patente_slug=OFICIAL.slug,
            xp=106_000,
        )
    )
    await session.flush()

    for documento in (
        {"id": "u8", "name": "Veterana", "discordId": 8, "xp": 106_000},
        {"id": "u8", "name": "Veterana", "discordId": 8, "tier": "Neófito", "xp": 106_000},
    ):
        await servico([documento]).importar(session)
        membro = await session.scalar(select(Membro).where(Membro.discord_id == 8))
        assert membro.patente_slug == OFICIAL.slug


async def test_cargos_institucionais_sao_espelhados_da_plataforma(session):
    """O bot não concede cargo (RN-021): Conselheiro/Administrador vêm da TYTO.club."""
    documentos = [
        {"id": "u14", "name": "Conselheira", "discordId": 14, "conselheiro": True, "admin": True}
    ]

    await servico(documentos).importar(session)

    membro = await session.scalar(select(Membro).where(Membro.id_externo == "u14"))
    assert membro.conselheiro is True
    assert membro.administrador is True

    # E revogados lá, são revogados aqui, com auditoria.
    await servico([{**documentos[0], "conselheiro": False, "admin": False}]).importar(session)
    assert membro.conselheiro is False
    assert membro.administrador is False
    registros = await session.scalar(
        select(func.count())
        .select_from(RegistroAuditoria)
        .where(RegistroAuditoria.acao == "importacao.cargo_espelhado")
    )
    assert registros == 1


async def test_quem_perde_a_elegibilidade_e_desativado(session):
    """RN-020 — suspenso na plataforma, suspenso no bot (soft-delete, RN-010)."""
    await servico().importar(session)

    relatorio = await servico([{**DOCS[0], "suspended": True}]).importar(session)

    perseu = await session.scalar(select(Membro).where(Membro.id_externo == "u1"))
    assert perseu.ativo is False
    assert perseu.desativado_em is not None
    assert relatorio.desativados == 1


async def test_volta_a_ser_elegivel_reativa(session):
    await servico().importar(session)
    await servico([{**DOCS[0], "suspended": True}]).importar(session)

    relatorio = await servico([DOCS[0]]).importar(session)

    perseu = await session.scalar(select(Membro).where(Membro.id_externo == "u1"))
    assert perseu.ativo is True
    assert perseu.desativado_em is None
    assert relatorio.reativados == 1


async def test_vincula_membro_ja_existente_pelo_discord_id(session):
    """Quem já estava no banco do bot não vira duplicata ao ser importado."""
    session.add(
        Membro(discord_id=1001, nome_exibicao="Perseu", patente_slug=VETERANO.slug, xp=2_000)
    )
    await session.flush()

    relatorio = await servico().importar(session)

    assert relatorio.criados == 1
    perseu = await session.scalar(select(Membro).where(Membro.discord_id == 1001))
    assert perseu.id_externo == "u1"
    assert perseu.xp == 2_000, "o XP já registrado não pode ser perdido"
    assert perseu.patente_slug == VETERANO.slug


async def test_ensaio_nao_grava_nada(session):
    relatorio = await servico().importar(session, dry_run=True)

    assert relatorio.criados == 2
    assert relatorio.dry_run is True
    assert await session.scalar(select(func.count()).select_from(Membro)) == 0


async def test_ausentes_sao_desativados_e_nao_apagados(session):
    """RN-010 / RN-020 — sair da plataforma tira o acesso, mas não apaga histórico."""
    await servico().importar(session)

    relatorio = await servico([DOCS[0]]).importar(session, desativar_ausentes=True)

    assert relatorio.desativados == 1
    assert await session.scalar(select(func.count()).select_from(Membro)) == 2
    inativo = await session.scalar(select(Membro).where(Membro.id_externo == "u2"))
    assert inativo.ativo is False
    assert inativo.desativado_em is not None


async def test_leitura_vazia_nao_desativa_ninguem(session):
    """Fonte que devolve zero documentos é falha de leitura, não um Clube vazio."""
    await servico().importar(session)

    relatorio = await servico([]).importar(session, desativar_ausentes=True)

    assert relatorio.desativados == 0
    assert await session.scalar(select(func.count()).select_from(Membro).where(Membro.ativo)) == 2


async def test_execucao_e_registrada_na_auditoria(session):
    await servico().importar(session)

    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "importacao.executada")
    )
    assert registro is not None
    assert registro.dados["criados"] == 2
    assert registro.dados["nao_elegiveis"] == 1


async def test_documento_invalido_nao_aborta_a_carga(session):
    documentos = [DOCS[0], {"name": "sem id"}, DOCS[1]]

    relatorio = await servico(documentos).importar(session)

    assert relatorio.criados == 2
    assert relatorio.invalidos == 1
    assert relatorio.erros == []


async def test_patente_desconhecida_deixa_o_xp_decidir(session):
    """Inclusive nomes da hierarquia anterior a TD-007, como "cavalaria"."""
    documentos = [{"id": "u9", "name": "Estranho", "discordId": 9, "tier": "cavalaria", "xp": 500}]

    await servico(documentos).importar(session)

    membro = await session.scalar(select(Membro).where(Membro.id_externo == "u9"))
    assert membro.patente_slug == ARMEIRO.slug


async def test_dados_do_cadastro_sao_atualizados(session):
    await servico().importar(session)

    atualizados = [{**DOCS[0], "name": "Perseu de Argos", "email": "novo@tyto.example"}]
    relatorio = await servico(atualizados).importar(session)

    assert relatorio.atualizados == 1
    perseu = await session.scalar(select(Membro).where(Membro.id_externo == "u1"))
    assert perseu.nome_exibicao == "Perseu de Argos"
    assert perseu.email == "novo@tyto.example"
    assert perseu.sincronizado_em is not None


async def test_importar_um_espelha_so_elegivel(session):
    externo_ok = normalizar(DOCS[0])
    externo_fora = normalizar({**DOCS[1], "suspended": True})

    membro = await servico().importar_um(session, externo_ok)
    assert membro is not None and membro.id_externo == "u1"

    assert await servico().importar_um(session, externo_fora) is None
    assert await session.scalar(select(Membro).where(Membro.id_externo == "u2")) is None


async def test_discord_id_de_outra_conta_nao_herda_xp_nem_cargos(session):
    """Quem preenche o `discordId` de outra pessoa não vira essa pessoa (RN-020)."""
    dona = {"id": "a", "name": "Dona", "discordId": "500", "xp": 5_000, "conselheiro": True}
    impostor = {"id": "b", "name": "Impostor", "discordId": "500"}
    await servico([dona]).importar(session)

    relatorio = await servico([impostor]).importar(session)

    original = await session.scalar(select(Membro).where(Membro.id_externo == "a"))
    assert original.xp == 5_000 and original.nome_exibicao == "Dona"
    assert await session.scalar(select(Membro).where(Membro.id_externo == "b")) is None
    assert len(relatorio.erros) == 1, "o conflito é relatado, e a carga continua"


async def test_conflito_de_discord_nao_derruba_o_resto_da_carga(session):
    documentos = [
        {"id": "a", "name": "A", "discordId": "600"},
        {"id": "b", "name": "B", "discordId": "600"},
        {"id": "c", "name": "C", "discordId": "601"},
    ]

    relatorio = await servico(documentos).importar(session)

    assert relatorio.criados == 2
    assert len(relatorio.erros) == 1
    assert await session.scalar(select(Membro).where(Membro.id_externo == "c")) is not None


async def test_importar_um_recusa_discord_de_outra_conta(session):
    await servico([{"id": "a", "name": "A", "discordId": "700"}]).importar(session)

    outro = normalizar({"id": "b", "name": "B", "discordId": "700"})
    assert await servico().importar_um(session, outro) is None


async def test_desativacao_e_reativacao_ficam_na_auditoria(session):
    await servico().importar(session)
    await servico([{**DOCS[0], "suspended": True}]).importar(session)
    await servico([DOCS[0]]).importar(session)

    acoes = set(
        await session.scalars(
            select(RegistroAuditoria.acao).where(RegistroAuditoria.acao.like("importacao.membro_%"))
        )
    )
    assert acoes == {"importacao.membro_desativado", "importacao.membro_reativado"}


async def test_leitura_parcial_suspeita_nao_desativa_em_massa(session):
    """Coleção errada ou leitura cortada: sumir quase todo mundo não é "saíram do Clube"."""
    todos = [{"id": f"m{i}", "name": f"M{i}", "discordId": str(800 + i)} for i in range(12)]
    await servico(todos).importar(session)

    relatorio = await servico(todos[:2]).importar(session, desativar_ausentes=True)

    assert relatorio.desativados == 0
    assert any("suspeito" in e for e in relatorio.erros)
    ativos = await session.scalar(select(func.count()).select_from(Membro).where(Membro.ativo))
    assert ativos == 12
