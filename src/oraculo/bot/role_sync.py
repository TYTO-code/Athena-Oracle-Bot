"""Sincronização de papéis com o Discord — RF-006 / RN-001 / RN-003 / TD-005 / TD-007.

Dois tipos de papel, tratados de forma diferente de propósito:

* **Patente** (XP.md Art. 2º) — exatamente um por membro (RN-001). A remoção
  de todos os papéis de patente vem **antes** da atribuição do novo: é a
  correção direta do legado, que acumulava cargos.
* **Cargo institucional** (Conselheiro, Administrador) — papel independente,
  adicionado ou removido sozinho, sem tocar no papel de patente.
"""

from __future__ import annotations

import discord

from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.domain.hierarchy import (
    CargoInstitucional,
    Patente,
    nomes_de_cargos_institucionais_discord,
    nomes_de_patentes_discord,
)
from oraculo.logging_config import get_logger

log = get_logger(__name__)


class SincronizadorDiscord:
    """Implementa `SincronizadorCargos` sobre a API do Discord."""

    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot

    async def sincronizar(
        self, *, discord_id: int, patente: Patente, guild_id: int | None = None
    ) -> None:
        for guild, membro in await self._membros_alvo(discord_id, guild_id):
            destino = self._papel(guild, patente.nome)

            # RN-001 / RN-003 — remover TODOS os papéis de patente antes de atribuir.
            gerenciados = nomes_de_patentes_discord()
            a_remover = [
                papel
                for papel in membro.roles
                if papel.name in gerenciados and papel.id != destino.id
            ]
            if a_remover:
                await membro.remove_roles(*a_remover, reason="Patente única TYTO (RN-001)")
                log.info(
                    "Removidos %s de %s em %s",
                    [p.name for p in a_remover],
                    discord_id,
                    guild.id,
                )

            if destino not in membro.roles:
                await membro.add_roles(destino, reason="Promoção de patente (RN-003)")
                log.info("Atribuído '%s' a %s em %s", destino.name, discord_id, guild.id)

    async def definir_cargo_institucional(
        self,
        *,
        discord_id: int,
        cargo: CargoInstitucional,
        ativo: bool,
        guild_id: int | None = None,
    ) -> None:
        for guild, membro in await self._membros_alvo(discord_id, guild_id):
            papel = self._papel(guild, cargo.nome)
            if ativo and papel not in membro.roles:
                await membro.add_roles(papel, reason="Cargo institucional concedido (TD-007)")
            elif not ativo and papel in membro.roles:
                await membro.remove_roles(papel, reason="Cargo institucional revogado (TD-007)")

    async def _membros_alvo(
        self, discord_id: int, guild_id: int | None
    ) -> list[tuple[discord.Guild, discord.Member]]:
        guilds = self._guilds_alvo(guild_id)
        if not guilds:
            raise IntegracaoIndisponivelError("Discord", "nenhum servidor disponível")

        encontrados = []
        for guild in guilds:
            membro = guild.get_member(discord_id)
            if membro is None:
                try:
                    membro = await guild.fetch_member(discord_id)
                except discord.NotFound:
                    log.debug("Membro %s não está em %s; ignorando.", discord_id, guild.id)
                    continue
            encontrados.append((guild, membro))
        return encontrados

    @staticmethod
    def _papel(guild: discord.Guild, nome: str) -> discord.Role:
        papel = discord.utils.get(guild.roles, name=nome)
        if papel is None:
            raise IntegracaoIndisponivelError(
                "Discord",
                f"papel '{nome}' não existe no servidor {guild.name}; "
                "crie os papéis TYTO ou rode `/verificar-cargos`.",
            )
        return papel

    def _guilds_alvo(self, guild_id: int | None) -> list[discord.Guild]:
        if guild_id is not None:
            guild = self._bot.get_guild(guild_id)
            return [guild] if guild else []
        return list(self._bot.guilds)


async def cargos_faltantes(guild: discord.Guild) -> list[str]:
    """Papéis TYTO (patentes + cargos institucionais) ausentes no servidor."""
    existentes = {papel.name for papel in guild.roles}
    esperados = nomes_de_patentes_discord() | nomes_de_cargos_institucionais_discord()
    return sorted(esperados - existentes)
