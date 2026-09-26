"""Integração com o Google Agenda — RN-009 / RF-011 / US-305 (bidirecional).

Bot → Google: criar, atualizar e cancelar o espelho de cada agendamento.
Google → bot: `alteracoes_desde` lista o que mudou no calendário (inclusive
eventos apagados) para `AgendaService.aplicar_alteracoes_externas`.

A biblioteca oficial é síncrona; as chamadas são executadas em thread separada
(`asyncio.to_thread`) para não bloquear o event loop do bot.

Quando a integração está desabilitada (`ORACULO_GOOGLE_ENABLED=false`), usa-se
`AgendaDesabilitada`, que registra a intenção em log e devolve `None`. Assim o
fluxo de reuniões/eventos continua utilizável em desenvolvimento sem credenciais.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from oraculo.config import Settings, get_settings
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.logging_config import get_logger

log = get_logger(__name__)

ESCOPOS = ["https://www.googleapis.com/auth/calendar"]


@dataclass(slots=True)
class EventoExterno:
    """Dados mínimos de um evento espelhado na agenda externa."""

    titulo: str
    inicio_em: datetime
    fim_em: datetime | None
    descricao: str | None = None
    local: str | None = None
    convidados_email: tuple[str, ...] = ()


@dataclass(slots=True)
class AlteracaoExterna:
    """Estado atual de um evento que mudou no calendário externo."""

    evento_id: str
    cancelado: bool
    titulo: str | None = None
    descricao: str | None = None
    local: str | None = None
    inicio_em: datetime | None = None
    fim_em: datetime | None = None


class AgendaExterna(Protocol):
    """Porta de calendário — permite trocar Google por outro provedor."""

    async def criar(self, evento: EventoExterno) -> str | None: ...

    async def atualizar(self, evento_id: str, evento: EventoExterno) -> None: ...

    async def cancelar(self, evento_id: str) -> None: ...

    async def alteracoes_desde(self, desde: datetime) -> list[AlteracaoExterna]: ...


class AgendaDesabilitada:
    """No-op consciente: mantém o fluxo funcionando sem credenciais Google."""

    async def criar(self, evento: EventoExterno) -> str | None:
        log.info("Google Agenda desabilitado; evento %r não sincronizado.", evento.titulo)
        return None

    async def atualizar(self, evento_id: str, evento: EventoExterno) -> None:
        log.info("Google Agenda desabilitado; atualização de %s ignorada.", evento_id)

    async def cancelar(self, evento_id: str) -> None:
        log.info("Google Agenda desabilitado; cancelamento de %s ignorado.", evento_id)

    async def alteracoes_desde(self, desde: datetime) -> list[AlteracaoExterna]:
        return []


class GoogleAgenda:
    """Cliente do Google Calendar via service account ou credenciais OAuth2."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._servico: Any | None = None

    # -- Ciclo de vida -----------------------------------------------------

    def _conectar(self) -> Any:
        """Constrói o serviço sob demanda (chamado sempre dentro de thread)."""
        if self._servico is not None:
            return self._servico
        if not self._cfg.google_credentials_file:
            raise IntegracaoIndisponivelError(
                "Google Agenda", "ORACULO_GOOGLE_CREDENTIALS_FILE não definido."
            )
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credenciais = service_account.Credentials.from_service_account_file(
                str(self._cfg.google_credentials_file), scopes=ESCOPOS
            )
            self._servico = build("calendar", "v3", credentials=credenciais, cache_discovery=False)
        except Exception as exc:  # noqa: BLE001
            raise IntegracaoIndisponivelError("Google Agenda", str(exc)) from exc
        return self._servico

    # -- Operações ---------------------------------------------------------

    async def criar(self, evento: EventoExterno) -> str | None:
        corpo = self._para_corpo(evento)
        criado = await asyncio.to_thread(self._criar_sync, corpo)
        return criado.get("id") if criado else None

    async def atualizar(self, evento_id: str, evento: EventoExterno) -> None:
        await asyncio.to_thread(self._atualizar_sync, evento_id, self._para_corpo(evento))

    async def cancelar(self, evento_id: str) -> None:
        await asyncio.to_thread(self._cancelar_sync, evento_id)

    async def alteracoes_desde(self, desde: datetime) -> list[AlteracaoExterna]:
        """Eventos alterados (ou apagados) no calendário desde `desde`."""
        brutos = await asyncio.to_thread(self._listar_alterados_sync, desde)
        return [alteracao_de_evento(bruto) for bruto in brutos]

    # -- Implementação síncrona -------------------------------------------

    def _criar_sync(self, corpo: dict) -> dict:
        servico = self._conectar()
        return (
            servico.events()
            .insert(calendarId=self._cfg.google_calendar_id, body=corpo, sendUpdates="all")
            .execute()
        )

    def _atualizar_sync(self, evento_id: str, corpo: dict) -> dict:
        servico = self._conectar()
        return (
            servico.events()
            .patch(
                calendarId=self._cfg.google_calendar_id,
                eventId=evento_id,
                body=corpo,
                sendUpdates="all",
            )
            .execute()
        )

    def _listar_alterados_sync(self, desde: datetime) -> list[dict]:
        servico = self._conectar()
        eventos: list[dict] = []
        pagina: str | None = None
        while True:
            resposta = (
                servico.events()
                .list(
                    calendarId=self._cfg.google_calendar_id,
                    updatedMin=desde.isoformat(),
                    # Apagados vêm com status "cancelled" — é assim que o bot
                    # descobre um cancelamento feito direto no Google.
                    showDeleted=True,
                    singleEvents=True,
                    maxResults=250,
                    pageToken=pagina,
                )
                .execute()
            )
            eventos.extend(resposta.get("items", []))
            pagina = resposta.get("nextPageToken")
            if not pagina:
                return eventos

    def _cancelar_sync(self, evento_id: str) -> None:
        servico = self._conectar()
        servico.events().delete(
            calendarId=self._cfg.google_calendar_id, eventId=evento_id, sendUpdates="all"
        ).execute()

    def _para_corpo(self, evento: EventoExterno) -> dict:
        fim = evento.fim_em or evento.inicio_em
        return {
            "summary": evento.titulo,
            "description": evento.descricao or "",
            "location": evento.local or "",
            "start": {
                "dateTime": evento.inicio_em.isoformat(),
                "timeZone": self._cfg.google_timezone,
            },
            "end": {"dateTime": fim.isoformat(), "timeZone": self._cfg.google_timezone},
            "attendees": [{"email": email} for email in evento.convidados_email],
            "reminders": {
                "useDefault": False,
                # RF-011 — lembretes: 1 dia antes por e-mail, 30 min antes popup.
                "overrides": [
                    {"method": "email", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 30},
                ],
            },
        }


def _data_do_evento(campo: dict | None) -> datetime | None:
    """`start`/`end` do Google: `dateTime` (evento com hora) ou `date` (dia inteiro)."""
    if not campo:
        return None
    valor = campo.get("dateTime") or campo.get("date")
    if not valor:
        return None
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def alteracao_de_evento(evento: dict) -> AlteracaoExterna:
    """Converte um item de `events.list` no formato neutro da porta."""
    if evento.get("status") == "cancelled":
        return AlteracaoExterna(evento_id=evento["id"], cancelado=True)
    return AlteracaoExterna(
        evento_id=evento["id"],
        cancelado=False,
        titulo=evento.get("summary"),
        descricao=evento.get("description") or None,
        local=evento.get("location") or None,
        inicio_em=_data_do_evento(evento.get("start")),
        fim_em=_data_do_evento(evento.get("end")),
    )


def criar_agenda_externa(settings: Settings | None = None) -> AgendaExterna:
    cfg = settings or get_settings()
    if not cfg.google_enabled:
        return AgendaDesabilitada()
    log.info("Google Agenda habilitado (calendário: %s).", cfg.google_calendar_id)
    return GoogleAgenda(cfg)
