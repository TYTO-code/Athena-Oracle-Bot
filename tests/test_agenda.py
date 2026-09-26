"""Reuniões, eventos e RSVP — UC-004, UC-005, UC-006 / RN-006, RN-007, RN-009, RN-010."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from oraculo.db.base import agora
from oraculo.db.models import (
    Agendamento,
    StatusAgendamento,
    StatusPresenca,
    TipoAgendamento,
)
from oraculo.domain.errors import PermissaoNegadaError
from oraculo.domain.hierarchy import NEOFITO, OFICIAL, VETERANO
from oraculo.integrations.google_calendar import EventoExterno
from oraculo.services.agenda_service import (
    AgendamentoEncerradoError,
    AgendaService,
    DataInvalidaError,
)


class AgendaExternaFalsa:
    """Dublê do Google Agenda — RN-009 sem depender de credenciais."""

    def __init__(self, falhar: bool = False) -> None:
        self.criados: list[EventoExterno] = []
        self.cancelados: list[str] = []
        self.falhar = falhar

    async def criar(self, evento: EventoExterno) -> str | None:
        if self.falhar:
            raise RuntimeError("Google indisponível")
        self.criados.append(evento)
        return f"gcal-{len(self.criados)}"

    async def atualizar(self, evento_id: str, evento: EventoExterno) -> None:
        pass

    async def cancelar(self, evento_id: str) -> None:
        self.cancelados.append(evento_id)


@pytest.fixture
def externa() -> AgendaExternaFalsa:
    return AgendaExternaFalsa()


@pytest.fixture
def servico(externa: AgendaExternaFalsa) -> AgendaService:
    return AgendaService(agenda_externa=externa)


@pytest.fixture
def amanha():
    return agora() + timedelta(days=1)


async def test_veterano_cria_reuniao_e_sincroniza_agenda(
    session, criar_membro, servico, externa, amanha
):
    """UC-004 / RN-006 / RN-009."""
    organizador = await criar_membro(VETERANO, nome="Sir Tyto")

    resultado = await servico.criar(
        session,
        tipo=TipoAgendamento.REUNIAO,
        titulo="Assembleia mensal",
        inicio_em=amanha,
        organizador=organizador,
        fim_em=amanha + timedelta(hours=1),
        guild_id=7,
    )

    assert resultado.sincronizado_google is True
    assert resultado.agendamento.google_event_id == "gcal-1"
    assert externa.criados[0].titulo == "Assembleia mensal"
    assert organizador.email in externa.criados[0].convidados_email
    # O organizador entra confirmado (UC-006).
    assert resultado.convidados[0].status is StatusPresenca.CONFIRMADO


async def test_membro_comum_nao_cria_reuniao(session, criar_membro, servico, amanha):
    """RN-006 — abaixo de Veterano a criação é bloqueada e nada é gravado."""
    organizador = await criar_membro(NEOFITO)

    with pytest.raises(PermissaoNegadaError):
        await servico.criar(
            session,
            tipo=TipoAgendamento.REUNIAO,
            titulo="Reunião não autorizada",
            inicio_em=amanha,
            organizador=organizador,
        )

    assert await session.scalar(select(func.count()).select_from(Agendamento)) == 0


async def test_veterano_nao_cria_evento_oficial(session, criar_membro, servico, amanha):
    """RN-007 — evento oficial exige Oficial+."""
    organizador = await criar_membro(VETERANO)

    with pytest.raises(PermissaoNegadaError):
        await servico.criar(
            session,
            tipo=TipoAgendamento.EVENTO,
            titulo="Torneio oficial",
            inicio_em=amanha,
            organizador=organizador,
        )


async def test_oficial_cria_evento_oficial(session, criar_membro, servico, amanha):
    organizador = await criar_membro(OFICIAL)

    resultado = await servico.criar(
        session,
        tipo=TipoAgendamento.EVENTO,
        titulo="Torneio oficial",
        inicio_em=amanha,
        organizador=organizador,
    )

    assert resultado.agendamento.tipo is TipoAgendamento.EVENTO


async def test_data_no_passado_e_rejeitada(session, criar_membro, servico):
    organizador = await criar_membro(VETERANO)

    with pytest.raises(DataInvalidaError):
        await servico.criar(
            session,
            tipo=TipoAgendamento.REUNIAO,
            titulo="Reunião retroativa",
            inicio_em=agora() - timedelta(hours=1),
            organizador=organizador,
        )


async def test_falha_no_google_nao_impede_o_registro(session, criar_membro, amanha):
    """RN-009 degrada com aviso: a reunião local continua válida."""
    servico = AgendaService(agenda_externa=AgendaExternaFalsa(falhar=True))
    organizador = await criar_membro(VETERANO)

    resultado = await servico.criar(
        session,
        tipo=TipoAgendamento.REUNIAO,
        titulo="Reunião sem agenda externa",
        inicio_em=amanha,
        organizador=organizador,
    )

    assert resultado.sincronizado_google is False
    assert "Google indisponível" in resultado.erro_google
    assert resultado.agendamento.id is not None


async def test_cancelamento_e_logico(session, criar_membro, servico, externa, amanha):
    """RN-010 — a linha permanece no banco com motivo e autor do cancelamento."""
    organizador = await criar_membro(VETERANO)
    criado = await servico.criar(
        session,
        tipo=TipoAgendamento.REUNIAO,
        titulo="Reunião cancelada",
        inicio_em=amanha,
        organizador=organizador,
    )

    await servico.cancelar(
        session,
        agendamento=criado.agendamento,
        solicitante=organizador,
        motivo="Conflito de agenda",
    )

    assert await session.scalar(select(func.count()).select_from(Agendamento)) == 1
    assert criado.agendamento.status is StatusAgendamento.CANCELADO
    assert criado.agendamento.motivo_cancelamento == "Conflito de agenda"
    assert criado.agendamento.cancelado_por_id == organizador.id
    assert externa.cancelados == ["gcal-1"]


async def test_membro_comum_nao_cancela_reuniao_de_outro(
    session, criar_membro, servico, amanha
):
    organizador = await criar_membro(VETERANO)
    intruso = await criar_membro(NEOFITO)
    criado = await servico.criar(
        session,
        tipo=TipoAgendamento.REUNIAO,
        titulo="Reunião protegida",
        inicio_em=amanha,
        organizador=organizador,
    )

    with pytest.raises(PermissaoNegadaError):
        await servico.cancelar(
            session, agendamento=criado.agendamento, solicitante=intruso, motivo="Quero cancelar"
        )

    assert criado.agendamento.status is StatusAgendamento.AGENDADO


async def test_rsvp_registra_e_contabiliza(session, criar_membro, servico, amanha):
    """UC-006 — confirmar, recusar e voltar a pendente."""
    organizador = await criar_membro(VETERANO)
    convidado = await criar_membro(NEOFITO)
    criado = await servico.criar(
        session,
        tipo=TipoAgendamento.REUNIAO,
        titulo="Reunião com RSVP",
        inicio_em=amanha,
        organizador=organizador,
        convidados=[convidado],
    )

    presenca = await servico.responder_rsvp(
        session,
        agendamento=criado.agendamento,
        membro=convidado,
        status=StatusPresenca.CONFIRMADO,
    )
    assert presenca.status is StatusPresenca.CONFIRMADO
    assert presenca.respondido_em is not None

    resumo = await servico.resumo_presencas(session, criado.agendamento.id)
    assert resumo == {"confirmado": 2, "recusado": 0, "pendente": 0}

    await servico.responder_rsvp(
        session,
        agendamento=criado.agendamento,
        membro=convidado,
        status=StatusPresenca.RECUSADO,
    )
    resumo = await servico.resumo_presencas(session, criado.agendamento.id)
    assert resumo == {"confirmado": 1, "recusado": 1, "pendente": 0}


async def test_rsvp_em_agendamento_cancelado_e_bloqueado(
    session, criar_membro, servico, amanha
):
    organizador = await criar_membro(VETERANO)
    convidado = await criar_membro(NEOFITO)
    criado = await servico.criar(
        session,
        tipo=TipoAgendamento.REUNIAO,
        titulo="Reunião encerrada",
        inicio_em=amanha,
        organizador=organizador,
    )
    await servico.cancelar(
        session, agendamento=criado.agendamento, solicitante=organizador, motivo="Adiada"
    )

    with pytest.raises(AgendamentoEncerradoError):
        await servico.responder_rsvp(
            session,
            agendamento=criado.agendamento,
            membro=convidado,
            status=StatusPresenca.CONFIRMADO,
        )
