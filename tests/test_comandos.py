"""Catálogo de comandos e `/ajuda` — RN-008.

Carrega os cogs de verdade (sem conectar ao Discord) e verifica que a árvore de
comandos e a política de permissões continuam coerentes entre si.
"""

from __future__ import annotations

import pytest

from oraculo.bot.client import COGS, OraculoBot
from oraculo.bot.cogs.ajuda import agrupar_por_requisito
from oraculo.bot.permissions import acao_requerida
from oraculo.domain.hierarchy import NEOFITO, OFICIAL, VETERANO, CargoInstitucional, Perfil
from oraculo.domain.permissions import requisito_minimo, satisfaz

CONSELHEIRO = CargoInstitucional.CONSELHEIRO
ADMINISTRADOR = CargoInstitucional.ADMINISTRADOR

COMANDOS_ESPERADOS = frozenset(
    {
        "ajuda",
        "perfil",
        "ranking",
        "hierarquia",
        "agenda",
        "criar-reuniao",
        "criar-evento",
        "cancelar-agendamento",
        "comunicar",
        "agendar-comunicado",
        "comunicados",
        "cancelar-comunicado",
        "perguntar",
        "auditoria",
        "sincronizar-papeis",
        "verificar-cargos",
    }
)
"""RN-021 — a superfície **inteira** do bot. Comando novo precisa entrar aqui de
propósito, e o teste abaixo garante que nenhum deles escreve na plataforma."""

COMANDOS_DE_ESCRITA_REMOVIDOS = frozenset(
    {
        "conceder-xp",
        "historico-xp",
        "cargo-institucional",
        "confirmar-patente",
        "migrar-para-clube",
        "reconciliar-conta",
        "vincular-conta",
        "confirmar-vinculo",
        "saldo",
        "extrato-dracmas",
        "doar-dracmas",
        "remover-xp",
        "definir-cargo",
    }
)


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
    """RN-020 — sem `@requer` o comando escaparia do gate de cadastro e do /ajuda."""
    sem_acao = [c.qualified_name for c in bot.tree.walk_commands() if acao_requerida(c) is None]
    assert sem_acao == []


async def test_superficie_de_comandos_e_exatamente_a_esperada(bot):
    nomes = {c.qualified_name for c in bot.tree.walk_commands()}
    assert nomes == COMANDOS_ESPERADOS


async def test_nenhum_comando_de_escrita_na_plataforma(bot):
    """RN-021 — XP, patente, cargo, Dracmas e vínculos só se alteram na TYTO.club."""
    nomes = {c.qualified_name for c in bot.tree.walk_commands()}
    assert nomes.isdisjoint(COMANDOS_DE_ESCRITA_REMOVIDOS)


@pytest.mark.parametrize(
    ("comando", "requisito"),
    [
        ("perfil", NEOFITO),
        ("ranking", NEOFITO),
        ("ajuda", NEOFITO),
        ("criar-reuniao", VETERANO),
        ("criar-evento", OFICIAL),
        ("comunicar", OFICIAL),
        ("agendar-comunicado", OFICIAL),
        ("cancelar-comunicado", OFICIAL),
        ("sincronizar-papeis", ADMINISTRADOR),
        ("auditoria", CONSELHEIRO),
    ],
)
async def test_requisito_de_cada_comando(bot, comando, requisito):
    alvo = next(c for c in bot.tree.walk_commands() if c.qualified_name == comando)
    assert requisito_minimo(acao_requerida(alvo)) == requisito


async def test_ajuda_agrupa_todos_os_comandos_por_requisito(bot):
    todos = list(bot.tree.walk_commands())
    grupos = agrupar_por_requisito(todos)

    total_agrupado = sum(len(lista) for lista in grupos.values())
    assert total_agrupado == len(todos)

    nomes_membro = {c.qualified_name for c in grupos[NEOFITO]}
    assert {"perfil", "ranking", "ajuda"} <= nomes_membro
    assert "auditoria" not in nomes_membro


async def test_neofito_ve_apenas_a_secao_liberada(bot):
    """Um Neófito sem cargo tem acesso só ao grupo de todos os membros."""
    grupos = agrupar_por_requisito(list(bot.tree.walk_commands()))
    liberados = [req for req in grupos if satisfaz(Perfil(NEOFITO), req)]
    assert liberados == [NEOFITO]


async def test_comandos_descrevem_o_que_fazem(bot):
    """A descrição alimenta o /ajuda e a lista nativa do Discord."""
    for comando in bot.tree.walk_commands():
        assert comando.description, f"{comando.qualified_name} sem descrição"
        assert len(comando.description) <= 100
