"""Repositório de movimentações de XP (`xp_audit`) — TD-006 / RN-005.

Somente inserções e leituras: não existe função de update ou delete aqui, e é
essa ausência que garante o histórico imutável exigido pela RN-010.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import Membro, MovimentacaoXp, OrigemAcao, TipoMovimentacaoXp


async def registrar(
    session: AsyncSession,
    *,
    membro: Membro,
    autor: Membro | None,
    autor_descricao: str,
    quantidade: int,
    saldo_anterior: int,
    saldo_posterior: int,
    motivo: str,
    origem: OrigemAcao = OrigemAcao.DISCORD,
    guild_id: int | None = None,
) -> MovimentacaoXp:
    """Grava uma linha de auditoria de XP (autor, membro, quantidade, motivo, data)."""
    movimentacao = MovimentacaoXp(
        membro_id=membro.id,
        autor_id=autor.id if autor else None,
        autor_descricao=autor_descricao,
        tipo=TipoMovimentacaoXp.CONCESSAO if quantidade > 0 else TipoMovimentacaoXp.REMOCAO,
        quantidade=quantidade,
        saldo_anterior=saldo_anterior,
        saldo_posterior=saldo_posterior,
        motivo=motivo.strip(),
        origem=origem,
        guild_id=guild_id,
    )
    session.add(movimentacao)
    await session.flush()
    return movimentacao


async def historico(
    session: AsyncSession,
    *,
    membro_id: int,
    limite: int = 20,
    offset: int = 0,
    desde: datetime | None = None,
) -> list[MovimentacaoXp]:
    """RF-003 / `/historico-xp` — movimentações mais recentes primeiro."""
    consulta = (
        select(MovimentacaoXp)
        .where(MovimentacaoXp.membro_id == membro_id)
        .order_by(MovimentacaoXp.criado_em.desc(), MovimentacaoXp.id.desc())
        .limit(limite)
        .offset(offset)
    )
    if desde is not None:
        consulta = consulta.where(MovimentacaoXp.criado_em >= desde)
    return list((await session.execute(consulta)).scalars())


async def total_movimentado(
    session: AsyncSession, *, membro_id: int, desde: datetime | None = None
) -> int:
    """Soma das movimentações — usada para conciliar `Membro.xp` com a trilha."""
    consulta = select(func.coalesce(func.sum(MovimentacaoXp.quantidade), 0)).where(
        MovimentacaoXp.membro_id == membro_id
    )
    if desde is not None:
        consulta = consulta.where(MovimentacaoXp.criado_em >= desde)
    return int(await session.scalar(consulta) or 0)


async def contar(session: AsyncSession, *, membro_id: int) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(MovimentacaoXp)
        .where(MovimentacaoXp.membro_id == membro_id)
    )
    return int(total or 0)
