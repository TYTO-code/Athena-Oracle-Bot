"""Webhook e health check — TD-003 / RNF-003 / US-102, US-403."""

from __future__ import annotations

import json
import time

import httpx
import pytest
from sqlalchemy import func, select

from oraculo.api.app import criar_app
from oraculo.api.security import assinar, validar_assinatura
from oraculo.db.models import EventoWebhook, RegistroAuditoria
from oraculo.domain.errors import AssinaturaInvalidaError

SEGREDO = "segredo-de-teste"
PAYLOAD = {"webhook_id": "wh-001", "event": "taskStatusUpdated"}


@pytest.fixture
def corpo() -> bytes:
    return json.dumps(PAYLOAD).encode()


@pytest.fixture
async def cliente(engine, settings, monkeypatch) -> httpx.AsyncClient:
    """Cliente ASGI sem lifespan: o schema já vem da fixture `engine`."""
    monkeypatch.setattr("oraculo.api.routers.webhooks.get_settings", lambda: settings)
    monkeypatch.setattr("oraculo.api.routers.health.get_settings", lambda: settings)
    app = criar_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://teste"
    ) as cliente_http:
        yield cliente_http


# --- Validação da assinatura (unitária) -------------------------------------


def test_assinatura_valida_passa(corpo):
    validar_assinatura(
        corpo=corpo, assinatura_recebida=assinar(corpo, SEGREDO), segredo=SEGREDO
    )


def test_prefixo_sha256_e_aceito(corpo):
    validar_assinatura(
        corpo=corpo,
        assinatura_recebida=f"sha256={assinar(corpo, SEGREDO)}",
        segredo=SEGREDO,
    )


def test_corpo_adulterado_invalida_a_assinatura(corpo):
    assinatura = assinar(corpo, SEGREDO)
    with pytest.raises(AssinaturaInvalidaError):
        validar_assinatura(
            corpo=corpo + b" ", assinatura_recebida=assinatura, segredo=SEGREDO
        )


def test_sem_segredo_configurado_falha_fechado(corpo):
    """RNF-003 — servidor sem segredo rejeita em vez de aceitar tudo."""
    with pytest.raises(AssinaturaInvalidaError):
        validar_assinatura(corpo=corpo, assinatura_recebida="qualquer", segredo=None)


def test_timestamp_antigo_e_rejeitado(corpo):
    antigo = str(time.time() - 3_600)
    with pytest.raises(AssinaturaInvalidaError, match="tolerância"):
        validar_assinatura(
            corpo=corpo,
            assinatura_recebida=assinar(corpo, SEGREDO),
            segredo=SEGREDO,
            timestamp=antigo,
        )


# --- Endpoint ---------------------------------------------------------------


async def test_webhook_sem_assinatura_e_rejeitado(cliente, corpo, session):
    resposta = await cliente.post("/webhooks/clickup", content=corpo)

    assert resposta.status_code == 401
    assert await session.scalar(select(func.count()).select_from(EventoWebhook)) == 0


async def test_webhook_com_assinatura_invalida_e_rejeitado(cliente, corpo, session):
    resposta = await cliente.post(
        "/webhooks/clickup", content=corpo, headers={"X-Signature": "0" * 64}
    )

    assert resposta.status_code == 401
    assert await session.scalar(select(func.count()).select_from(EventoWebhook)) == 0


async def test_webhook_valido_persiste_e_audita(cliente, corpo, session):
    resposta = await cliente.post(
        "/webhooks/clickup",
        content=corpo,
        headers={"X-Signature": assinar(corpo, SEGREDO)},
    )

    assert resposta.status_code == 202
    assert resposta.json()["status"] == "aceito"

    evento = await session.scalar(select(EventoWebhook))
    assert evento.evento_id == "wh-001"
    assert evento.tipo_evento == "taskStatusUpdated"
    assert evento.processado is True

    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "webhook.recebido")
    )
    assert registro is not None


async def test_replay_do_mesmo_evento_e_ignorado(cliente, corpo, session):
    cabecalhos = {"X-Signature": assinar(corpo, SEGREDO)}
    await cliente.post("/webhooks/clickup", content=corpo, headers=cabecalhos)
    resposta = await cliente.post("/webhooks/clickup", content=corpo, headers=cabecalhos)

    assert resposta.json()["status"] == "duplicado"
    assert await session.scalar(select(func.count()).select_from(EventoWebhook)) == 1


async def test_payload_nao_json_com_assinatura_valida_retorna_400(cliente):
    corpo_invalido = b"nao-e-json"
    resposta = await cliente.post(
        "/webhooks/clickup",
        content=corpo_invalido,
        headers={"X-Signature": assinar(corpo_invalido, SEGREDO)},
    )

    assert resposta.status_code == 400


async def test_health_e_readiness(cliente):
    assert (await cliente.get("/health")).json()["status"] == "ok"

    pronto = await cliente.get("/health/ready")
    assert pronto.status_code == 200
    assert pronto.json()["checagens"]["banco"] == "ok"
