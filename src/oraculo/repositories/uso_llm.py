"""Acesso à tabela `uso_llm_diario` (custo estimado da API do Claude por dia e modelo)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import UsoLlmDia
from oraculo.domain.custo_llm import UsoLLM


async def somar(session: AsyncSession, dia: str, uso: UsoLLM, microdolares: int) -> None:
    linha = await session.scalar(
        select(UsoLlmDia).where(UsoLlmDia.dia == dia, UsoLlmDia.modelo == uso.modelo)
    )
    if linha is None:
        linha = UsoLlmDia(
            dia=dia,
            modelo=uso.modelo,
            chamadas=0,
            tokens_entrada=0,
            tokens_saida=0,
            tokens_cache_escrita=0,
            tokens_cache_leitura=0,
            custo_microdolares=0,
        )
        session.add(linha)
    linha.chamadas += 1
    linha.tokens_entrada += max(uso.entrada, 0)
    linha.tokens_saida += max(uso.saida, 0)
    linha.tokens_cache_escrita += max(uso.cache_escrita, 0)
    linha.tokens_cache_leitura += max(uso.cache_leitura, 0)
    linha.custo_microdolares += max(microdolares, 0)
    await session.flush()


async def microdolares_do_dia(session: AsyncSession, dia: str) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(UsoLlmDia.custo_microdolares), 0)).where(UsoLlmDia.dia == dia)
    )
    return int(total or 0)


async def microdolares_do_mes(session: AsyncSession, mes: str) -> int:
    """`mes` no formato `AAAA-MM`."""
    total = await session.scalar(
        select(func.coalesce(func.sum(UsoLlmDia.custo_microdolares), 0)).where(
            UsoLlmDia.dia.like(f"{mes}-%")
        )
    )
    return int(total or 0)
