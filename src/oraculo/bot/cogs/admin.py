"""Comandos administrativos — RN-008, RF-012, RNF-003, RNF-004.

Inclui o diagnóstico de papéis ausentes no servidor, que é a causa mais comum
de falha silenciosa na sincronização (RF-006), e a reaplicação de papéis
no servidor. O bot só **consulta** a plataforma: patente, XP e cargos vêm da TYTO.club.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.bot.permissions import requer
from oraculo.bot.role_sync import cargos_faltantes
from oraculo.db.base import sessao
from oraculo.domain.hierarchy import PATENTES, CargoInstitucional
from oraculo.domain.permissions import Acao
from oraculo.repositories import auditoria as repo_auditoria
from oraculo.repositories import membros as repo_membros


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="hierarquia", description="Mostra a escala de patentes e os cargos institucionais."
    )
    @requer(Acao.VER_PERFIL, efemero=True)
    async def hierarquia(self, interaction: discord.Interaction) -> None:
        patentes = "\n".join(
            f"`{p.ordem:>2}` **{p.nome}** — {p.xp_minimo:,} XP".replace(",", ".")
            for p in PATENTES
        )
        cargos = (
            "**Conselheiro** — eleito pelo Conselho Régio (Carta Art. III/IV)\n"
            "**Administrador** — governança técnica do bot\n"
            "Espelhados da TYTO.club (o bot só consulta) e acumuláveis com qualquer patente."
        )
        embed = discord.Embed(
            title="🏛️ Hierarquia do Clube TYTO",
            description=(
                "A patente vem só do XP e nunca é perdida (XP.md Art. 1º).\n\n" + patentes
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Cargos institucionais", value=cargos, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="sincronizar-papeis",
        description="Reaplica no Discord a patente e os cargos gravados no banco (Admin).",
    )
    @app_commands.describe(membro="Membro cujos papéis devem ser reaplicados.")
    @requer(Acao.ADMINISTRAR_SISTEMA, efemero=True)
    async def sincronizar_papeis(
        self, interaction: discord.Interaction, membro: discord.Member
    ) -> None:
        sincronizador = self.bot.container.promocoes.sincronizador
        if sincronizador is None:
            await interaction.followup.send(
                embed=embeds.erro("Sincronização com o Discord indisponível."), ephemeral=True
            )
            return

        async with sessao() as session:
            alvo = await repo_membros.obter_cadastrado_por_discord(
                session, membro.id, sujeito=membro.display_name
            )
            perfil = alvo.perfil

        await sincronizador.sincronizar(
            discord_id=membro.id, patente=perfil.patente, guild_id=interaction.guild_id
        )
        for cargo in CargoInstitucional:
            await sincronizador.definir_cargo_institucional(
                discord_id=membro.id,
                cargo=cargo,
                ativo=perfil.possui(cargo),
                guild_id=interaction.guild_id,
            )
        await interaction.followup.send(
            f"Papéis de **{membro.display_name}** reaplicados: **{perfil.descricao()}**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="verificar-cargos", description="Verifica se os papéis TYTO existem no servidor."
    )
    @requer(Acao.ADMINISTRAR_SISTEMA, efemero=True)
    async def verificar_cargos(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.followup.send(
                embed=embeds.erro("Use este comando dentro de um servidor."), ephemeral=True
            )
            return

        faltantes = await cargos_faltantes(interaction.guild)
        if faltantes:
            texto = "Papéis ausentes (a sincronização falhará até criá-los):\n" + "\n".join(
                f"• {nome}" for nome in faltantes
            )
            cor = discord.Color.orange()
        else:
            texto = "Todos os papéis TYTO (patentes e cargos) existem neste servidor. ✅"
            cor = discord.Color.green()

        await interaction.followup.send(
            embed=discord.Embed(title="Diagnóstico de papéis", description=texto, color=cor),
            ephemeral=True,
        )

    @app_commands.command(
        name="auditoria", description="Últimos registros do log de auditoria (Conselheiro)."
    )
    @app_commands.describe(limite="Quantidade de registros (1 a 20).")
    @requer(Acao.VER_AUDITORIA, efemero=True)
    async def auditoria(
        self, interaction: discord.Interaction, limite: app_commands.Range[int, 1, 20] = 10
    ) -> None:
        async with sessao() as session:
            registros = await repo_auditoria.listar(session, limite=limite)
            linhas = [f"`{r.criado_em:%d/%m %H:%M}` **{r.acao}** — {r.resumo}" for r in registros]

        await interaction.followup.send(
            embed=discord.Embed(
                title="🧾 Log de auditoria",
                description="\n".join(linhas) or "Nenhum registro ainda.",
                color=discord.Color.blurple(),
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
