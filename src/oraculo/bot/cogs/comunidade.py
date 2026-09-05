"""`/saldo`, `/extrato-dracmas` e `/doar-dracmas` — camada Comunidade (Aldeão).

RN-011 a RN-015 / RF-013 / RF-014. Deliberadamente **não** usa `bot.permissions.requer(...)`:
aquele decorator resolve o cargo do autor via `repo_membros.obter_ou_criar_por_discord`, que
criaria um `Membro` (Clube) para qualquer pessoa que rodasse um comando — o oposto do que a
camada Comunidade precisa. Estes comandos operam direto sobre `discord_id`, via
`DracmasService`, sem tocar em `Membro` nem em `Cargo` — Aldeão e Membro são eixos
independentes (mesmo princípio de `CARTA_INSTITUCIONAL.md` Art. VIII, aplicado aqui às camadas
de acesso em vez de patente/cargo/função).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.db.base import sessao
from oraculo.services.dracmas_service import ResultadoDracmas
from oraculo.services.notificacao_service import NotificacaoService


class ComunidadeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="saldo", description="Consulta seu saldo de Dracmas na Comunidade.")
    async def saldo(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with sessao() as session:
            aldeao = await self.bot.container.dracmas.saldo_de(session, interaction.user.id)
        await interaction.followup.send(
            embed=embeds.saldo_dracmas(aldeao, nome=interaction.user.display_name), ephemeral=True
        )

    @app_commands.command(
        name="extrato-dracmas", description="Histórico de movimentações de Dracmas (RF-014)."
    )
    @app_commands.describe(limite="Quantidade de registros (1 a 25).")
    async def extrato_dracmas(
        self, interaction: discord.Interaction, limite: app_commands.Range[int, 1, 25] = 10
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with sessao() as session:
            movimentacoes = await self.bot.container.dracmas.extrato_de(
                session, interaction.user.id, limite=limite
            )
        await interaction.followup.send(
            embed=embeds.extrato_dracmas(movimentacoes, nome=interaction.user.display_name),
            ephemeral=True,
        )

    @app_commands.command(
        name="doar-dracmas", description="Doa Dracmas do seu saldo a outra pessoa (DRACMAS.md §2)."
    )
    @app_commands.describe(
        destinatario="Quem recebe a doação.",
        valor="Quantidade de Dracmas (positiva).",
        motivo="Motivo registrado no extrato de ambos (obrigatório).",
    )
    async def doar_dracmas(
        self,
        interaction: discord.Interaction,
        destinatario: discord.Member,
        valor: app_commands.Range[int, 1, 1_000_000],
        motivo: app_commands.Range[str, 3, 500],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if destinatario.id == interaction.user.id:
            await interaction.followup.send(
                embed=embeds.erro("Não é possível doar Dracmas para si mesmo."), ephemeral=True
            )
            return

        container = self.bot.container
        async with sessao() as session:
            resultado_debito, resultado_credito = await container.dracmas.doar(
                session,
                discord_id_origem=interaction.user.id,
                discord_id_destino=destinatario.id,
                valor=valor,
                motivo=motivo,
                autor_descricao=interaction.user.display_name,
            )

        await self._notificar_credito(resultado_credito, destinatario, motivo)

        await interaction.followup.send(
            embed=embeds.saldo_dracmas(resultado_debito.aldeao, nome=interaction.user.display_name),
            ephemeral=True,
        )

    # -- Interno -------------------------------------------------------------

    async def _notificar_credito(
        self, resultado: ResultadoDracmas, destinatario: discord.Member, motivo: str
    ) -> None:
        container = self.bot.container
        await container.notificacoes.enviar(
            NotificacaoService.dracmas_creditado(
                nome=destinatario.display_name,
                valor=resultado.movimentacao.valor,
                motivo=motivo,
                saldo=resultado.saldo_atual,
                discord_id=destinatario.id,
                ingresso_cobrado=resultado.ingresso_cobrado,
            )
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ComunidadeCog(bot))
