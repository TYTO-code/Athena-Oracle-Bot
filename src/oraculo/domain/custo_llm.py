"""Custo estimado das chamadas ao Claude (RN-017, freio de custo; observabilidade com Grafana).

Puro: recebe o uso que a API devolve (`usage`) e devolve dólares. A conta é uma estimativa para
alerta e teto, não uma fatura: a fatura real é a do Console da Anthropic.

Preço por milhão de tokens (tabela pública de 2026-11). Escrita no cache custa 1,25× a entrada
(TTL de 5 minutos, o que `/perguntar` usa) e leitura do cache custa 0,1× a entrada. Modelo que não
está na tabela é cobrado pelo preço mais alto da tabela: na dúvida, o teto dispara antes, nunca
depois.
"""

from __future__ import annotations

from dataclasses import dataclass

#: (entrada, saída) em US$ por milhão de tokens.
PRECOS_POR_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-5-5": (4.00, 20.00),
}

#: Preço usado para modelo desconhecido: o mais caro da tabela (conservador).
PRECO_DESCONHECIDO: tuple[float, float] = (
    max(p[0] for p in PRECOS_POR_MTOK.values()),
    max(p[1] for p in PRECOS_POR_MTOK.values()),
)

MULTIPLICADOR_CACHE_ESCRITA = 1.25
MULTIPLICADOR_CACHE_LEITURA = 0.10


@dataclass(frozen=True, slots=True)
class UsoLLM:
    """Tokens de uma chamada, como a API devolve em `usage`."""

    modelo: str
    entrada: int = 0
    saida: int = 0
    cache_escrita: int = 0
    cache_leitura: int = 0


def preco_do_modelo(modelo: str) -> tuple[float, float]:
    """Preço (entrada, saída) por milhão; aceita sufixo de data (`claude-haiku-4-5-2025...`)."""
    if modelo in PRECOS_POR_MTOK:
        return PRECOS_POR_MTOK[modelo]
    candidatos = [m for m in PRECOS_POR_MTOK if modelo.startswith(m + "-")]
    if candidatos:
        return PRECOS_POR_MTOK[max(candidatos, key=len)]
    return PRECO_DESCONHECIDO


def custo_usd(uso: UsoLLM) -> float:
    entrada, saida = preco_do_modelo(uso.modelo)
    total = (
        max(uso.entrada, 0) * entrada
        + max(uso.cache_escrita, 0) * entrada * MULTIPLICADOR_CACHE_ESCRITA
        + max(uso.cache_leitura, 0) * entrada * MULTIPLICADOR_CACHE_LEITURA
        + max(uso.saida, 0) * saida
    )
    return total / 1_000_000


def orcamento_esgotado(
    custo_hoje: float, custo_mes: float, teto_diario: float, orcamento_mensal: float
) -> str | None:
    """Motivo para recusar uma nova chamada, ou `None` se ainda cabe.

    Teto zero ou negativo desliga aquele freio (o outro continua valendo).
    """
    if teto_diario > 0 and custo_hoje >= teto_diario:
        return "diario"
    if orcamento_mensal > 0 and custo_mes >= orcamento_mensal:
        return "mensal"
    return None
