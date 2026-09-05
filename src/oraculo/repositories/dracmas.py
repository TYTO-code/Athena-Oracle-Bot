"""Repositório de Aldeões e do ledger de Dracmas — `DRACMAS.md` §2/§3.

Somente inserções e leituras no ledger: não existe update nem delete aqui, mesmo princípio de
`repositories/xp.py` para `xp_audit` — histórico imutável.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import Aldeao, Membro, MovimentacaoDracmas, TipoMovimentacaoDracmas


async def buscar_aldeao_por_discord(session: AsyncSession, discord_id: int) -> Aldeao | None:
    resultado = await session.execute(select(Aldeao).where(Aldeao.discord_id == discord_id))
    return resultado.scalar_one_or_none()


async def criar_aldeao(session: AsyncSession, *, discord_id: int) -> Aldeao:
    """Cria a conta de Comunidade — só deve ser chamado por `DracmasService.creditar`.

    `COMUNIDADE_E_CLUBE.md` Art. 1º §1º: um Visitante não tem onde receber Dracmas até
    ingressar ao menos na Comunidade — não existe caminho de negócio que crie um `Aldeao` sem
    que exista, na mesma operação, um crédito de Dracmas que o justifique.
    """
    aldeao = Aldeao(discord_id=discord_id, saldo_dracmas=0)
    session.add(aldeao)
    await session.flush()
    return aldeao


async def bloquear_aldeao(session: AsyncSession, aldeao: Aldeao) -> Aldeao:
    """Serializa movimentações concorrentes sobre a mesma conta (mesmo padrão de `xp_service`)."""
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        return aldeao
    resultado = await session.execute(
        select(Aldeao).where(Aldeao.id == aldeao.id).with_for_update()
    )
    return resultado.scalar_one()


async def bloquear_membro(session: AsyncSession, membro: Membro) -> Membro:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        return membro
    resultado = await session.execute(
        select(Membro).where(Membro.id == membro.id).with_for_update()
    )
    return resultado.scalar_one()


async def registrar_movimentacao(
    session: AsyncSession,
    *,
    aldeao: Aldeao | None = None,
    membro: Membro | None = None,
    tipo: TipoMovimentacaoDracmas,
    valor: int,
    saldo_anterior: int,
    saldo_posterior: int,
    motivo: str,
    origem_referencia: str | None = None,
    autor_descricao: str = "sistema",
) -> MovimentacaoDracmas:
    """Grava uma linha do ledger — exatamente um titular, `aldeao` xor `membro`."""
    if (aldeao is None) == (membro is None):
        raise ValueError("registrar_movimentacao exige exatamente um titular (aldeao xor membro).")

    movimentacao = MovimentacaoDracmas(
        aldeao_id=aldeao.id if aldeao else None,
        membro_id=membro.id if membro else None,
        tipo=tipo,
        valor=valor,
        saldo_anterior=saldo_anterior,
        saldo_posterior=saldo_posterior,
        motivo=motivo.strip(),
        origem_referencia=origem_referencia,
        autor_descricao=autor_descricao,
    )
    session.add(movimentacao)
    await session.flush()
    return movimentacao


async def historico_de_aldeao(
    session: AsyncSession, *, aldeao_id: int, limite: int = 20, offset: int = 0
) -> list[MovimentacaoDracmas]:
    consulta = (
        select(MovimentacaoDracmas)
        .where(MovimentacaoDracmas.aldeao_id == aldeao_id)
        .order_by(MovimentacaoDracmas.criado_em.desc(), MovimentacaoDracmas.id.desc())
        .limit(limite)
        .offset(offset)
    )
    return list((await session.execute(consulta)).scalars())


async def historico_de_membro(
    session: AsyncSession, *, membro_id: int, limite: int = 20, offset: int = 0
) -> list[MovimentacaoDracmas]:
    consulta = (
        select(MovimentacaoDracmas)
        .where(MovimentacaoDracmas.membro_id == membro_id)
        .order_by(MovimentacaoDracmas.criado_em.desc(), MovimentacaoDracmas.id.desc())
        .limit(limite)
        .offset(offset)
    )
    return list((await session.execute(consulta)).scalars())
