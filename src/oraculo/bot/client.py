"""Cliente Discord do Bot Oráculo — ADR-001 (discord.py + cogs).

Responsabilidades: carregar cogs, sincronizar slash commands, expor o container
de serviços e traduzir erros de domínio em respostas amigáveis.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.bot.permissions import PermissaoInsuficiente
from oraculo.bot.role_sync import SincronizadorDiscord
from oraculo.config import Settings, get_settings
from oraculo.container import Container
from oraculo.domain.errors import BusinessRuleError, OraculoError
from oraculo.logging_config import get_logger

log = get_logger(__name__)

COGS = (
    "oraculo.bot.cogs.ajuda",
    "oraculo.bot.cogs.perfil",
    "oraculo.bot.cogs.ranking",
    "oraculo.bot.cogs.xp",
    "oraculo.bot.cogs.agenda",
    "oraculo.bot.cogs.admin",
    "oraculo.bot.cogs.comunidade",
    "oraculo.bot.cogs.vinculo",
    "oraculo.bot.cogs.pergunta",
    "oraculo.bot.cogs.comunicados",
)


class OraculoBot(commands.Bot):
    """Bot do Clube TYTO."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

        intents = discord.Intents.default()
        # `members` é obrigatório para ler e alterar cargos (RF-006/RN-001).
        intents.members = True
        intents.message_content = False

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )

        # O sincronizador precisa do próprio bot: por isso o container é criado
        # aqui, e não no módulo de composição.
        self.container = Container.criar(
            self.settings, sincronizador_cargos=SincronizadorDiscord(self)
        )
        self.tree.on_error = self._on_app_command_error

    # -- Ciclo de vida -----------------------------------------------------

    async def setup_hook(self) -> None:
        for cog in COGS:
            await self.load_extension(cog)
            log.info("Cog carregado: %s", cog)

        from oraculo.bot.notificador import CanalDiscord

        self.container.notificacoes.registrar_canal(CanalDiscord(self))

        if self.settings.discord_guild_ids:
            for guild_id in self.settings.discord_guild_ids:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                comandos = await self.tree.sync(guild=guild)
                log.info("%d comandos sincronizados no servidor %s", len(comandos), guild_id)
        else:
            comandos = await self.tree.sync()
            log.info("%d comandos sincronizados globalmente", len(comandos))

    async def on_ready(self) -> None:
        log.info("Conectado como %s (%d servidores)", self.user, len(self.guilds))
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="o Clube TYTO | /perfil"
            )
        )

    async def close(self) -> None:
        await self.container.fechar()
        await super().close()

    # -- Erros -------------------------------------------------------------

    async def _on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Erros de negócio viram mensagem; o resto vira log + aviso genérico."""
        original = getattr(error, "original", error)

        if isinstance(error, PermissaoInsuficiente):
            embed = embeds.erro(str(error), titulo="Permissão insuficiente (RN-008)")
        elif isinstance(original, BusinessRuleError):
            embed = embeds.erro(str(original), titulo=f"Regra {original.regra}")
        elif isinstance(original, OraculoError):
            embed = embeds.erro(str(original))
        elif isinstance(error, app_commands.CommandOnCooldown):
            embed = embeds.erro(f"Aguarde {error.retry_after:.0f}s antes de tentar de novo.")
        else:
            log.exception("Erro não tratado no comando", exc_info=original)
            embed = embeds.erro(
                "Erro inesperado. A equipe foi notificada pelos logs.", titulo="Falha interna"
            )

        await self._responder(interaction, embed)

    @staticmethod
    async def _responder(interaction: discord.Interaction, embed: discord.Embed) -> None:
        """Responde ao erro respeitando o estado da interação.

        Como `requer` confirma a interação antes de checar permissão, o caminho
        normal aqui é **editar** a resposta adiada — se apenas enviássemos um
        followup, o "pensando..." ficaria pendurado no chat.
        """
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.HTTPException:  # pragma: no cover - interação expirada
                log.warning("Não foi possível responder à interação %s", interaction.id)


def criar_bot(settings: Settings | None = None) -> OraculoBot:
    return OraculoBot(settings)
