"""`/perguntar` — regulamento TYTO e projetos do membro (RN-017).

A resposta é **sempre efêmera**, e isso é segurança, não preferência: ela pode
conter conteúdo de um projeto restrito, e uma resposta pública no canal
entregaria esse conteúdo a quem não tem acesso — anulando, na saída, a
autorização aplicada na entrada (`services/pergunta_service.py`).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.bot.permissions import requer
from oraculo.db.base import sessao
from oraculo.domain.permissions import Acao
from oraculo.repositories import membros as repo_membros

LIMITE_DESCRICAO_EMBED = 4000
"""O embed do Discord corta em 4096; a margem cobre o rodapé de fontes."""


class PerguntaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="perguntar",
        description="Pergunte ao Oráculo sobre as regras do TYTO e seus projetos.",
    )
    @app_commands.describe(pergunta="O que você quer saber?")
    @requer(Acao.PERGUNTAR, efemero=True)
    async def perguntar(
        self, interaction: discord.Interaction, pergunta: app_commands.Range[str, 3, 1000]
    ) -> None:
        servico = self.bot.container.perguntas
        if servico is None:
            await interaction.followup.send(
                embed=embeds.erro(
                    "As perguntas ao Oráculo não estão configuradas neste servidor — "
                    "peça a um Administrador para configurar a chave da API do modelo."
                ),
                ephemeral=True,
            )
            return

        async with sessao() as session:
            membro = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            resposta = await servico.perguntar(
                session,
                membro,
                pergunta=pergunta,
                guild_id=interaction.guild_id,
            )

        embed = discord.Embed(
            title="🏛️ Oráculo",
            description=resposta.texto[:LIMITE_DESCRICAO_EMBED],
            color=discord.Color.blurple(),
        )
        if resposta.projetos_consultados:
            embed.set_footer(
                text="Projetos consultados: " + ", ".join(resposta.projetos_consultados)
            )
        else:
            embed.set_footer(text="Baseado no regulamento do Clube TYTO.")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PerguntaCog(bot))
