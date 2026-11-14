"""Alertas do Grafana por DM (D15): texto, rota protegida e caixa de entrega."""

from __future__ import annotations

import httpx
import pytest

from oraculo.api.app import criar_app
from oraculo.bot.cogs.alertas import entregar_alertas
from oraculo.domain.alertas_grafana import formatar_alerta
from oraculo.services.alertas_service import CaixaDeAlertas

TOKEN = "token-do-grafana"
PAYLOAD = {
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "Custo de IA do dia"},
            "annotations": {"summary": "Gasto de hoje passou de US$ 0,10"},
            "generatorURL": "https://interno.example.com/x",
        }
    ],
}

# --- Texto ------------------------------------------------------------------------------------


def test_texto_do_alerta_disparado_e_resolvido():
    assert formatar_alerta(PAYLOAD) == (
        "🚨 Alerta: **Custo de IA do dia** — Gasto de hoje passou de US$ 0,10"
    )
    resolvido = {"status": "resolved", "alerts": [{**PAYLOAD["alerts"][0], "status": "resolved"}]}
    assert formatar_alerta(resolvido).startswith("✅ Resolvido: **Custo de IA do dia**")


def test_texto_nao_leva_url_nem_valores_brutos():
    assert "interno.example.com" not in formatar_alerta(PAYLOAD)


def test_payload_invalido_ou_vazio_e_ignorado():
    assert formatar_alerta([]) is None
    assert formatar_alerta({"alerts": []}) is None


def test_muitos_alertas_sao_resumidos():
    muitos = {"alerts": [{"labels": {"alertname": f"a{i}"}} for i in range(15)]}
    texto = formatar_alerta(muitos)
    assert "… e mais 5" in texto
    assert len(texto) <= 1900


# --- Rota ---------------------------------------------------------------------------------------


@pytest.fixture
def caixa(monkeypatch) -> CaixaDeAlertas:
    nova = CaixaDeAlertas()
    monkeypatch.setattr("oraculo.api.routers.webhooks.CAIXA_ALERTAS", nova)
    return nova


async def _post(settings, monkeypatch, cabecalhos=None, corpo=PAYLOAD) -> httpx.Response:
    monkeypatch.setattr("oraculo.api.routers.webhooks.get_settings", lambda: settings)
    app = criar_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://teste"
    ) as cliente:
        return await cliente.post("/webhooks/grafana", json=corpo, headers=cabecalhos or {})


async def test_sem_token_configurado_a_rota_nao_existe(settings, monkeypatch, caixa):
    resposta = await _post(settings, monkeypatch, {"Authorization": f"Bearer {TOKEN}"})
    assert resposta.status_code == 404


async def test_token_errado_e_recusado(settings, monkeypatch, caixa):
    cfg = settings.model_copy(update={"grafana_webhook_token": TOKEN, "alertas_discord_id": 1})
    assert (await _post(cfg, monkeypatch)).status_code == 401
    errado = {"Authorization": "Bearer outro"}
    assert (await _post(cfg, monkeypatch, errado)).status_code == 401
    assert caixa.retirar_todos() == []


async def test_token_certo_enfileira_a_dm(settings, monkeypatch, caixa):
    cfg = settings.model_copy(
        update={"grafana_webhook_token": TOKEN, "alertas_discord_id": 1, "run_bot": True}
    )
    resposta = await _post(cfg, monkeypatch, {"Authorization": f"Bearer {TOKEN}"})
    assert resposta.status_code == 202
    assert resposta.json() == {"status": "enfileirado"}
    assert caixa.retirar_todos() == [formatar_alerta(PAYLOAD)]


async def test_sem_destinatario_nao_enfileira(settings, monkeypatch, caixa):
    cfg = settings.model_copy(update={"grafana_webhook_token": TOKEN, "alertas_discord_id": None})
    resposta = await _post(cfg, monkeypatch, {"Authorization": f"Bearer {TOKEN}"})
    assert resposta.json() == {"status": "sem_destino"}
    assert caixa.retirar_todos() == []


# --- Entrega ------------------------------------------------------------------------------------


async def test_entrega_esvazia_a_caixa():
    caixa = CaixaDeAlertas()
    caixa.enfileirar("a")
    caixa.enfileirar("b")
    enviados: list[str] = []

    async def enviar(texto: str) -> None:
        enviados.append(texto)

    assert await entregar_alertas(caixa, enviar) == 2
    assert enviados == ["a", "b"]
    assert caixa.retirar_todos() == []


async def test_falha_passageira_devolve_o_resto():
    import discord

    caixa = CaixaDeAlertas()
    for t in ("a", "b", "c"):
        caixa.enfileirar(t)
    chamadas: list[str] = []

    class Resposta:
        status = 503
        reason = "indisponivel"

    async def enviar(texto: str) -> None:
        chamadas.append(texto)
        if texto == "b":
            raise discord.HTTPException(Resposta(), "fora")

    assert await entregar_alertas(caixa, enviar) == 1
    assert caixa.retirar_todos() == ["b", "c"]


def test_caixa_cheia_descarta_o_mais_novo():
    caixa = CaixaDeAlertas(limite=1)
    assert caixa.enfileirar("a")
    assert not caixa.enfileirar("b")
    assert caixa.retirar_todos() == ["a"]
