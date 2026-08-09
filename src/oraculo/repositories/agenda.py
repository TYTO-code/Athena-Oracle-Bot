"""Repositório de agendamentos e presenças — RF-007, RF-008, RF-009."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from oraculo.db.base import agora
from oraculo.db.models import (
    Agendamento,
    Membro,
    Presenca,
    StatusAgendamento,
    StatusPresenca,
    TipoAgendamento,
)
from oraculo.domain.errors import RecursoNaoEncontradoError


async def criar(
    session: AsyncSession,
    *,
    tipo: TipoAgendamento,
    titulo: str,
    inicio_em: datetime,
    organizador: Membro,
    descricao: str | None = None,
    local: str | None = None,
    fim_em: datetime | None = None,
    guild_id: int | None = None,
) -> Agendamento:
    agendamento = Agendamento(
        tipo=tipo,
        titulo=titulo.strip(),
        descricao=descricao,
        local=local,
        inicio_em=inicio_em,
        fim_em=fim_em,
        organizador_id=organizador.id,
        guild_id=guild_id,
    )
    session.add(agendamento)
    await session.flush()
    return agendamento


async def obter(session: AsyncSession, agendamento_id: int) -> Agendamento:
    agendamento = await session.get(Agendamento, agendamento_id)
    if agendamento is None:
        raise RecursoNaoEncontradoError("Agendamento", agendamento_id)
    return agendamento


async def obter_com_presencas(session: AsyncSession, agendamento_id: int) -> Agendamento:
    resultado = await session.execute(
        select(Agendamento)
        .options(selectinload(Agendamento.presencas).selectinload(Presenca.membro))
        .where(Agendamento.id == agendamento_id)
    )
    agendamento = resultado.scalar_one_or_none()
    if agendamento is None:
        raise RecursoNaoEncontradoError("Agendamento", agendamento_id)
    return agendamento


async def listar_proximos(
    session: AsyncSession,
    *,
    tipo: TipoAgendamento | None = None,
    guild_id: int | None = None,
    a_partir_de: datetime | None = None,
    limite: int = 10,
) -> list[Agendamento]:
    """Agenda futura, ignorando cancelados (RN-010 mantém a linha no banco)."""
    consulta = (
        select(Agendamento)
        .where(
            Agendamento.status == StatusAgendamento.AGENDADO,
            Agendamento.inicio_em >= (a_partir_de or agora()),
        )
        .order_by(Agendamento.inicio_em.asc())
        .limit(limite)
    )
    if tipo is not None:
        consulta = consulta.where(Agendamento.tipo == tipo)
    if guild_id is not None:
        consulta = consulta.where(Agendamento.guild_id == guild_id)
    return list((await session.execute(consulta)).scalars())


async def convidar(session: AsyncSession, *, agendamento: Agendamento, membro: Membro) -> Presenca:
    """Cria o convite (RSVP pendente) ou devolve o existente — idempotente."""
    existente = await buscar_presenca(session, agendamento_id=agendamento.id, membro_id=membro.id)
    if existente is not None:
        return existente
    presenca = Presenca(
        agendamento_id=agendamento.id,
        membro_id=membro.id,
        status=StatusPresenca.PENDENTE,
    )
    session.add(presenca)
    await session.flush()
    return presenca


async def buscar_presenca(
    session: AsyncSession, *, agendamento_id: int, membro_id: int
) -> Presenca | None:
    resultado = await session.execute(
        select(Presenca).where(
            Presenca.agendamento_id == agendamento_id,
            Presenca.membro_id == membro_id,
        )
    )
    return resultado.scalar_one_or_none()


async def listar_presencas(
    session: AsyncSession, *, agendamento_id: int, status: StatusPresenca | None = None
) -> list[Presenca]:
    consulta = (
        select(Presenca)
        .options(selectinload(Presenca.membro))
        .where(Presenca.agendamento_id == agendamento_id)
    )
    if status is not None:
        consulta = consulta.where(Presenca.status == status)
    return list((await session.execute(consulta)).scalars())


async def contar_por_status(session: AsyncSession, *, agendamento_id: int) -> dict[str, int]:
    presencas = await listar_presencas(session, agendamento_id=agendamento_id)
    contagem = {status.value: 0 for status in StatusPresenca}
    for presenca in presencas:
        contagem[StatusPresenca(presenca.status).value] += 1
    return contagem
