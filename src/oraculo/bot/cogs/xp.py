"""`/conceder-xp`, `/remover-xp` e `/historico-xp` — UC-001 / RF-003 / US-203, US-205.

O motivo é parâmetro **obrigatório** dos comandos: a RN-005 é aplicada tanto na
interface quanto no serviço, e a auditoria é gravada na mesma transação.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.bot.permissions import requer
from oraculo.db.base import sessao
from oraculo.db.models import OrigemAcao
from oraculo.domain.hierarchy import cargo_por_slug
from oraculo.domain.permissions import Acao
from oraculo.repositories import membros as repo_membros
from oraculo.services.notificacao_service import NotificacaoService
from oraculo.services.xp_service import ResultadoXp


class XpCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="conceder-xp", description="Concede XP a um membro (Conselheiro+).")
    @app_commands.describe(
        membro="Membro que receberá o XP.",
        quantidade="Quantidade de XP (positiva).",
        motivo="Justificativa registrada na auditoria (obrigatório — RN-005).",
    )
    @requer(Acao.CONCEDER_XP)
    async def conceder_xp(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        quantidade: app_commands.Range[int, 1, 100_000],
        motivo: app_commands.Range[str, 3, 500],
    ) -> None:
        await self._movimentar(interaction, membro, quantidade, motivo, conceder=True)

    @app_commands.command(name="remover-xp", description="Remove XP de um membro (Conselheiro+).")
    @app_commands.describe(
        membro="Membro que perderá o XP.",
        quantidade="Quantidade de XP (positiva).",
        motivo="Justificativa registrada na auditoria (obrigatório — RN-005).",
    )
    @requer(Acao.REMOVER_XP)
    async def remover_xp(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        quantidade: app_commands.Range[int, 1, 100_000],
        motivo: app_commands.Range[str, 3, 500],
    ) -> None:
        await self._movimentar(interaction, membro, quantidade, motivo, conceder=False)

    @app_commands.command(
        name="historico-xp", description="Histórico auditável de XP de um membro (Conselheiro+)."
    )
    @app_commands.describe(membro="Membro a auditar.", limite="Quantidade de registros (1 a 25).")
    @requer(Acao.VER_HISTORICO_XP)
    async def historico_xp(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        limite: app_commands.Range[int, 1, 25] = 10,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with sessao() as session:
            autor = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            alvo = await repo_membros.obter_ou_criar_por_discord(
                session, discord_id=membro.id, nome_exibicao=membro.display_name
            )
            movimentacoes = await self.bot.container.xp.historico(
                session,
                membro=alvo,
                solicitante_cargo=cargo_por_slug(autor.cargo_slug),
                limite=limite,
            )
            nome = alvo.nome_exibicao

        await interaction.followup.send(
            embed=embeds.historico_xp(movimentacoes, nome=nome), ephemeral=True
        )

    # -- Interno -----------------------------------------------------------

    async def _movimentar(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        quantidade: int,
        motivo: str,
        *,
        conceder: bool,
    ) -> None:
        await interaction.response.defer()
        container = self.bot.container

        async with sessao() as session:
            autor = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            alvo = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=membro.id,
                nome_exibicao=membro.display_name,
            )
            operacao = container.xp.conceder if conceder else container.xp.remover
            resultado: ResultadoXp = await operacao(
                session,
                membro=alvo,
                quantidade=quantidade,
                motivo=motivo,
                autor=autor,
                origem=OrigemAcao.DISCORD,
                guild_id=interaction.guild_id,
            )
            resumo = self._resumo(resultado, autor_nome=autor.nome_exibicao)

        # Cache e notificações ficam fora da transação (RNF-001 / RF-010).
        await container.ranking.invalidar()
        await self._notificar(resultado, membro, autor_nome=resumo["autor"])
        await interaction.followup.send(embed=resumo["embed"])

    @staticmethod
    def _resumo(resultado: ResultadoXp, *, autor_nome: str) -> dict:
        notificacao = NotificacaoService.movimentacao_xp(
            nome=resultado.membro.nome_exibicao,
            quantidade=resultado.movimentacao.quantidade,
            motivo=resultado.movimentacao.motivo,
            saldo=resultado.saldo_atual,
            autor=autor_nome,
            discord_id=resultado.membro.discord_id,
        )
        embed = embeds.de_notificacao(notificacao)
        if resultado.promovido:
            embed.add_field(
                name="🏛️ Promoção",
                value=(
                    f"{resultado.promocao.cargo_anterior.nome} → "
                    f"**{resultado.promocao.cargo_atual.nome}**"
                    + ("" if resultado.promocao.sincronizado else " (cargo não sincronizado)")
                ),
                inline=False,
            )
        return {"embed": embed, "autor": autor_nome}

    async def _notificar(
        self, resultado: ResultadoXp, membro: discord.Member, *, autor_nome: str
    ) -> None:
        container = self.bot.container
        await container.notificacoes.enviar(
            NotificacaoService.movimentacao_xp(
                nome=resultado.membro.nome_exibicao,
                quantidade=resultado.movimentacao.quantidade,
                motivo=resultado.movimentacao.motivo,
                saldo=resultado.saldo_atual,
                autor=autor_nome,
                discord_id=membro.id,
            )
        )
        if resultado.promovido:
            await container.notificacoes.enviar(
                NotificacaoService.promocao(
                    nome=resultado.membro.nome_exibicao,
                    cargo_anterior=resultado.promocao.cargo_anterior.nome,
                    cargo_novo=resultado.promocao.cargo_atual.nome,
                    xp=resultado.saldo_atual,
                    discord_id=membro.id,
                )
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(XpCog(bot))
