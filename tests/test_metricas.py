"""Painel de métricas — Sprint 4 (RNF-001 / RNF-004)."""

from __future__ import annotations

import httpx
import pytest

from oraculo.api.app import criar_app
from oraculo.db.models import Aldeao, OrigemAcao
from oraculo.domain.hierarchy import OFICIAL, VETERANO, CargoInstitucional
from oraculo.repositories import auditoria
from oraculo.services.metricas_service import coletar, formato_prometheus

TOKEN = "token-de-metricas"


@pytest.fixture
async def cliente(engine, settings, monkeypatch) -> httpx.AsyncClient:
    settings.metricas_token = TOKEN
    monkeypatch.setattr("oraculo.api.routers.metricas.get_settings", lambda: settings)
    app = criar_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://teste"
    ) as cliente_http:
        yield cliente_http


async def test_coleta_agrega_membros_e_comunidade(session, criar_membro):
    await criar_membro(VETERANO, xp=2_000)
    await criar_membro(OFICIAL, xp=106_000)
    await criar_membro(CargoInstitucional.CONSELHEIRO)
    session.add(Aldeao(discord_id=1, saldo_dracmas=500))
    await auditoria.registrar(
        session, acao="backup.executado", resumo="ok", origem=OrigemAcao.SISTEMA
    )
    await session.flush()

    metricas = {m.nome: m for m in await coletar(session)}

    assert metricas["oraculo_membros_ativos"].valor() == 3
    assert metricas["oraculo_membros_por_patente"].valor(patente="oficial") == 1
    assert metricas["oraculo_membros_por_patente"].valor(patente="omni") == 0
    assert metricas["oraculo_membros_por_cargo"].valor(cargo="conselheiro") == 1
    assert metricas["oraculo_xp_total"].valor() == 108_000
    assert metricas["oraculo_aldeoes"].valor(situacao="ativa") == 1
    assert metricas["oraculo_dracmas_comunidade"].valor() == 500
    assert metricas["oraculo_ultimo_backup_timestamp_seconds"].valor() > 0
    assert metricas["oraculo_ultima_importacao_timestamp_seconds"].valor() == 0


async def test_formato_prometheus(session, criar_membro):
    await criar_membro(OFICIAL, xp=106_000)

    texto = formato_prometheus(await coletar(session))

    assert "# TYPE oraculo_membros_ativos gauge" in texto
    assert 'oraculo_membros_por_patente{patente="oficial"} 1' in texto
    assert texto.endswith("\n")


async def test_sem_token_configurado_os_endpoints_nao_existem(engine, settings, monkeypatch):
    settings.metricas_token = None
    monkeypatch.setattr("oraculo.api.routers.metricas.get_settings", lambda: settings)
    app = criar_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://teste"
    ) as cliente_http:
        assert (await cliente_http.get("/metrics")).status_code == 404
        assert (await cliente_http.get("/painel")).status_code == 404


async def test_token_errado_ou_ausente_e_recusado(cliente):
    assert (await cliente.get("/metrics")).status_code == 401
    resposta = await cliente.get("/metrics", headers={"Authorization": "Bearer errado"})
    assert resposta.status_code == 401


async def test_metrics_e_painel_com_token(cliente):
    resposta = await cliente.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert "oraculo_membros_ativos" in resposta.text

    painel = await cliente.get("/painel", params={"token": TOKEN})
    assert painel.status_code == 200
    assert "painel de métricas" in painel.text
