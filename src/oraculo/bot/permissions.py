"""Decorators de permissão para slash commands — RN-008 / US-204.

A checagem consulta o **perfil persistido** do membro (patente + cargos
institucionais), não os papéis do Discord: o banco é a fonte de verdade da
hierarquia (RN-001) e continua correto mesmo que alguém edite papéis
manualmente no servidor.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import discord
from discord import app_commands

from oraculo.db.base import sessao
from oraculo.db.models import Membro
from oraculo.domain.hierarchy import Perfil
from oraculo.domain.permissions import (
    Acao,
    descrever_requisito,
    pode_executar,
    requisito_minimo,
)
from oraculo.repositories import membros as repo_membros

T = TypeVar("T")


class PermissaoInsuficiente(app_commands.CheckFailure):
    """Erro traduzido para mensagem amigável pelo handler global."""

    def __init__(self, acao: Acao, perfil: Perfil) -> None:
        self.acao = acao
        self.perfil = perfil
        self.requisito = requisito_minimo(acao)
        super().__init__(
            f"Requer **{descrever_requisito(self.requisito)}**. "
            f"Você: **{perfil.descricao()}**."
        )


async def obter_autor(interaction: discord.Interaction) -> Membro:
    """Membro persistido correspondente ao autor da interação (RF-001)."""
    async with sessao() as session:
        return await repo_membros.obter_ou_criar_por_discord(
            session,
            discord_id=interaction.user.id,
            nome_exibicao=interaction.user.display_name,
        )


async def perfil_do_autor(interaction: discord.Interaction) -> Perfil:
    membro = await obter_autor(interaction)
    return membro.perfil


ATRIBUTO_ACAO = "__oraculo_acao__"


def requer(acao: Acao, *, efemero: bool = False) -> Callable[[T], T]:
    """Aplica a política central de permissões ao comando decorado.

    **Confirma a interação antes de consultar o banco.** O Discord derruba a
    interação com "O aplicativo não respondeu" se nada for confirmado em 3
    segundos, e esta checagem faz I/O (inclusive o `INSERT` de auto-registro no
    primeiro contato de um usuário). Como o `defer` acontece aqui, os comandos
    decorados **não** devem chamar `interaction.response.defer()` de novo —
    respondem sempre com `interaction.followup.send(...)`.

    `efemero` define a visibilidade da resposta do comando inteiro, porque é no
    `defer` que ela é decidida.

    Além de validar, registra a ação exigida no próprio comando: é assim que
    `/ajuda` descobre o requisito sem manter uma segunda lista.

    Uso::

        @app_commands.command(name="conceder-xp")
        @requer(Acao.CONCEDER_XP)
        async def conceder_xp(self, interaction, ...): ...
    """

    async def predicado(interaction: discord.Interaction) -> bool:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=efemero)
        perfil = await perfil_do_autor(interaction)
        if not pode_executar(perfil, acao):
            raise PermissaoInsuficiente(acao, perfil)
        return True

    def decorador(alvo: T) -> T:
        # Funciona com o decorator acima ou abaixo de `@app_commands.command`.
        setattr(getattr(alvo, "callback", alvo), ATRIBUTO_ACAO, acao)
        return app_commands.check(predicado)(alvo)

    return decorador


def acao_requerida(comando: app_commands.Command) -> Acao | None:
    """Ação exigida por um comando, ou `None` se ele não declarou nenhuma."""
    return getattr(comando.callback, ATRIBUTO_ACAO, None)
