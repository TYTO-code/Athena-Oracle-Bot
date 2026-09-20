"""Base externa de projetos: o filtro é a fronteira de autorização — RN-017.

Roda contra SQLite em memória com o mesmo contrato de schema esperado do
PostgreSQL externo — o objetivo é provar o comportamento do filtro, não o
dialeto do banco.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from oraculo.config import Settings
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.integrations.projetos_db import (
    LIMITE_CARACTERES_TEXTO,
    LIMITE_DECISOES_POR_PROJETO,
    ProjetosPostgres,
    _metadata,
    criar_base_de_projetos,
    decisoes_tabela,
    projetos_tabela,
)


@pytest.fixture
async def base():
    """Base externa dublê, com o schema do contrato e dois projetos."""
    motor = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with motor.begin() as conexao:
        await conexao.run_sync(_metadata.create_all)
        await conexao.execute(
            projetos_tabela.insert(),
            [
                {
                    "id": "proj-a",
                    "nome": "Projeto A",
                    "descricao": "Descrição do A",
                    "status": "ativo",
                },
                {"id": "proj-b", "nome": "Projeto B", "descricao": "SEGREDO-B", "status": "ativo"},
            ],
        )
        await conexao.execute(
            decisoes_tabela.insert(),
            [
                {
                    "id": 1,
                    "projeto_id": "proj-a",
                    "titulo": "Stack",
                    "conteudo": "Postgres",
                    "decidido_em": datetime(2026, 1, 1, tzinfo=UTC),
                },
                {
                    "id": 2,
                    "projeto_id": "proj-b",
                    "titulo": "Orçamento",
                    "conteudo": "50 mil",
                    "decidido_em": datetime(2026, 2, 1, tzinfo=UTC),
                },
            ],
        )

    repositorio = ProjetosPostgres(Settings(_env_file=None, projetos_database_url="sqlite://"))
    repositorio._engine = motor  # injeta o motor de teste
    try:
        yield repositorio
    finally:
        await motor.dispose()


async def test_traz_apenas_projetos_autorizados(base):
    contextos = await base.contexto(["proj-a"])

    assert [c.id for c in contextos] == ["proj-a"]
    assert all("SEGREDO-B" not in (c.descricao or "") for c in contextos)


async def test_decisoes_nunca_cruzam_projetos(base):
    contextos = await base.contexto(["proj-a"])

    conteudos = [d.conteudo for c in contextos for d in c.decisoes]
    assert conteudos == ["Postgres"]
    assert "50 mil" not in conteudos


async def test_lista_vazia_nao_consulta_o_banco(base):
    """Sem autorização não há consulta — nem com o banco disponível."""
    await base.fechar()  # derruba o motor: qualquer consulta falharia

    assert await base.contexto([]) == []


async def test_ids_repetidos_ou_vazios_sao_higienizados(base):
    contextos = await base.contexto(["proj-a", "proj-a", "", "proj-a"])

    assert [c.id for c in contextos] == ["proj-a"]


async def test_varios_projetos_autorizados_vem_juntos(base):
    contextos = await base.contexto(["proj-a", "proj-b"])

    assert sorted(c.id for c in contextos) == ["proj-a", "proj-b"]


async def test_texto_gigante_e_truncado(base):
    async with base._obter_engine().begin() as conexao:
        await conexao.execute(
            projetos_tabela.insert(),
            {"id": "proj-c", "nome": "C", "descricao": "x" * (LIMITE_CARACTERES_TEXTO + 500)},
        )

    contexto = (await base.contexto(["proj-c"]))[0]

    assert len(contexto.descricao) <= LIMITE_CARACTERES_TEXTO + len("… (truncado)")
    assert contexto.descricao.endswith("(truncado)")


async def test_historico_longo_respeita_o_teto_de_decisoes(base):
    async with base._obter_engine().begin() as conexao:
        await conexao.execute(projetos_tabela.insert(), {"id": "proj-d", "nome": "D"})
        await conexao.execute(
            decisoes_tabela.insert(),
            [
                {
                    "id": 100 + i,
                    "projeto_id": "proj-d",
                    "titulo": f"D{i}",
                    "conteudo": f"decisão {i}",
                    "decidido_em": datetime(2026, 1, 1, tzinfo=UTC),
                }
                for i in range(LIMITE_DECISOES_POR_PROJETO + 10)
            ],
        )

    contexto = (await base.contexto(["proj-d"]))[0]

    assert len(contexto.decisoes) == LIMITE_DECISOES_POR_PROJETO


async def test_sem_url_configurada_a_base_nao_e_criada():
    assert criar_base_de_projetos(Settings(_env_file=None, projetos_database_url=None)) is None


async def test_falha_de_conexao_vira_erro_de_integracao():
    repositorio = ProjetosPostgres(
        Settings(_env_file=None, projetos_database_url="sqlite+aiosqlite:///:memory:")
    )

    # Sem as tabelas do contrato, a consulta falha — e precisa chegar ao
    # chamador como indisponibilidade, não como exceção crua de SQL.
    with pytest.raises(IntegracaoIndisponivelError):
        await repositorio.contexto(["proj-a"])

    await repositorio.fechar()
