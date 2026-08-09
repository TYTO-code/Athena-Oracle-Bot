"""Decorators de permissão para slash commands — RN-008 / US-204.

A checagem consulta o **cargo persistido** do membro, não os papéis do Discord:
o banco é a fonte de verdade da hierarquia (RN-001) e continua correto mesmo
que alguém edite papéis manualmente no servidor.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import discord
from discord import app_commands

from oraculo.db.base import sessao
from oraculo.db.models import Membro
from oraculo.domain.hierarchy import Cargo, cargo_por_slug
from oraculo.domain.permissions import Acao, cargo_minimo, pode_executar
from oraculo.repositories import membros as repo_membros

T = TypeVar("T")


class PermissaoInsuficiente(app_commands.CheckFailure):
    """Erro traduzido para mensagem amigável pelo handler global."""

    def __init__(self, acao: Acao, cargo_atual: Cargo) -> None:
        self.acao = acao
        self.cargo_atual = cargo_atual
        self.cargo_minimo = cargo_minimo(acao)
        super().__init__(
            f"Requer **{self.cargo_minimo.nome}** ou superior. "
            f"Seu cargo: **{cargo_atual.nome}**."
        )


async def obter_autor(interaction: discord.Interaction) -> Membro:
    """Membro persistido correspondente ao autor da interação (RF-001)."""
    async with sessao() as session:
        return await repo_membros.obter_ou_criar_por_discord(
            session,
            discord_id=interaction.user.id,
            nome_exibicao=interaction.user.display_name,
        )


async def cargo_do_autor(interaction: discord.Interaction) -> Cargo:
    membro = await obter_autor(interaction)
    return cargo_por_slug(membro.cargo_slug)


def requer(acao: Acao) -> Callable[[T], T]:
    """Aplica a política central de permissões ao comando decorado.

    Uso::

        @app_commands.command(name="conceder-xp")
        @requer(Acao.CONCEDER_XP)
        async def conceder_xp(self, interaction, ...): ...
    """

    async def predicado(interaction: discord.Interaction) -> bool:
        cargo = await cargo_do_autor(interaction)
        if not pode_executar(cargo, acao):
            raise PermissaoInsuficiente(acao, cargo)
        return True

    return app_commands.check(predicado)
