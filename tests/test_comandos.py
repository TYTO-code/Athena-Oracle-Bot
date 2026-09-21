"""Catálogo de comandos e `/ajuda` — RN-008.

Carrega os cogs de verdade (sem conectar ao Discord) e verifica que a árvore de
comandos e a política de permissões continuam coerentes entre si.
"""

from __future__ import annotations

import pytest

from oraculo.bot.client import COGS, OraculoBot
from oraculo.bot.cogs.ajuda import agrupar_por_cargo
from oraculo.bot.permissions import acao_requerida
from oraculo.domain.hierarchy import CAVALARIA, CONSELHEIRO, LORDE, MEMBRO, pelo_menos
from oraculo.domain.permissions import cargo_minimo

COMANDOS_SEM_CARGO = frozenset(
    {"saldo", "extrato-dracmas", "doar-dracmas", "vincular-conta", "confirmar-vinculo"}
)
"""RN-011 — camada Comunidade opera por `discord_id`, não por `Membro`/cargo
do Clube (ver docstring de `bot/cogs/comunidade.py`); estes comandos
legitimamente não passam por `@requer` nem aparecem em `/ajuda` por cargo.

RN-016 — `vincular-conta`/`confirmar-vinculo` têm o mesmo motivo, mas na outra
ponta: `@requer` criaria o `Membro` "zerado" que o próprio fluxo existe para
recusar como duplicado (ver docstring de `bot/cogs/vinculo.py`)."""


@pytest.fixture
async def bot(settings):
    cliente = OraculoBot(settings)
    for cog in COGS:
        await cliente.load_extension(cog)
    try:
        yield cliente
    finally:
        await cliente.container.fechar()


async def test_todo_comando_declara_a_acao_exigida(bot):
    """Um comando sem `@requer` (fora da exceção documentada da Comunidade) escaparia da
    política e sumiria do /ajuda."""
    sem_acao = [
        c.qualified_name
        for c in bot.tree.walk_commands()
        if acao_requerida(c) is None and c.qualified_name not in COMANDOS_SEM_CARGO
    ]
    assert sem_acao == []


async def test_comandos_esperados_estao_registrados(bot):
    nomes = {c.qualified_name for c in bot.tree.walk_commands()}
    assert {
        "ajuda",
        "perfil",
        "ranking",
        "agenda",
        "hierarquia",
        "conceder-xp",
        "remover-xp",
        "historico-xp",
        "criar-reuniao",
        "criar-evento",
        "cancelar-agendamento",
        "auditoria",
        "definir-cargo",
        "verificar-cargos",
        "comunicar",
        "agendar-comunicado",
        "comunicados",
        "cancelar-comunicado",
    } <= nomes


@pytest.mark.parametrize(
    ("comando", "cargo_esperado"),
    [
        ("perfil", MEMBRO),
        ("ranking", MEMBRO),
        ("ajuda", MEMBRO),
        ("criar-reuniao", CAVALARIA),
        ("criar-evento", LORDE),
        ("conceder-xp", CONSELHEIRO),
        ("historico-xp", CONSELHEIRO),
        ("comunicar", LORDE),
        ("agendar-comunicado", LORDE),
        ("cancelar-comunicado", LORDE),
    ],
)
async def test_cargo_minimo_de_cada_comando(bot, comando, cargo_esperado):
    alvo = next(c for c in bot.tree.walk_commands() if c.qualified_name == comando)
    assert cargo_minimo(acao_requerida(alvo)) is cargo_esperado


async def test_ajuda_agrupa_todos_os_comandos_por_cargo(bot):
    todos = list(bot.tree.walk_commands())
    grupos = agrupar_por_cargo(todos)

    com_cargo = [c for c in todos if c.qualified_name not in COMANDOS_SEM_CARGO]
    total_agrupado = sum(len(lista) for lista in grupos.values())
    assert total_agrupado == len(com_cargo)

    nomes_membro = {c.qualified_name for c in grupos[MEMBRO]}
    assert {"perfil", "ranking", "ajuda"} <= nomes_membro
    assert "conceder-xp" not in nomes_membro


async def test_membro_ve_apenas_a_secao_liberada(bot):
    """Um Membro tem acesso ao grupo de Membro e a nenhum acima."""
    grupos = agrupar_por_cargo(list(bot.tree.walk_commands()))
    liberados = [cargo for cargo in grupos if pelo_menos(MEMBRO, cargo)]
    assert liberados == [MEMBRO]


async def test_comandos_descrevem_o_que_fazem(bot):
    """A descrição alimenta o /ajuda e a lista nativa do Discord."""
    for comando in bot.tree.walk_commands():
        assert comando.description, f"{comando.qualified_name} sem descrição"
        assert len(comando.description) <= 100
