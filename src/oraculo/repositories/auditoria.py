"""Repositório do log de auditoria (`audit_log`) — RF-012 / RNF-004.

Append-only por construção (RN-010).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import Membro, OrigemAcao, RegistroAuditoria


async def registrar(
    session: AsyncSession,
    *,
    acao: str,
    resumo: str,
    ator: Membro | None = None,
    ator_descricao: str | None = None,
    alvo_tipo: str | None = None,
    alvo_id: str | int | None = None,
    dados: dict | None = None,
    origem: OrigemAcao = OrigemAcao.SISTEMA,
    guild_id: int | None = None,
) -> RegistroAuditoria:
    registro = RegistroAuditoria(
        acao=acao,
        resumo=resumo[:500],
        ator_id=ator.id if ator else None,
        ator_descricao=ator_descricao or (ator.nome_exibicao if ator else "sistema"),
        alvo_tipo=alvo_tipo,
        alvo_id=str(alvo_id) if alvo_id is not None else None,
        dados=dados,
        origem=origem,
        guild_id=guild_id,
    )
    session.add(registro)
    await session.flush()
    return registro


async def listar(
    session: AsyncSession,
    *,
    acao: str | None = None,
    alvo_tipo: str | None = None,
    alvo_id: str | int | None = None,
    desde: datetime | None = None,
    limite: int = 50,
) -> list[RegistroAuditoria]:
    consulta = (
        select(RegistroAuditoria)
        .order_by(RegistroAuditoria.criado_em.desc(), RegistroAuditoria.id.desc())
        .limit(limite)
    )
    if acao:
        consulta = consulta.where(RegistroAuditoria.acao == acao)
    if alvo_tipo:
        consulta = consulta.where(RegistroAuditoria.alvo_tipo == alvo_tipo)
    if alvo_id is not None:
        consulta = consulta.where(RegistroAuditoria.alvo_id == str(alvo_id))
    if desde is not None:
        consulta = consulta.where(RegistroAuditoria.criado_em >= desde)
    return list((await session.execute(consulta)).scalars())
