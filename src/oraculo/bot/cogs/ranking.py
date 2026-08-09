"""`/ranking` — RF-004 / UC-002 / US-202."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.bot.permissions import requer
from oraculo.db.base import sessao
from oraculo.domain.permissions import Acao

TITULOS = {
    "geral": "🏛️ Ranking geral do Clube TYTO",
    "semana": "🏛️ Ranking — últimos 7 dias",
    "mes": "🏛️ Ranking — últimos 30 dias",
    "trimestre": "🏛️ Ranking — últimos 90 dias",
}


class RankingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ranking", description="Ranking por XP, geral ou por período.")
    @app_commands.describe(
        periodo="Janela de apuração do ranking.",
        limite="Quantidade de posições (1 a 25).",
        somente_este_servidor="Considera apenas o XP movimentado neste servidor.",
    )
    @app_commands.choices(
        periodo=[
            app_commands.Choice(name="Geral (XP acumulado)", value="geral"),
            app_commands.Choice(name="Últimos 7 dias", value="semana"),
            app_commands.Choice(name="Últimos 30 dias", value="mes"),
            app_commands.Choice(name="Últimos 90 dias", value="trimestre"),
        ]
    )
    @requer(Acao.VER_RANKING)
    async def ranking(
        self,
        interaction: discord.Interaction,
        periodo: app_commands.Choice[str] | None = None,
        limite: app_commands.Range[int, 1, 25] = 10,
        somente_este_servidor: bool = False,
    ) -> None:
        escolha = periodo.value if periodo else "geral"
        await interaction.response.defer()

        guild_id = interaction.guild_id if somente_este_servidor else None
        async with sessao() as session:
            linhas = await self.bot.container.ranking.ranking(
                session,
                limite=limite,
                periodo=None if escolha == "geral" else escolha,
                guild_id=guild_id,
            )

        titulo = TITULOS[escolha]
        if somente_este_servidor and interaction.guild:
            titulo = f"{titulo} · {interaction.guild.name}"
        await interaction.followup.send(embed=embeds.ranking(linhas, titulo=titulo))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RankingCog(bot))
