"""Perfil e ranking — RF-002, RF-004 / UC-002 / US-404."""

from __future__ import annotations

from datetime import timedelta

import pytest

from oraculo.db.base import agora
from oraculo.domain.hierarchy import NEOFITO, OMNI, VETERANO, CargoInstitucional
from oraculo.integrations.cache import CacheMemoria
from oraculo.services.ranking_service import RankingService
from oraculo.services.xp_service import XpService

CONSELHEIRO = CargoInstitucional.CONSELHEIRO
MEMBRO = NEOFITO


@pytest.fixture
def cache() -> CacheMemoria:
    return CacheMemoria()


@pytest.fixture
def servico(cache, settings) -> RankingService:
    return RankingService(cache=cache, settings=settings)


async def test_perfil_traz_progressao_completa(session, criar_membro, servico):
    """RF-002 — patente, XP, próxima patente, XP necessário e posição."""
    membro = await criar_membro(VETERANO, xp=2_000)
    await criar_membro(CONSELHEIRO, xp=4_000)

    perfil = await servico.perfil(session, membro)

    assert perfil.patente == VETERANO
    assert perfil.proxima.slug == "mestre-de-armas"
    assert perfil.xp_para_proximo == 4_600
    assert perfil.posicao == 2
    assert perfil.total_membros == 2
    assert perfil.no_topo is False


async def test_perfil_no_topo_da_progressao(session, criar_membro, servico):
    membro = await criar_membro(OMNI, xp=300_000_000_000)

    perfil = await servico.perfil(session, membro)

    assert perfil.no_topo is True
    assert perfil.xp_para_proximo is None


async def test_ranking_geral_ordena_por_xp(session, criar_membro, servico):
    await criar_membro(MEMBRO, xp=100, nome="Bronze")
    await criar_membro(MEMBRO, xp=900, nome="Ouro")
    await criar_membro(MEMBRO, xp=400, nome="Prata")

    linhas = await servico.ranking(session, limite=10)

    assert [linha.nome_exibicao for linha in linhas] == ["Ouro", "Prata", "Bronze"]
    assert [linha.posicao for linha in linhas] == [1, 2, 3]


async def test_ranking_por_periodo_considera_apenas_a_janela(session, criar_membro, servico):
    """RF-004 — o ranking do período soma a trilha `xp_audit` da janela."""
    autor = await criar_membro(CONSELHEIRO)
    veterano = await criar_membro(MEMBRO, xp=5_000, nome="Veterano")
    novato = await criar_membro(MEMBRO, xp=0, nome="Novato")

    xp_service = XpService()
    await xp_service.conceder(
        session, membro=novato, quantidade=300, motivo="Evento da semana", autor=autor
    )

    linhas = await servico.ranking(session, periodo="semana", limite=10)

    assert [linha.nome_exibicao for linha in linhas] == ["Novato"]
    assert veterano.nome_exibicao not in [linha.nome_exibicao for linha in linhas]


async def test_ranking_por_periodo_ignora_movimentacoes_antigas(session, criar_membro, servico):
    autor = await criar_membro(CONSELHEIRO)
    membro = await criar_membro(MEMBRO, xp=0)

    xp_service = XpService()
    resultado = await xp_service.conceder(
        session, membro=membro, quantidade=300, motivo="Evento antigo", autor=autor
    )
    resultado.movimentacao.criado_em = agora() - timedelta(days=45)
    await session.flush()

    assert await servico.ranking(session, periodo="semana") == []
    assert len(await servico.ranking(session, periodo="trimestre")) == 1


async def test_periodo_invalido_e_rejeitado(session, servico):
    with pytest.raises(ValueError, match="Período inválido"):
        await servico.ranking(session, periodo="decada")


async def test_ranking_usa_cache_e_invalida(session, criar_membro, servico, cache):
    """US-404 — a segunda chamada vem do cache; a invalidação força releitura."""
    await criar_membro(MEMBRO, xp=100, nome="Primeiro")

    primeira = await servico.ranking(session, limite=5)
    await criar_membro(MEMBRO, xp=999, nome="Segundo")

    assert await servico.ranking(session, limite=5) == primeira

    await servico.invalidar()
    atualizado = await servico.ranking(session, limite=5)
    assert [linha.nome_exibicao for linha in atualizado] == ["Segundo", "Primeiro"]


async def test_cache_expira_por_ttl(cache):
    await cache.definir("ranking:teste", [1, 2, 3], ttl=0)
    assert await cache.obter("ranking:teste") is None
