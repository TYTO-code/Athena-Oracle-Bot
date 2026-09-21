"""Comunicados oficiais — RF-015 / RN-018."""

from __future__ import annotations

from datetime import timedelta

import pytest

from oraculo.db.base import agora
from oraculo.db.models import Comunicado, StatusComunicado, TipoMencao
from oraculo.domain.errors import PermissaoNegadaError
from oraculo.domain.hierarchy import CAVALARIA, CONSELHEIRO, LORDE, MEMBRO
from oraculo.repositories import auditoria
from oraculo.repositories import comunicados as repo
from oraculo.services.comunicado_service import (
    MAX_TENTATIVAS,
    RESERVA_MAXIMA,
    CanalNaoConfiguradoError,
    ComunicadoEncerradoError,
    ComunicadoService,
    DataDeComunicadoInvalidaError,
)

CANAL = 999_000_111


class PublicadorFalso:
    """Registra o que seria enviado; pode ser configurado para falhar."""

    def __init__(self, *, erro: Exception | None = None) -> None:
        self.erro = erro
        self.publicados: list[int] = []
        self.proximo_id = 5000

    async def publicar(self, comunicado: Comunicado) -> int:
        if self.erro is not None:
            raise self.erro
        self.publicados.append(comunicado.id)
        self.proximo_id += 1
        return self.proximo_id


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


@pytest.fixture
def servico(publicador: PublicadorFalso) -> ComunicadoService:
    return ComunicadoService(publicador=publicador, atraso_maximo=timedelta(hours=6))


async def _agendar_direto(session, autor, *, quando, mencao=TipoMencao.NENHUMA) -> Comunicado:
    """Cria a linha pelo repositório, sem passar pela validação de data futura."""
    return await repo.criar(
        session,
        titulo="Assembleia",
        corpo="Reunião geral do clube.",
        canal_id=CANAL,
        autor=autor,
        publicar_em=quando,
        mencao=mencao,
    )


# -- Permissões (RN-008) ----------------------------------------------------


async def test_lorde_programa_comunicado(session, criar_membro, servico):
    autor = await criar_membro(LORDE)

    comunicado = await servico.programar(
        session,
        titulo="Assembleia de outubro",
        corpo="Pauta na descrição.",
        canal_id=CANAL,
        autor=autor,
        publicar_em=agora() + timedelta(days=1),
    )

    assert comunicado.status is StatusComunicado.AGENDADO
    assert comunicado.canal_id == CANAL


@pytest.mark.parametrize("cargo", [MEMBRO, CAVALARIA])
async def test_abaixo_de_lorde_nao_publica(session, criar_membro, servico, cargo):
    autor = await criar_membro(cargo)

    with pytest.raises(PermissaoNegadaError):
        await servico.programar(
            session,
            titulo="Aviso",
            corpo="Texto",
            canal_id=CANAL,
            autor=autor,
            publicar_em=agora() + timedelta(days=1),
        )


@pytest.mark.parametrize("mencao", [TipoMencao.AQUI, TipoMencao.TODOS])
async def test_mencionar_o_servidor_exige_conselheiro(session, criar_membro, servico, mencao):
    """Publicar é Lorde+; acordar o servidor inteiro é um degrau acima (RN-018)."""
    lorde = await criar_membro(LORDE)

    with pytest.raises(PermissaoNegadaError):
        await servico.programar(
            session,
            titulo="Urgente",
            corpo="Texto",
            canal_id=CANAL,
            autor=lorde,
            publicar_em=agora() + timedelta(days=1),
            mencao=mencao,
        )

    conselheiro = await criar_membro(CONSELHEIRO)
    comunicado = await servico.programar(
        session,
        titulo="Urgente",
        corpo="Texto",
        canal_id=CANAL,
        autor=conselheiro,
        publicar_em=agora() + timedelta(days=1),
        mencao=mencao,
    )
    assert TipoMencao(comunicado.mencao) is mencao


# -- Validação de entrada ---------------------------------------------------


async def test_recusa_data_no_passado(session, criar_membro, servico):
    autor = await criar_membro(LORDE)

    with pytest.raises(DataDeComunicadoInvalidaError):
        await servico.programar(
            session,
            titulo="Atrasado",
            corpo="Texto",
            canal_id=CANAL,
            autor=autor,
            publicar_em=agora() - timedelta(minutes=1),
        )


async def test_recusa_data_sem_fuso(session, criar_membro, servico):
    from datetime import datetime

    autor = await criar_membro(LORDE)

    with pytest.raises(DataDeComunicadoInvalidaError):
        await servico.programar(
            session,
            titulo="Sem fuso",
            corpo="Texto",
            canal_id=CANAL,
            autor=autor,
            publicar_em=datetime(2030, 1, 1, 12, 0),  # noqa: DTZ001
        )


