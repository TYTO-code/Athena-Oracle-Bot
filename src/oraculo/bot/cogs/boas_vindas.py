"""Banner de boas-vindas ao entrar no servidor.

Funcionalidade de engajamento, sem RN correspondente — não lê nem escreve dado algum da plataforma
TYTO.club (RN-021 não se aplica). Falha ao montar ou publicar o banner nunca é visível a ninguém
além dos logs: é cosmético, então nunca deve travar nem avisar quem entrou.
"""

from __future__ import annotations

import io

import discord
from discord.ext import commands

from oraculo.bot.welcome_image import montar_banner
from oraculo.logging_config import get_logger

log = get_logger(__name__)


class BoasVindasCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        settings = self.bot.settings  # type: ignore[attr-defined]
        canal_id = settings.discord_boas_vindas_channel_id
        if not canal_id:
            return

        canal = self.bot.get_channel(canal_id)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(canal_id)
            except discord.HTTPException:
                log.warning("Canal de boas-vindas %s não encontrado", canal_id)
                return
        if not isinstance(canal, discord.abc.Messageable):
            log.warning("Canal de boas-vindas %s não aceita mensagens", canal_id)
            return

        try:
            avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
            banner = montar_banner(avatar_bytes)
        except Exception:
            log.exception("Falha ao montar o banner de boas-vindas de %s", member.id)
            return

        arquivo = discord.File(io.BytesIO(banner), filename="boas-vindas.png")
        mensagem = f"Bem-vindo(a) ao Clube TYTO, {member.mention}! 🎉"
        try:
            await canal.send(content=mensagem, file=arquivo)
        except discord.HTTPException:
            log.exception("Falha ao publicar o banner de boas-vindas de %s", member.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BoasVindasCog(bot))
