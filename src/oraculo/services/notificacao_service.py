"""Notificações — RF-010 / UC-001, UC-003, UC-004, UC-005.

O serviço só conhece o contrato `CanalNotificacao`; quem entrega é o canal
(Discord, e-mail, futuramente WhatsApp). Falha de um canal nunca interrompe os
demais nem o caso de uso que originou o aviso.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from oraculo.logging_config import get_logger

log = get_logger(__name__)


class Severidade(StrEnum):
    INFO = "info"
    SUCESSO = "sucesso"
    ALERTA = "alerta"
    ERRO = "erro"


@dataclass(slots=True)
class Notificacao:
    """Mensagem independente de canal."""

    titulo: str
    corpo: str
    severidade: Severidade = Severidade.INFO
    #: Discord ID do destinatário; `None` envia apenas aos canais públicos.
    destinatario_discord_id: int | None = None
    destinatario_email: str | None = None
    guild_id: int | None = None
    campos: dict[str, str] = field(default_factory=dict)


class CanalNotificacao(Protocol):
    nome: str

    async def enviar(self, notificacao: Notificacao) -> None: ...


class NotificacaoService:
    def __init__(self, canais: list[CanalNotificacao] | None = None) -> None:
        self._canais = canais or []

    def registrar_canal(self, canal: CanalNotificacao) -> None:
        self._canais.append(canal)

    async def enviar(self, notificacao: Notificacao) -> None:
        """Dispara em paralelo; erros são registrados, nunca propagados."""
        if not self._canais:
            log.debug("Sem canais de notificação; %r não enviada.", notificacao.titulo)
            return
        resultados = await asyncio.gather(
            *(canal.enviar(notificacao) for canal in self._canais),
            return_exceptions=True,
        )
        for canal, resultado in zip(self._canais, resultados, strict=True):
            if isinstance(resultado, Exception):
                log.warning("Canal %s falhou ao notificar: %s", canal.nome, resultado)

    # -- Fábricas de mensagens dos casos de uso ---------------------------

    @staticmethod
    def promocao(
        *, nome: str, cargo_anterior: str, cargo_novo: str, xp: int, discord_id: int | None
    ) -> Notificacao:
        """UC-003 — aviso de promoção."""
        return Notificacao(
            titulo="🏛️ Promoção no Clube TYTO",
            corpo=f"**{nome}** avançou de **{cargo_anterior}** para **{cargo_novo}**!",
            severidade=Severidade.SUCESSO,
            destinatario_discord_id=discord_id,
            campos={"XP acumulado": str(xp), "Novo cargo": cargo_novo},
        )

    @staticmethod
    def movimentacao_xp(
        *,
        nome: str,
        quantidade: int,
        motivo: str,
        saldo: int,
        autor: str,
        discord_id: int | None,
    ) -> Notificacao:
        """UC-001 — aviso de concessão/remoção de XP."""
        verbo = "recebeu" if quantidade > 0 else "perdeu"
        return Notificacao(
            titulo="⚡ Movimentação de XP",
            corpo=f"**{nome}** {verbo} **{abs(quantidade)} XP**.",
            severidade=Severidade.INFO if quantidade > 0 else Severidade.ALERTA,
            destinatario_discord_id=discord_id,
            campos={"Motivo": motivo, "Saldo atual": str(saldo), "Autor": autor},
        )

    @staticmethod
    def dracmas_creditado(
        *,
        nome: str,
        valor: int,
        motivo: str,
        saldo: int,
        discord_id: int | None,
        ingresso_cobrado: bool = False,
    ) -> Notificacao:
        """Comunidade — aviso de crédito de Dracmas (`DRACMAS.md` §2), com o ingresso automático
        na Comunidade destacado quando aplicável (`COMUNIDADE_E_CLUBE.md` Art. 3º §1º/§3º)."""
        corpo = f"**{nome}** recebeu **{valor} Dracmas**."
        if ingresso_cobrado:
            corpo += " Conta de Comunidade criada agora — 30.000 Dracmas de ingresso já descontados."
        return Notificacao(
            titulo="🪙 Dracmas creditados",
            corpo=corpo,
            severidade=Severidade.SUCESSO,
            destinatario_discord_id=discord_id,
            campos={"Motivo": motivo, "Saldo atual": str(saldo)},
        )

    @staticmethod
    def agendamento(
        *, tipo: str, titulo: str, quando: str, organizador: str, guild_id: int | None
    ) -> Notificacao:
        """UC-004 / UC-005 — anúncio de reunião ou evento."""
        return Notificacao(
            titulo=f"📅 Nova {tipo}: {titulo}",
            corpo=f"Organizado por **{organizador}**.",
            severidade=Severidade.INFO,
            guild_id=guild_id,
            campos={"Quando": quando},
        )