async def test_sem_canal_no_comando_nem_no_ambiente(session, criar_membro, servico):
    autor = await criar_membro(LORDE)

    with pytest.raises(CanalNaoConfiguradoError):
        await servico.programar(
            session,
            titulo="Aviso",
            corpo="Texto",
            canal_id=None,
            autor=autor,
            publicar_em=agora() + timedelta(days=1),
            canal_padrao=None,
        )


async def test_canal_do_comando_vence_o_padrao(session, criar_membro, servico):
    autor = await criar_membro(LORDE)

    comunicado = await servico.programar(
        session,
        titulo="Aviso",
        corpo="Texto",
        canal_id=CANAL,
        autor=autor,
        publicar_em=agora() + timedelta(days=1),
        canal_padrao=123,
    )

    assert comunicado.canal_id == CANAL


# -- Ciclo de publicação ----------------------------------------------------


async def test_publica_o_vencido_e_deixa_o_futuro(session, criar_membro, servico, publicador):
    autor = await criar_membro(LORDE)
    vencido = await _agendar_direto(session, autor, quando=agora() - timedelta(minutes=1))
    futuro = await _agendar_direto(session, autor, quando=agora() + timedelta(days=2))

    resultado = await servico.publicar_pendentes(session)

    assert resultado.publicados == [vencido.id]
    assert publicador.publicados == [vencido.id]
    assert vencido.status is StatusComunicado.PUBLICADO
    assert vencido.mensagem_id is not None
    assert futuro.status is StatusComunicado.AGENDADO


async def test_nao_republica_no_ciclo_seguinte(session, criar_membro, servico, publicador):
    """A garantia central: um comunicado programado sai uma vez, não a cada minuto."""
    autor = await criar_membro(LORDE)
    await _agendar_direto(session, autor, quando=agora() - timedelta(minutes=1))

    await servico.publicar_pendentes(session)
    segundo = await servico.publicar_pendentes(session)

    assert segundo.publicados == []
    assert len(publicador.publicados) == 1


async def test_sem_publicador_nada_acontece(session, criar_membro):
    """Processo só de API não deve publicar nem marcar nada como perdido."""
    autor = await criar_membro(LORDE)
    pendente = await _agendar_direto(session, autor, quando=agora() - timedelta(minutes=1))

    resultado = await ComunicadoService().publicar_pendentes(session)

    assert not resultado.houve_trabalho
    assert pendente.status is StatusComunicado.AGENDADO


async def test_falha_de_envio_volta_para_a_fila(session, criar_membro):
    autor = await criar_membro(LORDE)
    servico = ComunicadoService(publicador=PublicadorFalso(erro=RuntimeError("canal fora do ar")))
    pendente = await _agendar_direto(session, autor, quando=agora() - timedelta(minutes=1))

    resultado = await servico.publicar_pendentes(session)

    assert resultado.reagendados == [pendente.id]
    assert pendente.status is StatusComunicado.AGENDADO
    assert pendente.tentativas == 1
    assert "canal fora do ar" in pendente.erro


async def test_desiste_depois_do_limite_de_tentativas(session, criar_membro):
    autor = await criar_membro(LORDE)
    servico = ComunicadoService(publicador=PublicadorFalso(erro=RuntimeError("sem permissão")))
    pendente = await _agendar_direto(session, autor, quando=agora() - timedelta(minutes=1))

    for _ in range(MAX_TENTATIVAS):
        await servico.publicar_pendentes(session)

    assert pendente.status is StatusComunicado.FALHOU
    assert pendente.tentativas == MAX_TENTATIVAS


async def test_comunicado_atrasado_demais_nao_vai_ao_ar(session, criar_membro, publicador):
    """Se o bot passou o fim de semana fora, o aviso de sexta não sai na segunda."""
    autor = await criar_membro(LORDE)
    servico = ComunicadoService(publicador=publicador, atraso_maximo=timedelta(hours=6))
    velho = await _agendar_direto(session, autor, quando=agora() - timedelta(days=2))

    resultado = await servico.publicar_pendentes(session)

    assert resultado.expirados == [velho.id]
    assert publicador.publicados == []
    assert velho.status is StatusComunicado.FALHOU
    assert "atraso tolerado" in velho.erro


async def test_reserva_orfa_vira_falha_sem_republicar(session, criar_membro, servico, publicador):
    """Bot reiniciado no meio do envio: a dúvida é resolvida a favor de não
    duplicar o `@everyone`, e a linha fica visível como falha."""
    autor = await criar_membro(LORDE)
    preso = await _agendar_direto(session, autor, quando=agora() - timedelta(hours=1))
    preso.status = StatusComunicado.PUBLICANDO
    preso.reservado_em = agora() - RESERVA_MAXIMA - timedelta(minutes=1)
    await session.flush()

    resultado = await servico.publicar_pendentes(session)

    assert resultado.orfaos == [preso.id]
    assert preso.status is StatusComunicado.FALHOU
    assert publicador.publicados == []


