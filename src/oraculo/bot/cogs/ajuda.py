"""`/ajuda` — catálogo de comandos por cargo (RN-008).

A lista é derivada da árvore de comandos e da política central de permissões,
nunca escrita à mão: um comando novo aparece aqui sozinho, e um comando cuja
permissão mude troca de seção sem ninguém editar texto.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot.permissions import acao_requerida, obter_autor, requer
from oraculo.domain.hierarchy import HIERARQUIA, Cargo, cargo_por_slug
from oraculo.domain.permissions import Acao, cargo_minimo, pode_executar


def agrupar_por_cargo(
    comandos: list[app_commands.Command],
) -> dict[Cargo, list[app_commands.Command]]:
    """Organiza os comandos pelo cargo mínimo que cada um exige."""
    grupos: dict[Cargo, list[app_commands.Command]] = {}
    for comando in comandos:
        acao = acao_requerida(comando)
        if acao is None:
            continue
        grupos.setdefault(cargo_minimo(acao), []).append(comando)
    for lista in grupos.values():
        lista.sort(key=lambda c: c.qualified_name)
    return grupos


class AjudaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ajuda", description="Lista os comandos do Oráculo e o seu acesso.")
    @app_commands.describe(
        tudo="Mostra também os comandos que exigem cargo acima do seu (padrão: sim)."
    )
    @requer(Acao.VER_PERFIL, efemero=True)
    async def ajuda(self, interaction: discord.Interaction, tudo: bool = True) -> None:
        autor = await obter_autor(interaction)
        cargo = cargo_por_slug(autor.cargo_slug)
        grupos = agrupar_por_cargo(list(self.bot.tree.walk_commands()))

        embed = discord.Embed(
            title="🏛️ Comandos do Bot Oráculo",
            description=(
                f"Seu cargo: **{cargo.nome}**\n"
                "✅ disponível para você · 🔒 exige cargo superior"
            ),
            color=discord.Color.blurple(),
        )

        for cargo_exigido in HIERARQUIA:
            comandos = grupos.get(cargo_exigido)
            if not comandos:
                continue

            liberado = pode_executar(cargo, Acao.VER_PERFIL) and cargo >= cargo_exigido
            if not liberado and not tudo:
                continue

            marca = "✅" if liberado else "🔒"
            linhas = [f"`/{c.qualified_name}` — {c.description}" for c in comandos]
            titulo = (
                f"{marca} Todos os membros"
                if cargo_exigido.ordem == 0
                else f"{marca} {cargo_exigido.nome} ou superior"
            )
            embed.add_field(name=titulo, value="\n".join(linhas), inline=False)

        embed.set_footer(
            text="Digite / no chat e escolha o comando na lista — colar o texto não funciona."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AjudaCog(bot))
