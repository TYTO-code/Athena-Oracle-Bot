"""Gerente dos projetos no Discord (docs/GERENTE_PLANO.md, fases 3 e 6).

* Entrega: um laço busca na TYTO.club-API as mensagens prontas (lembretes, alertas, destaque de
  missões, boas-vindas, resumo semanal) e as entrega por DM ou no canal configurado.
* Comandos fixos: `/meus-prazos`, `/minhas-tasks`, `/status`, `/missoes` — respondidos por código,
  sem IA, com dados já filtrados pela API conforme o cargo de quem pergunta.

Sem `ORACULO_TYTO_API_URL`/`ORACULO_TYTO_API_SERVICE_KEY` o cog fica inerte: os comandos
avisam que o gerente não está configurado e o laço não roda.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks

from oraculo.bot import embeds
from oraculo.bot.permissions import requer
from oraculo.domain.gerente_respostas import (
    formatar_meus_prazos,
    formatar_minhas_tasks,
    formatar_missoes,
    formatar_status,
)
from oraculo.domain.permissions import Acao
from oraculo.domain.roteador_perguntas import Rota
from oraculo.integrations.gerente_api import FonteGerente, criar_fonte_gerente
from oraculo.logging_config import get_logger
from oraculo.observabilidade import contar_rota, medir_job
from oraculo.services.gerente_entrega_service import GerenteEntregaService, ResultadoEnvio

log = get_logger(__name__)

LIMITE_DM = 1900
"""A DM do Discord aceita 2000 caracteres; a margem cobre quebras de linha."""


class RemetenteDiscord:
    def __init__(self, bot: commands.Bot, canal_missoes_id: int | None) -> None:
        self._bot = bot
        self._canal_id = canal_missoes_id

    async def enviar_dm(self, discord_id: int, texto: str) -> str:
        try:
            usuario = self._bot.get_user(discord_id) or await self._bot.fetch_user(discord_id)
            await usuario.send(texto[:LIMITE_DM])
            return ResultadoEnvio.ENTREGUE
        except (discord.Forbidden, discord.NotFound):
            return ResultadoEnvio.RECUSADO
        except discord.HTTPException as exc:
            log.warning("Gerente: DM falhou (%s); volta para a fila.", exc)
            return ResultadoEnvio.TENTAR_DE_NOVO

    async def publicar_no_canal(self, texto: str) -> str:
        if self._canal_id is None:
            return ResultadoEnvio.RECUSADO
        canal = self._bot.get_channel(self._canal_id)
        if not isinstance(canal, discord.abc.Messageable):
            log.warning("Gerente: canal de missões %s não encontrado.", self._canal_id)
            return ResultadoEnvio.RECUSADO
        try:
            # Destaque é convite, não aviso geral: nenhuma menção é permitida.
            await canal.send(texto[:LIMITE_DM], allowed_mentions=discord.AllowedMentions.none())
            return ResultadoEnvio.ENTREGUE
        except discord.HTTPException as exc:
            log.warning("Gerente: publicação no canal falhou (%s).", exc)
            return ResultadoEnvio.TENTAR_DE_NOVO


class GerenteCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        cfg = bot.settings  # type: ignore[attr-defined]
        self.fonte: FonteGerente | None = criar_fonte_gerente(cfg)
        self.entrega: GerenteEntregaService | None = (
            GerenteEntregaService(self.fonte, RemetenteDiscord(bot, cfg.gerente_canal_missoes_id))
            if self.fonte is not None
            else None
        )
        minutos = cfg.gerente_entrega_intervalo_minutos
        if self.entrega is not None and minutos > 0:
            self.laco_entrega.change_interval(minutes=minutos)
            self.laco_entrega.start()

    async def cog_unload(self) -> None:
        self.laco_entrega.cancel()

    @tasks.loop(minutes=5)
    async def laco_entrega(self) -> None:
        if self.entrega is None:
            return
        try:
            async with medir_job("gerente_entrega"):
                relatorio = await self.entrega.entregar_pendentes()
        except Exception:  # noqa: BLE001 — o laço não pode morrer por uma falha pontual
            log.exception("Gerente: falha no ciclo de entrega")
            return
        if relatorio.entregues or relatorio.recusadas or relatorio.adiadas:
            log.info(
                "Gerente: %d entregues, %d recusadas, %d adiadas.",
                relatorio.entregues,
                relatorio.recusadas,
                relatorio.adiadas,
            )

    @laco_entrega.before_loop
    async def _esperar_conexao(self) -> None:
        await self.bot.wait_until_ready()

    # -- Comandos fixos (sem IA) -----------------------------------------------

    async def _consultar(
        self, interaction: discord.Interaction, recurso: str, **params: str
    ) -> dict | None:
        if self.fonte is None:
            await interaction.followup.send(
                embed=embeds.erro("O gerente dos projetos não está configurado neste servidor."),
                ephemeral=True,
            )
            return None
        return await self.fonte.consultar(recurso, interaction.user.id, **params)

    async def _responder(
        self, interaction: discord.Interaction, titulo: str, texto: str, rodape: str = ""
    ) -> None:
        embed = discord.Embed(
            title=titulo, description=texto[:4000], color=discord.Color.dark_teal()
        )
        if rodape:
            embed.set_footer(text=rodape)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @property
    def disponivel(self) -> bool:
        return self.fonte is not None

    async def responder_rota(self, interaction: discord.Interaction, rota: Rota) -> None:
        """Resposta do `/perguntar` desviada para um comando fixo (sem IA). Já adiada pelo
        `/perguntar`; a permissão de consultar o gerente vale para qualquer membro."""
        rodape = f"Resposta direta, sem IA. Atalho: /{rota.comando}"
        if rota.comando == "status":
            dados = await self._consultar(interaction, "status", projeto=rota.projeto)
            titulo, texto = "📊 Status do projeto", formatar_status(dados or {})
        elif rota.comando == "missoes":
            dados = await self._consultar(interaction, "missoes")
            titulo, texto = "🦉 Missões abertas", formatar_missoes(dados or {})
        else:
            dados = await self._consultar(interaction, "eu")
            if rota.comando == "meus-prazos":
                titulo, texto = "📅 Meus prazos", formatar_meus_prazos(dados or {})
            else:
                titulo, texto = "🗂️ Minhas tasks", formatar_minhas_tasks(dados or {})
        if dados is not None:
            contar_rota(rota.comando)
            await self._responder(interaction, titulo, texto, rodape)

    @app_commands.command(
        name="meus-prazos", description="Seus próximos prazos nas tasks dos projetos."
    )
    @requer(Acao.CONSULTAR_GERENTE, efemero=True)
    async def meus_prazos(self, interaction: discord.Interaction) -> None:
        dados = await self._consultar(interaction, "eu")
        if dados is not None:
            await self._responder(interaction, "📅 Meus prazos", formatar_meus_prazos(dados))

    @app_commands.command(name="minhas-tasks", description="Suas tasks abertas nos projetos.")
    @requer(Acao.CONSULTAR_GERENTE, efemero=True)
    async def minhas_tasks(self, interaction: discord.Interaction) -> None:
        dados = await self._consultar(interaction, "eu")
        if dados is not None:
            await self._responder(interaction, "🗂️ Minhas tasks", formatar_minhas_tasks(dados))

    @app_commands.command(
        name="status", description="Situação de um projeto (conforme o seu acesso)."
    )
    @app_commands.describe(projeto="Nome do projeto")
    @requer(Acao.CONSULTAR_GERENTE, efemero=True)
    async def status(
        self, interaction: discord.Interaction, projeto: app_commands.Range[str, 2, 80]
    ) -> None:
        dados = await self._consultar(interaction, "status", projeto=projeto)
        if dados is not None:
            await self._responder(interaction, "📊 Status do projeto", formatar_status(dados))

    @app_commands.command(name="missoes", description="Missões abertas esperando alguém.")
    @requer(Acao.CONSULTAR_GERENTE, efemero=True)
    async def missoes(self, interaction: discord.Interaction) -> None:
        dados = await self._consultar(interaction, "missoes")
        if dados is not None:
            await self._responder(interaction, "🦉 Missões abertas", formatar_missoes(dados))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GerenteCog(bot))
