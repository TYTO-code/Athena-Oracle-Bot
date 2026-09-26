"""Sincronização de papéis no Discord — RF-006 / RN-001 / RN-003 / TD-005 / TD-007.

Este é o teste que fecha o defeito do legado: o bot antigo atribuía o novo cargo
sem remover os anteriores. Os dublês abaixo imitam apenas a superfície da API do
discord.py usada pelo sincronizador.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from oraculo.bot.role_sync import SincronizadorDiscord, cargos_faltantes
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.domain.hierarchy import OFICIAL, PATENTES, VETERANO, CargoInstitucional


@dataclass
class PapelFalso:
    id: int
    name: str


@dataclass
class MembroFalso:
    id: int
    roles: list[PapelFalso] = field(default_factory=list)
    removidos: list[str] = field(default_factory=list)
    adicionados: list[str] = field(default_factory=list)

    async def remove_roles(self, *papeis, reason: str | None = None) -> None:
        self.removidos.extend(p.name for p in papeis)
        restantes = {p.id for p in papeis}
        self.roles = [p for p in self.roles if p.id not in restantes]

    async def add_roles(self, *papeis, reason: str | None = None) -> None:
        self.adicionados.extend(p.name for p in papeis)
        self.roles.extend(papeis)


@dataclass
class GuildFalsa:
    id: int
    name: str
    roles: list[PapelFalso]
    membros: dict[int, MembroFalso] = field(default_factory=dict)

    def get_member(self, discord_id: int) -> MembroFalso | None:
        return self.membros.get(discord_id)


@dataclass
class BotFalso:
    guilds: list[GuildFalsa]

    def get_guild(self, guild_id: int) -> GuildFalsa | None:
        return next((g for g in self.guilds if g.id == guild_id), None)


def montar_guild(papeis_do_membro: list[str]) -> tuple[GuildFalsa, MembroFalso]:
    nomes = [p.nome for p in PATENTES] + ["Conselheiro", "Administrador", "Designer"]
    catalogo = {nome: PapelFalso(id=indice + 1, name=nome) for indice, nome in enumerate(nomes)}
    membro = MembroFalso(id=999, roles=[catalogo[nome] for nome in papeis_do_membro])
    guild = GuildFalsa(id=1, name="Clube TYTO", roles=list(catalogo.values()))
    guild.membros[membro.id] = membro
    return guild, membro


async def test_remove_todas_as_patentes_antes_de_atribuir():
    """TD-005 — o acúmulo de papéis do legado não pode se repetir."""
    guild, membro = montar_guild(["Neófito", "Veterano"])
    sincronizador = SincronizadorDiscord(BotFalso([guild]))

    await sincronizador.sincronizar(discord_id=999, patente=OFICIAL, guild_id=1)

    assert sorted(membro.removidos) == ["Neófito", "Veterano"]
    assert membro.adicionados == ["Oficial"]
    assert [p.name for p in membro.roles] == ["Oficial"]


async def test_preserva_papeis_que_nao_sao_patente():
    """Papéis decorativos e cargos institucionais não são tocados pela patente."""
    guild, membro = montar_guild(["Veterano", "Designer", "Conselheiro"])
    sincronizador = SincronizadorDiscord(BotFalso([guild]))

    await sincronizador.sincronizar(discord_id=999, patente=OFICIAL, guild_id=1)

    assert membro.removidos == ["Veterano"]
    assert sorted(p.name for p in membro.roles) == ["Conselheiro", "Designer", "Oficial"]


async def test_operacao_e_idempotente():
    guild, membro = montar_guild(["Veterano"])
    sincronizador = SincronizadorDiscord(BotFalso([guild]))

    await sincronizador.sincronizar(discord_id=999, patente=VETERANO, guild_id=1)

    assert membro.removidos == []
    assert membro.adicionados == []
    assert [p.name for p in membro.roles] == ["Veterano"]


async def test_cargo_institucional_e_adicionado_e_removido_sem_tocar_na_patente():
    guild, membro = montar_guild(["Oficial"])
    sincronizador = SincronizadorDiscord(BotFalso([guild]))

    await sincronizador.definir_cargo_institucional(
        discord_id=999, cargo=CargoInstitucional.CONSELHEIRO, ativo=True, guild_id=1
    )
    assert sorted(p.name for p in membro.roles) == ["Conselheiro", "Oficial"]

    await sincronizador.definir_cargo_institucional(
        discord_id=999, cargo=CargoInstitucional.CONSELHEIRO, ativo=False, guild_id=1
    )
    assert [p.name for p in membro.roles] == ["Oficial"]


async def test_erro_claro_quando_o_papel_nao_existe_no_servidor():
    guild = GuildFalsa(id=1, name="Clube TYTO", roles=[PapelFalso(1, "Neófito")])
    guild.membros[999] = MembroFalso(id=999, roles=[])
    sincronizador = SincronizadorDiscord(BotFalso([guild]))

    with pytest.raises(IntegracaoIndisponivelError, match="Oficial"):
        await sincronizador.sincronizar(discord_id=999, patente=OFICIAL, guild_id=1)


async def test_diagnostico_lista_papeis_ausentes():
    presentes = [p.nome for p in PATENTES if p.nome != "Omni"]
    guild = GuildFalsa(
        id=1,
        name="Clube TYTO",
        roles=[PapelFalso(i, nome) for i, nome in enumerate([*presentes, "Conselheiro"])],
    )
    assert await cargos_faltantes(guild) == ["Administrador", "Omni"]
