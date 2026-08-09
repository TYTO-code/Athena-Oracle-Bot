"""Canal de notificação via Discord — RF-010 / US-302 / US-401.

Envia DM ao destinatário (quando houver) e espelha no canal `#logs-oráculo`
configurado, que funciona como registro visível das movimentações (RF-012).
"""

from __future__ import annotations

import discord

from oraculo.bot import embeds
from oraculo.config import get_settings
from oraculo.logging_config import get_logger
from oraculo.services.notificacao_service import Notificacao

log = get_logger(__name__)


class CanalDiscord:
    nome = "discord"

    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot
        self._cfg = get_settings()

    async def enviar(self, notificacao: Notificacao) -> None:
        embed = embeds.de_notificacao(notificacao)
        await self._enviar_dm(notificacao, embed)
        await self._enviar_canal_logs(embed)

    async def _enviar_dm(self, notificacao: Notificacao, embed: discord.Embed) -> None:
        if notificacao.destinatario_discord_id is None:
            return
        try:
            usuario = self._bot.get_user(notificacao.destinatario_discord_id)
            if usuario is None:
                usuario = await self._bot.fetch_user(notificacao.destinatario_discord_id)
            await usuario.send(embed=embed)
        except discord.Forbidden:
            # DM fechada é escolha do usuário: não é erro operacional.
            log.debug("DM bloqueada para %s.", notificacao.destinatario_discord_id)
        except discord.HTTPException as exc:
            log.warning("Falha ao enviar DM: %s", exc)

    async def _enviar_canal_logs(self, embed: discord.Embed) -> None:
        canal_id = self._cfg.discord_log_channel_id
        if canal_id is None:
            return
        canal = self._bot.get_channel(canal_id)
        if canal is None:
            log.warning("Canal de logs %s não encontrado.", canal_id)
            return
        try:
            await canal.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("Falha ao publicar no canal de logs: %s", exc)
