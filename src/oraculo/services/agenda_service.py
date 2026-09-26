"""Reuniões, eventos oficiais e RSVP — UC-004, UC-005, UC-006.

Permissões (RN-006 / RN-007) são resolvidas pela política central em
`domain.permissions`: reunião exige a patente Veterano+, evento oficial exige
Oficial+ (TD-007).

Cancelamento é sempre lógico (RN-010): a linha permanece com `status` e
`motivo_cancelamento`, e o espelho no Google Agenda é removido.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora, como_utc
from oraculo.db.models import (
    Agendamento,
    Membro,
    OrigemAcao,
    Presenca,
    StatusAgendamento,
    StatusPresenca,
    TipoAgendamento,
)
from oraculo.domain.errors import BusinessRuleError
from oraculo.domain.permissions import Acao, exigir
from oraculo.integrations.google_calendar import (
    AgendaDesabilitada,
    AgendaExterna,
    AlteracaoExterna,
    EventoExterno,
)
from oraculo.logging_config import get_logger
from oraculo.repositories import agenda as repo_agenda
from oraculo.repositories import auditoria

log = get_logger(__name__)

ACAO_CRIAR = {
    TipoAgendamento.REUNIAO: Acao.CRIAR_REUNIAO,
    TipoAgendamento.EVENTO: Acao.CRIAR_EVENTO,
}
ACAO_GERIR = {
    TipoAgendamento.REUNIAO: Acao.GERIR_REUNIAO,
    TipoAgendamento.EVENTO: Acao.GERIR_EVENTO,
}


class DataInvalidaError(BusinessRuleError):
    """Agendamento no passado ou com intervalo inconsistente."""

    regra = "RF-007/RF-008"


class AgendamentoEncerradoError(BusinessRuleError):
    """Operação sobre agendamento já cancelado ou concluído (RN-010)."""

    regra = "RN-010"


@dataclass(slots=True)
class ResultadoAgendamento:
    agendamento: Agendamento
    convidados: list[Presenca]
    sincronizado_google: bool
    erro_google: str | None = None


@dataclass(slots=True)
class ResumoSincronizacaoExterna:
    """Resultado de aplicar as alterações vindas do Google Agenda (US-305)."""

    atualizados: int = 0
    cancelados: int = 0
    ignorados: int = 0


class AgendaService:
    def __init__(self, agenda_externa: AgendaExterna | None = None) -> None:
        self._externa = agenda_externa or AgendaDesabilitada()

    # -- Criação -----------------------------------------------------------

    async def criar(
        self,
        session: AsyncSession,
        *,
        tipo: TipoAgendamento,
        titulo: str,
        inicio_em: datetime,
        organizador: Membro,
        descricao: str | None = None,
        local: str | None = None,
        fim_em: datetime | None = None,
        convidados: Iterable[Membro] = (),
        guild_id: int | None = None,
        origem: OrigemAcao = OrigemAcao.DISCORD,
    ) -> ResultadoAgendamento:
        """UC-004 / UC-005 — cria, convida e sincroniza com o Google Agenda."""
        exigir(organizador.perfil, ACAO_CRIAR[tipo])
        self._validar_datas(inicio_em, fim_em)

        agendamento = await repo_agenda.criar(
            session,
            tipo=tipo,
            titulo=titulo,
            inicio_em=inicio_em,
            organizador=organizador,
            descricao=descricao,
            local=local,
            fim_em=fim_em,
            guild_id=guild_id,
        )

        # O organizador entra já confirmado; os demais como pendentes (UC-006).
        presenca_organizador = await repo_agenda.convidar(
            session, agendamento=agendamento, membro=organizador
        )
        presenca_organizador.status = StatusPresenca.CONFIRMADO
        presenca_organizador.respondido_em = agora()

        convidados_unicos = [c for c in convidados if c.id != organizador.id]
        presencas = [presenca_organizador]
        for convidado in convidados_unicos:
            presencas.append(
                await repo_agenda.convidar(session, agendamento=agendamento, membro=convidado)
            )

        emails = tuple(
            m.email for m in (organizador, *convidados_unicos) if m.email
        )
        sincronizado, erro = await self._sincronizar_criacao(agendamento, emails)

        await auditoria.registrar(
            session,
            acao=f"{tipo.value}.criado",
            resumo=f"{organizador.nome_exibicao} criou {tipo.value} '{agendamento.titulo}'",
            ator=organizador,
            alvo_tipo="agendamento",
            alvo_id=agendamento.id,
            dados={
                "tipo": tipo.value,
                "inicio_em": inicio_em.isoformat(),
                "convidados": len(presencas),
                "google_event_id": agendamento.google_event_id,
            },
            origem=origem,
            guild_id=guild_id,
        )
        return ResultadoAgendamento(agendamento, presencas, sincronizado, erro)

    # -- Cancelamento ------------------------------------------------------

    async def cancelar(
        self,
        session: AsyncSession,
        *,
        agendamento: Agendamento,
        solicitante: Membro,
        motivo: str,
        origem: OrigemAcao = OrigemAcao.DISCORD,
    ) -> Agendamento:
        """RN-010 — cancelamento lógico; a linha nunca é apagada."""
        self._exigir_gestao(agendamento, solicitante)
        if agendamento.status != StatusAgendamento.AGENDADO:
            raise AgendamentoEncerradoError(
                f"Agendamento já está como '{StatusAgendamento(agendamento.status).value}'."
            )

        agendamento.status = StatusAgendamento.CANCELADO
        agendamento.cancelado_em = agora()
        agendamento.cancelado_por_id = solicitante.id
        agendamento.motivo_cancelamento = (motivo or "").strip()[:500] or "Sem motivo informado"

        if agendamento.google_event_id:
            try:
                await self._externa.cancelar(agendamento.google_event_id)
            except Exception as exc:  # noqa: BLE001 — cancelamento local prevalece
                log.warning("Falha ao remover evento do Google Agenda: %s", exc)

        await auditoria.registrar(
            session,
            acao=f"{TipoAgendamento(agendamento.tipo).value}.cancelado",
            resumo=(
                f"{solicitante.nome_exibicao} cancelou '{agendamento.titulo}': "
                f"{agendamento.motivo_cancelamento}"
            ),
            ator=solicitante,
            alvo_tipo="agendamento",
            alvo_id=agendamento.id,
            dados={"motivo": agendamento.motivo_cancelamento},
            origem=origem,
            guild_id=agendamento.guild_id,
        )
        return agendamento

    # -- Google Agenda → bot (US-305, sentido Google → bot) ------------------

    async def aplicar_alteracoes_externas(
        self, session: AsyncSession, alteracoes: Iterable[AlteracaoExterna]
    ) -> ResumoSincronizacaoExterna:
        """Traz para o bot o que mudou direto no Google Agenda.

        * evento apagado no Google → agendamento cancelado (lógico, RN-010), sem
          tentar apagar de novo no Google;
        * título, descrição, local ou horário alterados → copiados para o bot.

        Só mexe em agendamentos ainda `AGENDADO` e ligados a um evento do
        Google; eventos que o bot não criou são ignorados. Idempotente: aplicar
        a mesma alteração duas vezes não muda nada na segunda.
        """
        resumo = ResumoSincronizacaoExterna()
        for alteracao in alteracoes:
            agendamento = await session.scalar(
                select(Agendamento).where(Agendamento.google_event_id == alteracao.evento_id)
            )
            if agendamento is None or agendamento.status != StatusAgendamento.AGENDADO:
                resumo.ignorados += 1
                continue

            if alteracao.cancelado:
                await self._cancelar_por_fora(session, agendamento)
                resumo.cancelados += 1
            elif await self._atualizar_por_fora(session, agendamento, alteracao):
                resumo.atualizados += 1
            else:
                resumo.ignorados += 1
        return resumo

    async def _cancelar_por_fora(self, session: AsyncSession, agendamento: Agendamento) -> None:
        agendamento.status = StatusAgendamento.CANCELADO
        agendamento.cancelado_em = agora()
        agendamento.motivo_cancelamento = "Cancelado no Google Agenda"
        agendamento.google_sincronizado_em = agora()
        await auditoria.registrar(
            session,
            acao=f"{TipoAgendamento(agendamento.tipo).value}.cancelado",
            resumo=f"'{agendamento.titulo}' cancelado no Google Agenda",
            ator_descricao="Google Agenda",
            alvo_tipo="agendamento",
            alvo_id=agendamento.id,
            dados={"motivo": agendamento.motivo_cancelamento, "origem_externa": "google"},
            origem=OrigemAcao.SISTEMA,
            guild_id=agendamento.guild_id,
        )

    async def _atualizar_por_fora(
        self, session: AsyncSession, agendamento: Agendamento, alteracao: AlteracaoExterna
    ) -> bool:
        novos = {
            "titulo": (alteracao.titulo or "").strip()[:160] or agendamento.titulo,
            "descricao": alteracao.descricao or None,
            "local": (alteracao.local or "").strip()[:200] or None,
            "inicio_em": alteracao.inicio_em or como_utc(agendamento.inicio_em),
            "fim_em": alteracao.fim_em,
        }
        atuais = {
            "titulo": agendamento.titulo,
            "descricao": agendamento.descricao or None,
            "local": agendamento.local or None,
            "inicio_em": como_utc(agendamento.inicio_em),
            "fim_em": como_utc(agendamento.fim_em) if agendamento.fim_em else None,
        }
        # O bot espelha evento sem fim com fim == início; não é uma mudança real.
        if novos["fim_em"] == novos["inicio_em"] and atuais["fim_em"] is None:
            novos["fim_em"] = None

        mudancas = {campo: valor for campo, valor in novos.items() if valor != atuais[campo]}
        if not mudancas:
            return False
        if novos["fim_em"] is not None and novos["fim_em"] < novos["inicio_em"]:
            log.warning(
                "Alteração do Google ignorada: fim antes do início (agendamento=%s).",
                agendamento.id,
            )
            return False

        for campo, valor in mudancas.items():
            setattr(agendamento, campo, valor)
        agendamento.google_sincronizado_em = agora()

        await auditoria.registrar(
            session,
            acao=f"{TipoAgendamento(agendamento.tipo).value}.atualizado_externamente",
            resumo=f"'{agendamento.titulo}' alterado no Google Agenda: {', '.join(mudancas)}",
            ator_descricao="Google Agenda",
            alvo_tipo="agendamento",
            alvo_id=agendamento.id,
            dados={
                campo: valor.isoformat() if isinstance(valor, datetime) else valor
                for campo, valor in mudancas.items()
            },
            origem=OrigemAcao.SISTEMA,
            guild_id=agendamento.guild_id,
        )
        return True

    # -- RSVP --------------------------------------------------------------

    async def responder_rsvp(
        self,
        session: AsyncSession,
        *,
        agendamento: Agendamento,
        membro: Membro,
        status: StatusPresenca,
        observacao: str | None = None,
        origem: OrigemAcao = OrigemAcao.DISCORD,
    ) -> Presenca:
        """UC-006 — confirmar, recusar ou voltar a pendente."""
        if agendamento.status != StatusAgendamento.AGENDADO:
            raise AgendamentoEncerradoError(
                "Não é possível responder a um agendamento cancelado ou concluído."
            )

        # Convite implícito: quem tem acesso ao anúncio pode responder (RF-009).
        presenca = await repo_agenda.convidar(session, agendamento=agendamento, membro=membro)
        presenca.status = status
        presenca.respondido_em = agora()
        presenca.observacao = (observacao or None) and observacao.strip()[:300]

        await auditoria.registrar(
            session,
            acao="rsvp.respondido",
            resumo=(
                f"{membro.nome_exibicao} marcou '{status.value}' em '{agendamento.titulo}'"
            ),
            ator=membro,
            alvo_tipo="agendamento",
            alvo_id=agendamento.id,
            dados={"status": status.value},
            origem=origem,
            guild_id=agendamento.guild_id,
        )
        return presenca

    async def resumo_presencas(self, session: AsyncSession, agendamento_id: int) -> dict[str, int]:
        return await repo_agenda.contar_por_status(session, agendamento_id=agendamento_id)

    # -- Interno -----------------------------------------------------------

    def _exigir_gestao(self, agendamento: Agendamento, solicitante: Membro) -> None:
        """Organizador gere o próprio agendamento; demais precisam da permissão."""
        if agendamento.organizador_id == solicitante.id:
            return
        exigir(
            solicitante.perfil,
            ACAO_GERIR[TipoAgendamento(agendamento.tipo)],
        )

    @staticmethod
    def _validar_datas(inicio_em: datetime, fim_em: datetime | None) -> None:
        if inicio_em.tzinfo is None:
            raise DataInvalidaError("Informe a data/hora com fuso horário (timezone-aware).")
        if inicio_em <= agora():
            raise DataInvalidaError("O início deve estar no futuro.")
        if fim_em is not None and fim_em <= inicio_em:
            raise DataInvalidaError("O término deve ser posterior ao início.")

    async def _sincronizar_criacao(
        self, agendamento: Agendamento, emails: tuple[str, ...]
    ) -> tuple[bool, str | None]:
        """RN-009 — espelha no Google Agenda sem bloquear o registro local."""
        evento = EventoExterno(
            titulo=agendamento.titulo,
            inicio_em=agendamento.inicio_em,
            fim_em=agendamento.fim_em,
            descricao=agendamento.descricao,
            local=agendamento.local,
            convidados_email=emails,
        )
        try:
            evento_id = await self._externa.criar(evento)
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao criar evento no Google Agenda")
            return False, f"{type(exc).__name__}: {exc}"[:500]

        if evento_id:
            agendamento.google_event_id = evento_id
            agendamento.google_sincronizado_em = agora()
            return True, None
        return False, None
