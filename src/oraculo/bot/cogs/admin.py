"""Comandos administrativos — RN-008, RF-012, RNF-003, RNF-004.

Inclui o diagnóstico de cargos ausentes no servidor, que é a causa mais comum
de falha silenciosa na sincronização (RF-006).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.bot.permissions import obter_autor, requer
from oraculo.bot.role_sync import cargos_faltantes
from oraculo.db.base import sessao
from oraculo.db.models import OrigemAcao
from oraculo.domain.hierarchy import HIERARQUIA, cargo_por_slug
from oraculo.domain.permissions import Acao
from oraculo.repositories import auditoria as repo_auditoria
from oraculo.repositories import membros as repo_membros
from oraculo.services import vinculo_service
from oraculo.services.notificacao_service import NotificacaoService


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="hierarquia", description="Mostra a hierarquia TYTO e os limiares de XP."
    )
    @requer(Acao.VER_PERFIL, efemero=True)
    async def hierarquia(self, interaction: discord.Interaction) -> None:
        linhas = []
        for cargo in HIERARQUIA:
            limiar = f"{cargo.xp_minimo} XP" if cargo.automatico else "atribuição manual"
            linhas.append(f"**{cargo.nome}** — {limiar}\n> {cargo.descricao}")
        await interaction.followup.send(
            embed=discord.Embed(
                title="🏛️ Hierarquia do Clube TYTO",
                description="\n\n".join(linhas),
                color=discord.Color.blurple(),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="definir-cargo", description="Define manualmente o cargo de um membro (Admin)."
    )
    @app_commands.describe(
        membro="Membro alvo.", cargo="Cargo TYTO de destino.", motivo="Justificativa (auditada)."
    )
    @app_commands.choices(
        cargo=[app_commands.Choice(name=c.nome, value=c.slug) for c in HIERARQUIA]
    )
    @requer(Acao.DEFINIR_CARGO_MANUAL, efemero=True)
    async def definir_cargo(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        cargo: app_commands.Choice[str],
        motivo: app_commands.Range[str, 3, 500],
    ) -> None:
        destino = cargo_por_slug(cargo.value)
        container = self.bot.container

        async with sessao() as session:
            autor = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            alvo = await repo_membros.obter_ou_criar_por_discord(
                session, discord_id=membro.id, nome_exibicao=membro.display_name
            )
            resultado = await container.promocoes.aplicar(
                session,
                alvo,
                cargo_novo=destino,
                automatica=False,
                autor_descricao=autor.nome_exibicao,
                motivo=motivo,
                origem=OrigemAcao.DISCORD,
                guild_id=interaction.guild_id,
            )

        await container.notificacoes.enviar(
            NotificacaoService.promocao(
                nome=membro.display_name,
                cargo_anterior=resultado.cargo_anterior.nome,
                cargo_novo=resultado.cargo_atual.nome,
                xp=alvo.xp,
                discord_id=membro.id,
            )
        )
        aviso = "" if resultado.sincronizado else "\n⚠️ Cargo não sincronizado no Discord."
        await interaction.followup.send(
            f"Cargo de **{membro.display_name}** definido como **{destino.nome}**.{aviso}",
            ephemeral=True,
        )

    @app_commands.command(
        name="reconciliar-conta",
        description="Mescla um registro órfão da plataforma numa conta Discord (RN-016).",
    )
    @app_commands.describe(
        membro="Conta Discord que já existe no bot.",
        identificador="E-mail ou ID (id_externo) do registro da plataforma a mesclar.",
    )
    @requer(Acao.RECONCILIAR_CONTA, efemero=True)
    async def reconciliar_conta(
        self, interaction: discord.Interaction, membro: discord.Member, identificador: str
    ) -> None:
        autor = await obter_autor(interaction)
        async with sessao() as session:
            sobrevivente = await vinculo_service.reconciliar_manualmente(
                session,
                discord_id=membro.id,
                identificador=identificador,
                autor_descricao=autor.nome_exibicao,
                guild_id=interaction.guild_id,
            )
            id_externo = sobrevivente.id_externo

        await interaction.followup.send(
            f"Conta de **{membro.display_name}** agora está ligada ao registro da plataforma "
            f"`{id_externo}`. XP/cargo acompanham a próxima sincronização.",
            ephemeral=True,
        )

    @app_commands.command(
        name="verificar-cargos", description="Verifica se os cargos TYTO existem no servidor."
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
            texto = "Cargos ausentes (a sincronização falhará até criá-los):\n" + "\n".join(
                f"• {nome}" for nome in faltantes
            )
            cor = discord.Color.orange()
        else:
            texto = "Todos os cargos da hierarquia TYTO existem neste servidor. ✅"
            cor = discord.Color.green()

        await interaction.followup.send(
            embed=discord.Embed(title="Diagnóstico de cargos", description=texto, color=cor),
            ephemeral=True,
        )

    @app_commands.command(
        name="auditoria", description="Últimos registros do log de auditoria (Conselheiro+)."
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
