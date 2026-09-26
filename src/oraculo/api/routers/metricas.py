"""Painel de métricas — Sprint 4 (RNF-001 / RNF-004).

* `GET /metrics` — texto Prometheus, para Grafana ou qualquer coletor.
* `GET /painel` — a mesma coleta em uma página HTML simples, para abrir no navegador.

Os dois só existem com `ORACULO_METRICAS_TOKEN` definido (senão, 404) e exigem o
token — em `Authorization: Bearer <token>` ou, no painel aberto pelo
navegador, em `?token=<token>`. Comparação em tempo constante.
"""

from __future__ import annotations

import hmac
from html import escape

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse

from oraculo.config import get_settings
from oraculo.db.base import agora, sessao
from oraculo.services.metricas_service import Metrica, coletar, formato_prometheus

router = APIRouter(tags=["observabilidade"])


def _autorizar(request: Request) -> None:
    esperado = get_settings().metricas_token
    if not esperado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    cabecalho = request.headers.get("authorization", "")
    recebido = (
        cabecalho.removeprefix("Bearer ").strip()
        if cabecalho.startswith("Bearer ")
        else request.query_params.get("token", "")
    )
    if not hmac.compare_digest(recebido.encode(), esperado.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@router.get("/metrics", summary="Métricas no formato Prometheus", include_in_schema=False)
async def metrics(request: Request) -> PlainTextResponse:
    _autorizar(request)
    async with sessao() as session:
        metricas = await coletar(session)
    return PlainTextResponse(
        formato_prometheus(metricas), media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@router.get("/painel", summary="Painel de métricas (HTML)", include_in_schema=False)
async def painel(request: Request) -> HTMLResponse:
    _autorizar(request)
    async with sessao() as session:
        metricas = await coletar(session)
    return HTMLResponse(_html(metricas))


def _linhas(metrica: Metrica) -> str:
    if len(metrica.amostras) == 1 and not metrica.amostras[0][0]:
        return f"<tr><td>—</td><td>{metrica.amostras[0][1]:,.0f}</td></tr>"
    return "".join(
        f"<tr><td>{escape(', '.join(rotulos.values()))}</td><td>{valor:,.0f}</td></tr>"
        for rotulos, valor in metrica.amostras
    )


def _html(metricas: list[Metrica]) -> str:
    cartoes = "".join(
        f"<section><h2>{escape(m.ajuda)}</h2><code>{m.nome}</code>"
        f"<table>{_linhas(m)}</table></section>"
        for m in metricas
        if not m.nome.endswith("_timestamp_seconds")
    )
    horarios = "".join(
        f"<li>{escape(m.ajuda)} "
        + (
            escape(
                agora().fromtimestamp(m.amostras[0][1], tz=agora().tzinfo).strftime(
                    "%d/%m/%Y %H:%M UTC"
                )
            )
            if m.amostras[0][1]
            else "nunca"
        )
        + "</li>"
        for m in metricas
        if m.nome.endswith("_timestamp_seconds")
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oráculo — métricas</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0b0e17;color:#e2e8f0;margin:0;padding:24px}}
h1{{font-size:20px;margin:0 0 16px}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}
section{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:12px}}
h2{{font-size:13px;margin:0 0 4px}} code{{font-size:11px;color:#64748b}}
table{{width:100%;margin-top:8px;font-size:13px;border-collapse:collapse}}
td{{padding:2px 0}} td:last-child{{text-align:right;font-variant-numeric:tabular-nums}}
ul{{font-size:13px;color:#94a3b8}}
</style></head>
<body><h1>Oráculo — painel de métricas</h1><ul>{horarios}</ul><main>{cartoes}</main></body></html>
"""
