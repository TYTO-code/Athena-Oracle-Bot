"""Repositório de membros — RF-001, RF-002, RF-004."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora
from oraculo.db.models import Membro, MovimentacaoXp
from oraculo.domain.errors import RecursoNaoEncontradoError
from oraculo.domain.hierarchy import PATENTE_INICIAL


class LinhaRanking(NamedTuple):
    """Uma posição do ranking (RF-004 / UC-002)."""

    posicao: int
    membro_id: int
    nome_exibicao: str
    discord_id: int | None
    patente_slug: str
    xp: int


async def obter_por_id(session: AsyncSession, membro_id: int) -> Membro:
    membro = await session.get(Membro, membro_id)
    if membro is None:
        raise RecursoNaoEncontradoError("Membro", membro_id)
    return membro


async def buscar_por_discord_id(session: AsyncSession, discord_id: int) -> Membro | None:
    resultado = await session.execute(select(Membro).where(Membro.discord_id == discord_id))
    return resultado.scalar_one_or_none()


async def buscar_por_whatsapp(session: AsyncSession, telefone_e164: str) -> Membro | None:
    resultado = await session.execute(
        select(Membro).where(Membro.whatsapp_e164 == telefone_e164)
    )
    return resultado.scalar_one_or_none()


async def obter_ou_criar_por_discord(
    session: AsyncSession,
    *,
    discord_id: int,
    nome_exibicao: str,
    email: str | None = None,
) -> Membro:
    """RF-001 — registra o usuário no primeiro contato (auto-onboarding).

    O nome de exibição é mantido sincronizado com o Discord; XP, patente e
    cargos de um membro já existente jamais são reinicializados aqui.
    """
    membro = await buscar_por_discord_id(session, discord_id)
    if membro is not None:
        if nome_exibicao and membro.nome_exibicao != nome_exibicao:
            membro.nome_exibicao = nome_exibicao
        if email and not membro.email:
            membro.email = email
        return membro

    membro = Membro(
        discord_id=discord_id,
        nome_exibicao=nome_exibicao or str(discord_id),
        email=email,
        patente_slug=PATENTE_INICIAL.slug,
        xp=0,
    )
    session.add(membro)
    await session.flush()
    return membro


async def reativar(session: AsyncSession, membro: Membro) -> Membro:
    membro.ativo = True
    membro.desativado_em = None
    await session.flush()
    return membro


async def desativar(session: AsyncSession, membro: Membro) -> Membro:
    """RN-010 — soft-delete: o histórico do membro permanece intacto."""
    membro.ativo = False
    membro.desativado_em = agora()
    await session.flush()
    return membro


async def ranking(
    session: AsyncSession,
    *,
    limite: int = 10,
    offset: int = 0,
    desde: datetime | None = None,
    guild_id: int | None = None,
) -> list[LinhaRanking]:
    """RF-004 — ranking geral, por servidor ou por período.

    Sem `desde`, ordena pelo XP acumulado. Com `desde`, soma as movimentações
    do período em `xp_audit` — só aparecem membros com movimentação na janela,
    que é a leitura correta de "ranking do período".
    """
    if desde is None:
        consulta = (
            select(
                Membro.id,
                Membro.nome_exibicao,
                Membro.discord_id,
                Membro.patente_slug,
                Membro.xp,
            )
            .where(Membro.ativo.is_(True))
            .order_by(Membro.xp.desc(), Membro.nome_exibicao.asc())
            .limit(limite)
            .offset(offset)
        )
    else:
        total_periodo = func.coalesce(func.sum(MovimentacaoXp.quantidade), 0).label("xp_periodo")
        filtros = [MovimentacaoXp.criado_em >= desde]
        if guild_id is not None:
            filtros.append(MovimentacaoXp.guild_id == guild_id)
        consulta = (
            select(
                Membro.id,
                Membro.nome_exibicao,
                Membro.discord_id,
                Membro.patente_slug,
                total_periodo,
            )
            .join(MovimentacaoXp, MovimentacaoXp.membro_id == Membro.id)
            .where(Membro.ativo.is_(True), *filtros)
            .group_by(Membro.id, Membro.nome_exibicao, Membro.discord_id, Membro.patente_slug)
            .order_by(total_periodo.desc(), Membro.nome_exibicao.asc())
            .limit(limite)
            .offset(offset)
        )

    linhas = (await session.execute(consulta)).all()
    return [
        LinhaRanking(
            posicao=offset + indice,
            membro_id=linha[0],
            nome_exibicao=linha[1],
            discord_id=linha[2],
            patente_slug=linha[3],
            xp=int(linha[4]),
        )
        for indice, linha in enumerate(linhas, start=1)
    ]


async def posicao_no_ranking(session: AsyncSession, membro: Membro) -> int:
    """Posição do membro no ranking geral (1 = primeiro colocado) — RF-002."""
    acima = await session.scalar(
        select(func.count())
        .select_from(Membro)
        .where(Membro.ativo.is_(True), Membro.xp > membro.xp)
    )
    return int(acima or 0) + 1


async def total_ativos(session: AsyncSession) -> int:
    total = await session.scalar(
        select(func.count()).select_from(Membro).where(Membro.ativo.is_(True))
    )
    return int(total or 0)
