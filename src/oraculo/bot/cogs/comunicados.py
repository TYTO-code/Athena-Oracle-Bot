"""Comunicados oficiais — RF-015 / RN-018.

`/comunicar` publica agora; `/agendar-comunicado` deixa marcado para depois.
Quem realmente publica o que está programado é o ciclo `publicar_programados`,
dentro deste cog: roda no processo do próprio bot (mesma escolha do backup e da
sincronização — ADR-001, um container só), e só começa depois do `on_ready`,
porque antes disso o cliente não consegue resolver canal nenhum.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks

from oraculo.bot import embeds
from oraculo.bot.comunicador import ComunicadorDiscord
from oraculo.bot.datas import interpretar_data
from oraculo.bot.permissions import requer
from oraculo.db.base import sessao
from oraculo.db.models import StatusComunicado, TipoMencao
from oraculo.domain.permissions import Acao
from oraculo.logging_config import get_logger
from oraculo.repositories import comunicados as repo_comunicados
from oraculo.repositories import membros as repo_membros
from oraculo.services.comunicado_service import (
    ComunicadoService,
    DataDeComunicadoInvalidaError,
    ResultadoCiclo,
)

log = get_logger(__name__)

ESCOLHAS_MENCAO = [
    app_commands.Choice(name="Sem menção (padrão)", value=TipoMencao.NENHUMA.value),
    app_commands.Choice(name="@here — quem está online", value=TipoMencao.AQUI.value),
    app_commands.Choice(name="@everyone — todo o servidor", value=TipoMencao.TODOS.value),
]

ESCOLHAS_STATUS = [
    app_commands.Choice(name="Programados", value=StatusComunicado.AGENDADO.value),
    app_commands.Choice(name="Publicados", value=StatusComunicado.PUBLICADO.value),
    app_commands.Choice(name="Cancelados", value=StatusComunicado.CANCELADO.value),
    app_commands.Choice(name="Com falha", value=StatusComunicado.FALHOU.value),
]


def texto_do_corpo(bruto: str) -> str:
    """Slash command não aceita Enter no campo de texto — `\\n` vira quebra de linha."""
    return bruto.replace("\\n", "\n").strip()


class ComunicadosCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._servico: ComunicadoService = bot.container.comunicados

    async def cog_unload(self) -> None:
        self.publicar_programados.cancel()

    # -- Ciclo de publicação ----------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Liga o ciclo só quando há cliente pronto (e só uma vez por sessão)."""
        intervalo = self.bot.settings.comunicados_intervalo_segundos
        if intervalo <= 0:
            log.info("Publicação programada de comunicados desligada (intervalo = 0).")
            return
        if self.publicar_programados.is_running():
            return
        self._servico.registrar_publicador(ComunicadorDiscord(self.bot))
        self.publicar_programados.change_interval(seconds=intervalo)
        self.publicar_programados.start()
        log.info("Publicador de comunicados ativo (a cada %ds).", intervalo)

    @tasks.loop(seconds=60)
    async def publicar_programados(self) -> None:
        # Durante uma reconexão o cliente não resolve canal nenhum: a volta do
        # ciclo é pulada inteira, e o comunicado espera a próxima — ele continua
        # AGENDADO no banco, que é o estado certo para tentar de novo.
        if not self.bot.is_ready():
            return

        try:
            async with sessao() as session:
                resultado = await self._servico.publicar_pendentes(session)
        except Exception:  # noqa: BLE001 — um ciclo ruim não pode matar o loop
            log.exception("Falha no ciclo de publicação de comunicados")
            return

        if resultado.houve_trabalho:
            log.info(
                "Ciclo de comunicados: %d publicados, %d expirados, %d falhados, "
                "%d reagendados, %d órfãos.",
                len(resultado.publicados),
                len(resultado.expirados),
                len(resultado.falhados),
                len(resultado.reagendados),
                len(resultado.orfaos),
            )
        await self._avisar_sobre_falhas(resultado)

    async def _avisar_sobre_falhas(self, resultado: ResultadoCiclo) -> None:
        """Comunicado que não saiu precisa aparecer para alguém (RF-012)."""
        problemas = [*resultado.expirados, *resultado.falhados, *resultado.orfaos]
        if not problemas:
            return
        async with sessao() as session:
            for identificador in problemas:
                comunicado = await repo_comunicados.obter(session, identificador)
                await self.bot.container.notificacoes.enviar(
                    ComunicadoService.aviso_de_falha(comunicado)
                )

    # -- Comandos ----------------------------------------------------------

    @app_commands.command(
        name="comunicar", description="Publica um comunicado oficial num canal (Lorde+)."
    )
    @app_commands.describe(
        titulo="Assunto do comunicado.",
        corpo="Texto do aviso. Use \\n para quebrar linha.",
        canal="Onde publicar (padrão: canal de comunicados configurado).",
        mencao="Quem notificar. @here/@everyone exigem Conselheiro+.",
    )
    @app_commands.choices(mencao=ESCOLHAS_MENCAO)
    @requer(Acao.PUBLICAR_COMUNICADO, efemero=True)
    async def comunicar(
        self,
        interaction: discord.Interaction,
        titulo: app_commands.Range[str, 3, 160],
        corpo: app_commands.Range[str, 3, 3900],
        canal: discord.TextChannel | None = None,
        mencao: app_commands.Choice[str] | None = None,
    ) -> None:
        async with sessao() as session:
            autor = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            comunicado = await self._servico.publicar_agora(
                session,
                titulo=titulo,
                corpo=texto_do_corpo(corpo),
                canal_id=canal.id if canal else None,
                autor=autor,
                mencao=TipoMencao(mencao.value) if mencao else TipoMencao.NENHUMA,
                guild_id=interaction.guild_id,
                canal_padrao=self.bot.settings.discord_comunicados_channel_id,
            )
            estado = StatusComunicado(comunicado.status)
            identificador, canal_id, erro = comunicado.id, comunicado.canal_id, comunicado.erro

        if estado is StatusComunicado.PUBLICADO:
            await interaction.followup.send(
                embed=embeds.sucesso(
                    f"Comunicado `#{identificador}` publicado em <#{canal_id}>.",
                    titulo="📢 Comunicado publicado",
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=embeds.erro(
                f"Não consegui publicar agora em <#{canal_id}>: {erro}\n"
                "O comunicado ficou na fila e será tentado de novo automaticamente. "
                f"Acompanhe em `/comunicados` (`#{identificador}`).",
                titulo="Publicação adiada",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="agendar-comunicado",
        description="Programa um comunicado para publicar mais tarde (Lorde+).",
    )
    @app_commands.describe(
        titulo="Assunto do comunicado.",
        corpo="Texto do aviso. Use \\n para quebrar linha.",
        quando="Data e hora no formato DD/MM/AAAA HH:MM.",
        canal="Onde publicar (padrão: canal de comunicados configurado).",
        mencao="Quem notificar. @here/@everyone exigem Conselheiro+.",
    )
    @app_commands.choices(mencao=ESCOLHAS_MENCAO)
    @requer(Acao.PUBLICAR_COMUNICADO, efemero=True)
    async def agendar_comunicado(
        self,
        interaction: discord.Interaction,
        titulo: app_commands.Range[str, 3, 160],
        corpo: app_commands.Range[str, 3, 3900],
        quando: str,
        canal: discord.TextChannel | None = None,
        mencao: app_commands.Choice[str] | None = None,
    ) -> None:
        publicar_em = interpretar_data(quando, excecao=DataDeComunicadoInvalidaError)

        async with sessao() as session:
            autor = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            comunicado = await self._servico.programar(
                session,
                titulo=titulo,
                corpo=texto_do_corpo(corpo),
                canal_id=canal.id if canal else None,
                autor=autor,
                publicar_em=publicar_em,
                mencao=TipoMencao(mencao.value) if mencao else TipoMencao.NENHUMA,
                guild_id=interaction.guild_id,
                canal_padrao=self.bot.settings.discord_comunicados_channel_id,
            )
            identificador, canal_id = comunicado.id, comunicado.canal_id

        await interaction.followup.send(
            embed=embeds.sucesso(
                f"**{titulo}** sai em <t:{int(publicar_em.timestamp())}:F> "
                f"(<t:{int(publicar_em.timestamp())}:R>) em <#{canal_id}>.\n"
                f"Para desmarcar: `/cancelar-comunicado identificador:{identificador}`.",
                titulo="🗓️ Comunicado programado",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="comunicados", description="Lista os comunicados programados e os já publicados."
    )
    @app_commands.describe(status="Filtra pela situação (padrão: todos).")
    @app_commands.choices(status=ESCOLHAS_STATUS)
    @requer(Acao.PUBLICAR_COMUNICADO, efemero=True)
    async def listar(
        self,
        interaction: discord.Interaction,
        status: app_commands.Choice[str] | None = None,
    ) -> None:
        filtro = StatusComunicado(status.value) if status else None

        async with sessao() as session:
            encontrados = await repo_comunicados.listar(
                session, status=filtro, guild_id=interaction.guild_id, limite=10
            )
            embed = embeds.lista_comunicados(encontrados)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="cancelar-comunicado",
        description="Cancela um comunicado ainda não publicado (RN-010).",
    )
    @app_commands.describe(
        identificador="ID exibido em /comunicados.", motivo="Motivo do cancelamento."
    )
    @requer(Acao.PUBLICAR_COMUNICADO, efemero=True)
    async def cancelar(
        self,
        interaction: discord.Interaction,
        identificador: int,
        motivo: app_commands.Range[str, 3, 500],
    ) -> None:
        async with sessao() as session:
            comunicado = await repo_comunicados.obter(session, identificador)
            solicitante = await repo_membros.obter_ou_criar_por_discord(
                session,
                discord_id=interaction.user.id,
                nome_exibicao=interaction.user.display_name,
            )
            await self._servico.cancelar(
                session, comunicado=comunicado, solicitante=solicitante, motivo=motivo
            )
            titulo = comunicado.titulo

        await interaction.followup.send(
            embed=embeds.sucesso(
                f"**{titulo}** não será publicado.\nMotivo: {motivo}",
                titulo="🗑️ Comunicado cancelado",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ComunicadosCog(bot))
