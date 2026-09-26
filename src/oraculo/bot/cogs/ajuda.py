"""`/ajuda` — catálogo de comandos por requisito (RN-008).

A lista é derivada da árvore de comandos e da política central de permissões,
nunca escrita à mão: um comando novo aparece aqui sozinho, e um comando cuja
permissão mude troca de seção sem ninguém editar texto.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot.permissions import acao_requerida, obter_autor, requer
from oraculo.domain.hierarchy import NEOFITO, PATENTES, CargoInstitucional
from oraculo.domain.permissions import (
    Acao,
    Requisito,
    descrever_requisito,
    requisito_minimo,
    satisfaz,
)

#: Ordem das seções: patentes de baixo para cima, depois cargos institucionais.
ORDEM_REQUISITOS: tuple[Requisito, ...] = (*PATENTES, *CargoInstitucional)


def agrupar_por_requisito(
    comandos: list[app_commands.Command],
) -> dict[Requisito, list[app_commands.Command]]:
    """Organiza os comandos pelo requisito (patente ou cargo) que cada um exige."""
    grupos: dict[Requisito, list[app_commands.Command]] = {}
    for comando in comandos:
        acao = acao_requerida(comando)
        if acao is None:
            continue
        grupos.setdefault(requisito_minimo(acao), []).append(comando)
    for lista in grupos.values():
        lista.sort(key=lambda c: c.qualified_name)
    return grupos


class AjudaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ajuda", description="Lista os comandos do Oráculo e o seu acesso.")
    @app_commands.describe(
        tudo="Mostra também os comandos que você ainda não pode usar (padrão: sim)."
    )
    @requer(Acao.VER_PERFIL, efemero=True)
    async def ajuda(self, interaction: discord.Interaction, tudo: bool = True) -> None:
        autor = await obter_autor(interaction)
        perfil = autor.perfil
        grupos = agrupar_por_requisito(list(self.bot.tree.walk_commands()))

        embed = discord.Embed(
            title="🏛️ Comandos do Bot Oráculo",
            description=(
                f"Você: **{perfil.descricao()}**\n"
                "✅ disponível para você · 🔒 exige patente ou cargo que você não tem"
            ),
            color=discord.Color.blurple(),
        )

        for requisito in ORDEM_REQUISITOS:
            comandos = grupos.get(requisito)
            if not comandos:
                continue

            liberado = satisfaz(perfil, requisito)
            if not liberado and not tudo:
                continue

            marca = "✅" if liberado else "🔒"
            linhas = [f"`/{c.qualified_name}` — {c.description}" for c in comandos]
            titulo = (
                f"{marca} Todos os membros"
                if requisito == NEOFITO
                else f"{marca} {descrever_requisito(requisito).capitalize()}"
            )
            embed.add_field(name=titulo, value="\n".join(linhas), inline=False)

        embed.set_footer(
            text="Digite / no chat e escolha o comando na lista — colar o texto não funciona."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AjudaCog(bot))