async def test_reserva_recente_e_deixada_em_paz(session, criar_membro, servico):
    """Reserva de segundos atrás é o ciclo normal em andamento, não um órfão."""
    autor = await criar_membro(LORDE)
    emandamento = await _agendar_direto(session, autor, quando=agora() - timedelta(minutes=1))
    emandamento.status = StatusComunicado.PUBLICANDO
    emandamento.reservado_em = agora()
    await session.flush()

    resultado = await servico.publicar_pendentes(session)

    assert resultado.orfaos == []
    assert emandamento.status is StatusComunicado.PUBLICANDO


async def test_publicar_agora_sai_na_hora(session, criar_membro, servico, publicador):
    autor = await criar_membro(LORDE)

    comunicado = await servico.publicar_agora(
        session,
        titulo="Agora",
        corpo="Texto",
        canal_id=CANAL,
        autor=autor,
    )

    assert comunicado.status is StatusComunicado.PUBLICADO
    assert publicador.publicados == [comunicado.id]


async def test_publicar_agora_respeita_a_regra_de_mencao(session, criar_membro, servico):
    lorde = await criar_membro(LORDE)

    with pytest.raises(PermissaoNegadaError):
        await servico.publicar_agora(
            session,
            titulo="Agora",
            corpo="Texto",
            canal_id=CANAL,
            autor=lorde,
            mencao=TipoMencao.TODOS,
        )


# -- Cancelamento (RN-010) --------------------------------------------------


async def test_autor_cancela_o_proprio_comunicado(session, criar_membro, servico):
    autor = await criar_membro(LORDE)
    comunicado = await _agendar_direto(session, autor, quando=agora() + timedelta(days=1))

    await servico.cancelar(
        session, comunicado=comunicado, solicitante=autor, motivo="Adiado pelo Conselho"
    )

    assert comunicado.status is StatusComunicado.CANCELADO
    assert comunicado.motivo_cancelamento == "Adiado pelo Conselho"
    assert comunicado.cancelado_por_id == autor.id


async def test_terceiro_sem_cargo_nao_cancela(session, criar_membro, servico):
    autor = await criar_membro(LORDE)
    intruso = await criar_membro(CAVALARIA)
    comunicado = await _agendar_direto(session, autor, quando=agora() + timedelta(days=1))

    with pytest.raises(PermissaoNegadaError):
        await servico.cancelar(
            session, comunicado=comunicado, solicitante=intruso, motivo="Não quero"
        )
    assert comunicado.status is StatusComunicado.AGENDADO


async def test_cancelado_nao_e_apagado(session, criar_membro, servico):
    """RN-010 — a linha continua no banco, com o motivo."""
    autor = await criar_membro(LORDE)
    comunicado = await _agendar_direto(session, autor, quando=agora() + timedelta(days=1))

    await servico.cancelar(session, comunicado=comunicado, solicitante=autor, motivo="Erro meu")

    assert await repo.obter(session, comunicado.id) is comunicado


async def test_nao_cancela_o_que_ja_foi_publicado(session, criar_membro, servico):
    autor = await criar_membro(LORDE)
    comunicado = await _agendar_direto(session, autor, quando=agora() - timedelta(minutes=1))
    await servico.publicar_pendentes(session)

    with pytest.raises(ComunicadoEncerradoError):
        await servico.cancelar(
            session, comunicado=comunicado, solicitante=autor, motivo="Tarde demais"
        )


async def test_cancelado_nao_e_publicado_depois(session, criar_membro, servico, publicador):
    autor = await criar_membro(LORDE)
    comunicado = await _agendar_direto(session, autor, quando=agora() + timedelta(seconds=1))
    await servico.cancelar(session, comunicado=comunicado, solicitante=autor, motivo="Desmarcado")

    await servico.publicar_pendentes(session, momento=agora() + timedelta(minutes=5))

    assert publicador.publicados == []
    assert comunicado.status is StatusComunicado.CANCELADO


# -- Auditoria (RF-012) -----------------------------------------------------


async def test_trilha_de_auditoria_do_ciclo_completo(session, criar_membro, servico):
    autor = await criar_membro(LORDE)
    await servico.programar(
        session,
        titulo="Assembleia",
        corpo="Texto",
        canal_id=CANAL,
        autor=autor,
        publicar_em=agora() + timedelta(seconds=2),
    )
    await servico.publicar_pendentes(session, momento=agora() + timedelta(minutes=1))

    acoes = {registro.acao for registro in await auditoria.listar(session, limite=20)}
    assert {"comunicado.programado", "comunicado.publicado"} <= acoes


# -- Listagem ---------------------------------------------------------------


async def test_listagem_mostra_tambem_os_que_falharam(session, criar_membro, servico):
    autor = await criar_membro(LORDE)
    await _agendar_direto(session, autor, quando=agora() - timedelta(days=3))
    await servico.publicar_pendentes(session)

    falhados = await repo.listar(session, status=StatusComunicado.FALHOU)

    assert len(falhados) == 1
