"""Reuniões, eventos oficiais e RSVP — UC-004, UC-005, UC-006 / US-301, US-303, US-304.

Os botões de RSVP são itens dinâmicos (`DynamicItem`): o `custom_id` carrega o
id do agendamento, então continuam funcionando depois de reiniciar o bot, sem
precisar manter estado em memória.
"""

from __future__ import annotations

import re
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot.datas import interpretar_data
from oraculo.bot.permissions import requer
from oraculo.db.base import sessao
from oraculo.db.models import OrigemAcao, StatusPresenca, TipoAgendamento
from oraculo.domain.permissions import Acao
from oraculo.logging_config import get_logger
from oraculo.repositories import agenda as repo_agenda
from oraculo.repositories import membros as repo_membros
from oraculo.services.notificacao_service import NotificacaoService

log = get_logger(__name__)

ROTULOS_RSVP = {
    StatusPresenca.CONFIRMADO: ("✅ Confirmar", discord.ButtonStyle.success),
    StatusPresenca.RECUSADO: ("❌ Recusar", discord.ButtonStyle.danger),
    StatusPresenca.PENDENTE: ("🤔 Pendente", discord.ButtonStyle.secondary),
}


class BotaoRsvp(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"rsvp:(?P<agendamento>\d+):(?P<status>\w+)",
):
    """Botão de presença persistente — UC-006."""

    def __init__(self, agendamento_id: int, status: StatusPresenca) -> None:
        self.agendamento_id = agendamento_id
        self.status = status
        rotulo, estilo = ROTULOS_RSVP[status]
        super().__init__(
            discord.ui.Button(
                label=rotulo,
                style=estilo,
                custom_id=f"rsvp:{agendamento_id}:{status.value}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> BotaoRsvp:
        return cls(int(match["agendamento"]), StatusPresenca(match["status"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        container = interaction.client.container

        async with sessao() as session:
            agendamento = await repo_agenda.obter(session, self.agendamento_id)
            membro = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            await container.agenda.responder_rsvp(
                session,
                agendamento=agendamento,
                membro=membro,
                status=self.status,
                origem=OrigemAcao.DISCORD,
            )
            resumo = await container.agenda.resumo_presencas(session, self.agendamento_id)
            titulo = agendamento.titulo

        await interaction.followup.send(
            f"Presença registrada em **{titulo}**: **{self.status.value}**.\n"
            f"✅ {resumo['confirmado']} · ❌ {resumo['recusado']} · 🤔 {resumo['pendente']}",
            ephemeral=True,
        )


class PainelRsvp(discord.ui.View):
    """Conjunto de botões anexado ao anúncio do agendamento."""

    def __init__(self, agendamento_id: int) -> None:
        super().__init__(timeout=None)
        for status in (
            StatusPresenca.CONFIRMADO,
            StatusPresenca.RECUSADO,
            StatusPresenca.PENDENTE,
        ):
            self.add_item(BotaoRsvp(agendamento_id, status))


class AgendaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -- Criação -----------------------------------------------------------

    @app_commands.command(
        name="criar-reuniao", description="Cria uma reunião e sincroniza a agenda (Cavalaria+)."
    )
    @app_commands.describe(
        titulo="Assunto da reunião.",
        inicio="Início no formato DD/MM/AAAA HH:MM.",
        duracao_minutos="Duração prevista em minutos.",
        local="Local ou canal de voz.",
        descricao="Pauta ou detalhes.",
    )
    @requer(Acao.CRIAR_REUNIAO)
    async def criar_reuniao(
        self,
        interaction: discord.Interaction,
        titulo: app_commands.Range[str, 3, 160],
        inicio: str,
        duracao_minutos: app_commands.Range[int, 15, 1440] = 60,
        local: str | None = None,
        descricao: str | None = None,
    ) -> None:
        await self._criar(
            interaction,
            TipoAgendamento.REUNIAO,
            titulo,
            inicio,
            duracao_minutos,
            local,
            descricao,
        )

    @app_commands.command(
        name="criar-evento", description="Cria um evento oficial do clube (Lorde+)."
    )
    @app_commands.describe(
        titulo="Nome do evento.",
        inicio="Início no formato DD/MM/AAAA HH:MM.",
        duracao_minutos="Duração prevista em minutos.",
        local="Local do evento.",
        descricao="Detalhes do evento.",
    )
    @requer(Acao.CRIAR_EVENTO)
    async def criar_evento(
        self,
        interaction: discord.Interaction,
        titulo: app_commands.Range[str, 3, 160],
        inicio: str,
        duracao_minutos: app_commands.Range[int, 15, 10_080] = 120,
        local: str | None = None,
        descricao: str | None = None,
    ) -> None:
        await self._criar(
            interaction,
            TipoAgendamento.EVENTO,
            titulo,
            inicio,
            duracao_minutos,
            local,
            descricao,
        )

    # -- Consulta e cancelamento ------------------------------------------

    @app_commands.command(name="agenda", description="Próximas reuniões e eventos do clube.")
    @app_commands.describe(tipo="Filtra por tipo de agendamento.")
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Reuniões", value="reuniao"),
            app_commands.Choice(name="Eventos oficiais", value="evento"),
        ]
    )
    @requer(Acao.VER_PERFIL)
    async def agenda(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str] | None = None,
    ) -> None:
        filtro = TipoAgendamento(tipo.value) if tipo else None

        async with sessao() as session:
            proximos = await repo_agenda.listar_proximos(
                session, tipo=filtro, guild_id=interaction.guild_id, limite=10
            )
            linhas = [
                f"**{item.titulo}** · {TipoAgendamento(item.tipo).value} · "
                f"<t:{int(item.inicio_em.timestamp())}:F> · `#{item.id}`"
                for item in proximos
            ]

        embed = discord.Embed(
            title="📅 Próximos compromissos",
            description="\n".join(linhas) or "Nada agendado por enquanto.",
            color=discord.Color.blurple(),
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="cancelar-agendamento", description="Cancela uma reunião ou evento (RN-010)."
    )
    @app_commands.describe(identificador="ID exibido em /agenda.", motivo="Motivo do cancelamento.")
    @requer(Acao.GERIR_REUNIAO)
    async def cancelar(
        self,
        interaction: discord.Interaction,
        identificador: int,
        motivo: app_commands.Range[str, 3, 500],
    ) -> None:
        async with sessao() as session:
            agendamento = await repo_agenda.obter(session, identificador)
            solicitante = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            await self.bot.container.agenda.cancelar(
                session, agendamento=agendamento, solicitante=solicitante, motivo=motivo
            )
            titulo = agendamento.titulo

        await interaction.followup.send(
            embed=discord.Embed(
                title="🗑️ Agendamento cancelado",
                description=f"**{titulo}** foi cancelado.\nMotivo: {motivo}",
                color=discord.Color.orange(),
            )
        )

    # -- Interno -----------------------------------------------------------

    async def _criar(
        self,
        interaction: discord.Interaction,
        tipo: TipoAgendamento,
        titulo: str,
        inicio: str,
        duracao_minutos: int,
        local: str | None,
        descricao: str | None,
    ) -> None:
        inicio_em = interpretar_data(inicio)
        fim_em = inicio_em + timedelta(minutes=duracao_minutos)
        container = self.bot.container

        async with sessao() as session:
            organizador = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            resultado = await container.agenda.criar(
                session,
                tipo=tipo,
                titulo=titulo,
                inicio_em=inicio_em,
                organizador=organizador,
                descricao=descricao,
                local=local,
                fim_em=fim_em,
                guild_id=interaction.guild_id,
            )
            agendamento_id = resultado.agendamento.id
            sincronizado = resultado.sincronizado_google
            organizador_nome = organizador.nome_exibicao

        embed = discord.Embed(
            title=(
                f"📅 {'Reunião' if tipo is TipoAgendamento.REUNIAO else 'Evento oficial'}: {titulo}"
            ),
            description=descricao or "Sem descrição.",
            color=discord.Color.green(),
        )
        embed.add_field(name="Quando", value=f"<t:{int(inicio_em.timestamp())}:F>", inline=False)
        embed.add_field(name="Local", value=local or "A definir", inline=True)
        embed.add_field(name="Organizador", value=organizador_nome, inline=True)
        embed.add_field(
            name="Google Agenda",
            value="Sincronizado ✅" if sincronizado else "Não sincronizado ⚠️",
            inline=True,
        )
        embed.set_footer(text=f"ID #{agendamento_id} · responda abaixo (UC-006)")

        await interaction.followup.send(embed=embed, view=PainelRsvp(agendamento_id))
        await container.notificacoes.enviar(
            NotificacaoService.agendamento(
                tipo="reunião" if tipo is TipoAgendamento.REUNIAO else "evento",
                titulo=titulo,
                quando=inicio_em.strftime("%d/%m/%Y %H:%M"),
                organizador=organizador_nome,
                guild_id=interaction.guild_id,
            )
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_dynamic_items(BotaoRsvp)
    await bot.add_cog(AgendaCog(bot))
