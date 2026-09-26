"""Comandos administrativos — RN-008, RF-012, RNF-003, RNF-004.

Inclui o diagnóstico de papéis ausentes no servidor, que é a causa mais comum
de falha silenciosa na sincronização (RF-006), e a gestão dos cargos
institucionais fora da escala de patentes (TD-007).
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
from oraculo.domain.hierarchy import PATENTES, CargoInstitucional
from oraculo.domain.permissions import Acao
from oraculo.repositories import auditoria as repo_auditoria
from oraculo.repositories import membros as repo_membros
from oraculo.services import vinculo_service
from oraculo.services.notificacao_service import NotificacaoService


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
            "Concedidos por um Administrador, acumuláveis com qualquer patente."
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
        name="cargo-institucional",
        description="Concede ou revoga Conselheiro/Administrador (Admin).",
    )
    @app_commands.describe(
        membro="Membro alvo.",
        cargo="Cargo institucional.",
        operacao="Conceder ou revogar.",
        motivo="Justificativa (auditada).",
    )
    @app_commands.choices(
        cargo=[app_commands.Choice(name=c.nome, value=c.value) for c in CargoInstitucional],
        operacao=[
            app_commands.Choice(name="Conceder", value="conceder"),
            app_commands.Choice(name="Revogar", value="revogar"),
        ],
    )
    @requer(Acao.DEFINIR_CARGO_INSTITUCIONAL, efemero=True)
    async def cargo_institucional(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        cargo: app_commands.Choice[str],
        operacao: app_commands.Choice[str],
        motivo: app_commands.Range[str, 3, 500],
    ) -> None:
        destino = CargoInstitucional(cargo.value)
        ativo = operacao.value == "conceder"

        async with sessao() as session:
            autor = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            alvo = await repo_membros.obter_ou_criar_por_discord(
                session, discord_id=membro.id, nome_exibicao=membro.display_name
            )
            resultado = await self.bot.container.cargos.definir(
                session,
                membro=alvo,
                cargo=destino,
                ativo=ativo,
                motivo=motivo,
                autor=autor,
                origem=OrigemAcao.DISCORD,
                guild_id=interaction.guild_id,
            )

        verbo = "concedido a" if ativo else "revogado de"
        aviso = "" if resultado.sincronizado else "\n⚠️ Papel não sincronizado no Discord."
        await interaction.followup.send(
            f"Cargo **{destino.nome}** {verbo} **{membro.display_name}**.{aviso}",
            ephemeral=True,
        )

    @app_commands.command(
        name="confirmar-patente",
        description="Libera a patente que o XP determina, retida pela importação (Admin).",
    )
    @app_commands.describe(membro="Membro com patente pendente de confirmação.")
    @requer(Acao.CONFIRMAR_PATENTE, efemero=True)
    async def confirmar_patente(
        self, interaction: discord.Interaction, membro: discord.Member
    ) -> None:
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
            resultado = await container.promocoes.confirmar(
                session,
                alvo,
                autor_descricao=autor.nome_exibicao,
                origem=OrigemAcao.DISCORD,
                guild_id=interaction.guild_id,
            )
            xp = alvo.xp

        if not resultado.promovido:
            await interaction.followup.send(
                f"**{membro.display_name}** já está na patente que o XP determina "
                f"(**{resultado.patente_atual.nome}**). Nada a confirmar.",
                ephemeral=True,
            )
            return

        await container.notificacoes.enviar(
            NotificacaoService.promocao(
                nome=membro.display_name,
                cargo_anterior=resultado.patente_anterior.nome,
                cargo_novo=resultado.patente_atual.nome,
                xp=xp,
                discord_id=membro.id,
            )
        )
        aviso = "" if resultado.sincronizado else "\n⚠️ Papel não sincronizado no Discord."
        await interaction.followup.send(
            f"Patente de **{membro.display_name}** confirmada: "
            f"**{resultado.patente_atual.nome}**.{aviso}",
            ephemeral=True,
        )

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
            alvo = await repo_membros.obter_ou_criar_por_discord(
                session, discord_id=membro.id, nome_exibicao=membro.display_name
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
            f"`{id_externo}`. XP e patente acompanham a próxima sincronização.",
            ephemeral=True,
        )

    @app_commands.command(
        name="migrar-para-clube",
        description="Na filiação, leva o saldo da Comunidade para o Clube (Admin).",
    )
    @app_commands.describe(membro="Novo membro do Clube, já vinculado à plataforma.")
    @requer(Acao.MIGRAR_SALDO_COMUNIDADE, efemero=True)
    async def migrar_para_clube(
        self, interaction: discord.Interaction, membro: discord.Member
    ) -> None:
        async with sessao() as session:
            autor = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            alvo = await repo_membros.obter_ou_criar_por_discord(
                session, discord_id=membro.id, nome_exibicao=membro.display_name
            )
            resultado = await self.bot.container.filiacao.migrar_saldo_para_clube(
                session,
                membro=alvo,
                autor=autor,
                origem=OrigemAcao.DISCORD,
                guild_id=interaction.guild_id,
            )

        await interaction.followup.send(
            f"Saldo da Comunidade de **{membro.display_name}** migrado para o Clube: "
            f"**{resultado.valor:,} Dracmas** na plataforma.".replace(",", "."),
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
