"""Sincronização de cargos no Discord — RF-006 / RN-001 / RN-003 / TD-005.

Este é o teste que fecha o defeito do legado: o bot antigo atribuía o novo cargo
sem remover os anteriores. Os dublês abaixo imitam apenas a superfície da API do
discord.py usada pelo sincronizador.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from oraculo.bot.role_sync import SincronizadorDiscord, cargos_faltantes
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.domain.hierarchy import CAVALARIA, LORDE


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
    catalogo = {
        nome: PapelFalso(id=indice + 1, name=nome)
        for indice, nome in enumerate(
            ["Membro", "Cavalaria", "Lorde", "Conselheiro", "Administrador", "Veterano"]
        )
    }
    membro = MembroFalso(id=999, roles=[catalogo[nome] for nome in papeis_do_membro])
    guild = GuildFalsa(id=1, name="Clube TYTO", roles=list(catalogo.values()))
    guild.membros[membro.id] = membro
    return guild, membro


async def test_remove_todos_os_cargos_tyto_antes_de_atribuir():
    """TD-005 — o acúmulo de cargos do legado não pode se repetir."""
    guild, membro = montar_guild(["Membro", "Cavalaria"])
    sincronizador = SincronizadorDiscord(BotFalso([guild]))

    await sincronizador.sincronizar(discord_id=999, cargo=LORDE, guild_id=1)

    assert sorted(membro.removidos) == ["Cavalaria", "Membro"]
    assert membro.adicionados == ["Lorde"]
    assert [p.name for p in membro.roles] == ["Lorde"]


async def test_preserva_cargos_que_nao_sao_da_hierarquia():
    """Cargos decorativos do servidor não são gerenciados pelo bot."""
    guild, membro = montar_guild(["Cavalaria", "Veterano"])
    sincronizador = SincronizadorDiscord(BotFalso([guild]))

    await sincronizador.sincronizar(discord_id=999, cargo=LORDE, guild_id=1)

    assert "Veterano" not in membro.removidos
    assert sorted(p.name for p in membro.roles) == ["Lorde", "Veterano"]


async def test_operacao_e_idempotente():
    guild, membro = montar_guild(["Cavalaria"])
    sincronizador = SincronizadorDiscord(BotFalso([guild]))

    await sincronizador.sincronizar(discord_id=999, cargo=CAVALARIA, guild_id=1)

    assert membro.removidos == []
    assert membro.adicionados == []
    assert [p.name for p in membro.roles] == ["Cavalaria"]


async def test_erro_claro_quando_o_cargo_nao_existe_no_servidor():
    guild = GuildFalsa(id=1, name="Clube TYTO", roles=[PapelFalso(1, "Membro")])
    guild.membros[999] = MembroFalso(id=999, roles=[])
    sincronizador = SincronizadorDiscord(BotFalso([guild]))

    with pytest.raises(IntegracaoIndisponivelError, match="Lorde"):
        await sincronizador.sincronizar(discord_id=999, cargo=LORDE, guild_id=1)


async def test_diagnostico_lista_cargos_ausentes():
    guild = GuildFalsa(id=1, name="Clube TYTO", roles=[PapelFalso(1, "Membro")])
    assert await cargos_faltantes(guild) == [
        "Administrador",
        "Cavalaria",
        "Conselheiro",
        "Lorde",
    ]
