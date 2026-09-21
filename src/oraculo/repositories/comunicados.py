"""Repositório de comunicados — RF-015 / RN-018.

A única consulta com alguma sutileza é `reservar_vencidos`: ela muda o estado
das linhas que vai devolver, porque "escolher o que publicar" e "marcar que
alguém já pegou" precisam ser a mesma operação. Ver `services.comunicado_service`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora
from oraculo.db.models import Comunicado, Membro, StatusComunicado, TipoMencao
from oraculo.domain.errors import RecursoNaoEncontradoError


async def criar(
    session: AsyncSession,
    *,
    titulo: str,
    corpo: str,
    canal_id: int,
    autor: Membro,
    publicar_em: datetime,
    mencao: TipoMencao = TipoMencao.NENHUMA,
    guild_id: int | None = None,
) -> Comunicado:
    comunicado = Comunicado(
        titulo=titulo.strip(),
        corpo=corpo.strip(),
        canal_id=canal_id,
        autor_id=autor.id,
        publicar_em=publicar_em,
        mencao=mencao,
        guild_id=guild_id,
    )
    session.add(comunicado)
    await session.flush()
    return comunicado


async def obter(session: AsyncSession, comunicado_id: int) -> Comunicado:
    comunicado = await session.get(Comunicado, comunicado_id)
    if comunicado is None:
        raise RecursoNaoEncontradoError("Comunicado", comunicado_id)
    return comunicado


async def listar(
    session: AsyncSession,
    *,
    status: StatusComunicado | None = None,
    guild_id: int | None = None,
    limite: int = 10,
) -> list[Comunicado]:
    """Fila mais recente primeiro pela data de publicação.

    Sem filtro de status devolve tudo, inclusive cancelados e falhados: é
    exatamente neles que alguém precisa reparar (RN-010 os mantém no banco).
    """
    consulta = (
        select(Comunicado)
        .order_by(Comunicado.publicar_em.desc(), Comunicado.id.desc())
        .limit(limite)
    )
    if status is not None:
        consulta = consulta.where(Comunicado.status == status)
    if guild_id is not None:
        consulta = consulta.where(Comunicado.guild_id == guild_id)
    return list((await session.execute(consulta)).scalars())


async def reservar_vencidos(
    session: AsyncSession, *, momento: datetime | None = None, limite: int = 5
) -> list[Comunicado]:
    """Toma para publicação os comunicados cuja hora chegou (AGENDADO → PUBLICANDO).

    O `UPDATE ... WHERE status = 'agendado'` é a reserva: quem conseguir mudar a
    linha é quem publica. Quem chamar isto **precisa** dar commit antes de falar
    com o Discord — é o commit que torna a reserva durável e impede que um
    reinício no meio do envio vire publicação duplicada.
    """
    instante = momento or agora()

    candidatos = (
        select(Comunicado.id)
        .where(
            Comunicado.status == StatusComunicado.AGENDADO,
            Comunicado.publicar_em <= instante,
        )
        .order_by(Comunicado.publicar_em.asc())
        .limit(limite)
    )
    ids = list((await session.execute(candidatos)).scalars())
    if not ids:
        return []

    await session.execute(
        update(Comunicado)
        .where(Comunicado.id.in_(ids), Comunicado.status == StatusComunicado.AGENDADO)
        .values(status=StatusComunicado.PUBLICANDO, reservado_em=instante)
        .execution_options(synchronize_session=False),
    )

    # `populate_existing` traz de volta o que o UPDATE em massa escreveu. Sem
    # isso a sessão devolveria as instâncias com o status antigo em memória —
    # e `expire_all()` no lugar cobraria o preço em todo objeto já carregado.
    reservados = await session.execute(
        select(Comunicado)
        .where(Comunicado.id.in_(ids), Comunicado.status == StatusComunicado.PUBLICANDO)
        .order_by(Comunicado.publicar_em.asc())
        .execution_options(populate_existing=True),
    )
    return list(reservados.scalars())


async def listar_reservas_esquecidas(
    session: AsyncSession, *, limite_em: datetime
) -> list[Comunicado]:
    """Linhas presas em PUBLICANDO desde antes de `limite_em`.

    Só acontece quando o processo morre entre a reserva e a resposta do Discord.
    """
    consulta = select(Comunicado).where(
        Comunicado.status == StatusComunicado.PUBLICANDO,
        Comunicado.reservado_em < limite_em,
    )
    return list((await session.execute(consulta)).scalars())
