"""Texto da DM de alerta a partir do webhook do Grafana (D15). Puro.

O Grafana manda `{status, alerts: [{status, labels, annotations}], ...}`. A DM diz o que disparou
(ou voltou ao normal) com o resumo escrito na regra. Nada do payload além de nome, resumo e
estado entra no texto: o resto (URLs internas, valores brutos) fica no Grafana.
"""

from __future__ import annotations

from typing import Any

LIMITE_ALERTAS = 10
LIMITE_TEXTO = 1900  # a DM do Discord aceita 2000


def _texto(valor: object, limite: int = 300) -> str:
    texto = " ".join(str(valor or "").split())
    return texto[: limite - 1] + "…" if len(texto) > limite else texto


def formatar_alerta(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    alertas = [a for a in payload.get("alerts") or [] if isinstance(a, dict)]
    if not alertas:
        return None

    linhas: list[str] = []
    for alerta in alertas[:LIMITE_ALERTAS]:
        rotulos = alerta.get("labels") if isinstance(alerta.get("labels"), dict) else {}
        notas = alerta.get("annotations") if isinstance(alerta.get("annotations"), dict) else {}
        nome = _texto(rotulos.get("alertname") or "alerta", 80)
        resumo = _texto(notas.get("summary") or notas.get("description") or "")
        resolvido = str(alerta.get("status") or payload.get("status")) == "resolved"
        icone = "✅ Resolvido" if resolvido else "🚨 Alerta"
        linhas.append(f"{icone}: **{nome}**" + (f" — {resumo}" if resumo else ""))
    if len(alertas) > LIMITE_ALERTAS:
        linhas.append(f"… e mais {len(alertas) - LIMITE_ALERTAS}. Veja no Grafana.")

    texto = "\n".join(linhas)
    return texto[: LIMITE_TEXTO - 1] + "…" if len(texto) > LIMITE_TEXTO else texto
