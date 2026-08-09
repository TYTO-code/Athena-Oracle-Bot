"""Sincronização de cargos com o Discord — RF-006 / RN-001 / RN-003 / TD-005.

Correção direta do defeito do legado: a função de cargo atribuía o novo papel
sem remover os anteriores, permitindo que um membro acumulasse "Cavalaria" e
"Lorde" ao mesmo tempo. Aqui a remoção vem **antes** da atribuição e cobre
todos os nomes de cargo do catálogo TYTO.
"""

from __future__ import annotations

import discord

from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.domain.hierarchy import Cargo, nomes_de_cargos_discord
from oraculo.logging_config import get_logger

log = get_logger(__name__)


class SincronizadorDiscord:
    """Implementa `SincronizadorCargos` sobre a API do Discord."""

    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot

    async def sincronizar(
        self, *, discord_id: int, cargo: Cargo, guild_id: int | None = None
    ) -> None:
        guilds = self._guilds_alvo(guild_id)
        if not guilds:
            raise IntegracaoIndisponivelError("Discord", "nenhum servidor disponível")

        for guild in guilds:
            membro = guild.get_member(discord_id)
            if membro is None:
                try:
                    membro = await guild.fetch_member(discord_id)
                except discord.NotFound:
                    log.debug("Membro %s não está em %s; ignorando.", discord_id, guild.id)
                    continue

            gerenciados = nomes_de_cargos_discord()
            a_remover = [papel for papel in membro.roles if papel.name in gerenciados]
            destino = discord.utils.get(guild.roles, name=cargo.nome)

            if destino is None:
                raise IntegracaoIndisponivelError(
                    "Discord",
                    f"cargo '{cargo.nome}' não existe no servidor {guild.name}; "
                    "crie os cargos TYTO ou rode `/oraculo-verificar-cargos`.",
                )

            # RN-001 / RN-003 — remover TODOS os cargos TYTO antes de atribuir.
            a_remover = [papel for papel in a_remover if papel.id != destino.id]
            if a_remover:
                await membro.remove_roles(*a_remover, reason="Cargo único TYTO (RN-001)")
                log.info(
                    "Removidos %s de %s em %s",
                    [p.name for p in a_remover],
                    discord_id,
                    guild.id,
                )

            if destino not in membro.roles:
                await membro.add_roles(destino, reason="Promoção automática (RN-003)")
                log.info("Atribuído '%s' a %s em %s", destino.name, discord_id, guild.id)

    def _guilds_alvo(self, guild_id: int | None) -> list[discord.Guild]:
        if guild_id is not None:
            guild = self._bot.get_guild(guild_id)
            return [guild] if guild else []
        return list(self._bot.guilds)


async def cargos_faltantes(guild: discord.Guild) -> list[str]:
    """Cargos TYTO ausentes no servidor — usado no diagnóstico de admin."""
    existentes = {papel.name for papel in guild.roles}
    return sorted(nomes_de_cargos_discord() - existentes)
