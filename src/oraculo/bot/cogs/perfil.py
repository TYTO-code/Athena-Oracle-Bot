"""`/perfil` — RF-002 / US-201."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.bot.permissions import requer
from oraculo.db.base import sessao
from oraculo.domain.permissions import Acao
from oraculo.repositories import membros as repo_membros


class PerfilCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="perfil", description="Mostra cargo, XP, próximo cargo e posição no ranking."
    )
    @app_commands.describe(membro="Membro a consultar (padrão: você mesmo).")
    @requer(Acao.VER_PERFIL)
    async def perfil(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ) -> None:
        alvo = membro or interaction.user
        await interaction.response.defer()

        async with sessao() as session:
            registro = await repo_membros.obter_ou_criar_por_discord(
                session, discord_id=alvo.id, nome_exibicao=alvo.display_name
            )
            dados = await self.bot.container.ranking.perfil(session, registro)

        await interaction.followup.send(embed=embeds.perfil(dados))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PerfilCog(bot))
