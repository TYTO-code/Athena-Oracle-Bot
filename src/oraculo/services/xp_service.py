"""Gestão de XP — UC-001 / RF-003, RN-004, RN-005, RN-010.

Cada operação é uma transação única que faz, nesta ordem:

1. valida permissão do autor (RN-004/RN-008) e o motivo (RN-005);
2. bloqueia a linha do membro (evita a race condition do legado, TD-002);
3. atualiza o saldo e grava a linha de auditoria com autor/motivo (TD-006);
4. dispara a avaliação de promoção (UC-003).

Se qualquer passo falhar, o rollback desfaz tudo: nunca existe XP alterado sem
trilha de auditoria correspondente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import Membro, MovimentacaoXp, OrigemAcao
from oraculo.domain.errors import (
    AutorNaoIdentificadoError,
    MotivoObrigatorioError,
    QuantidadeInvalidaError,
    SaldoInalteradoError,
)
from oraculo.domain.hierarchy import Cargo, cargo_por_slug
from oraculo.domain.permissions import Acao, exigir
from oraculo.logging_config import get_logger
from oraculo.repositories import xp as repo_xp
from oraculo.services.promocao_service import PromocaoService, ResultadoPromocao

log = get_logger(__name__)

MOTIVO_MIN_CARACTERES = 3
XP_MAXIMO_POR_OPERACAO = 100_000


@dataclass(slots=True)
class ResultadoXp:
    """Retorno de uma movimentação de XP, pronto para virar embed/resposta."""

    membro: Membro
    movimentacao: MovimentacaoXp
    saldo_anterior: int
    saldo_atual: int
    promocao: ResultadoPromocao

    @property
    def promovido(self) -> bool:
        return self.promocao.promovido


class XpService:
    """Casos de uso de concessão, remoção e consulta de XP."""

    def __init__(self, promocoes: PromocaoService | None = None) -> None:
        self._promocoes = promocoes or PromocaoService()

    # -- Comandos ----------------------------------------------------------

    async def conceder(
        self,
        session: AsyncSession,
        *,
        membro: Membro,
        quantidade: int,
        motivo: str,
        autor: Membro | None,
        autor_descricao: str | None = None,
        origem: OrigemAcao = OrigemAcao.DISCORD,
        guild_id: int | None = None,
    ) -> ResultadoXp:
        """UC-001 — adiciona XP ao membro (quantidade positiva)."""
        return await self._movimentar(
            session,
            membro=membro,
            delta=self._validar_quantidade(quantidade),
            motivo=motivo,
            autor=autor,
            autor_descricao=autor_descricao,
            acao=Acao.CONCEDER_XP,
            origem=origem,
            guild_id=guild_id,
        )

    async def remover(
        self,
        session: AsyncSession,
        *,
        membro: Membro,
        quantidade: int,
        motivo: str,
        autor: Membro | None,
        autor_descricao: str | None = None,
        origem: OrigemAcao = OrigemAcao.DISCORD,
        guild_id: int | None = None,
    ) -> ResultadoXp:
        """RF-003 — remove XP do membro. O saldo nunca fica negativo."""
        return await self._movimentar(
            session,
            membro=membro,
            delta=-self._validar_quantidade(quantidade),
            motivo=motivo,
            autor=autor,
            autor_descricao=autor_descricao,
            acao=Acao.REMOVER_XP,
            origem=origem,
            guild_id=guild_id,
        )

    # -- Consultas ---------------------------------------------------------

    async def historico(
        self,
        session: AsyncSession,
        *,
        membro: Membro,
        solicitante_cargo: Cargo | None = None,
        limite: int = 20,
        desde: datetime | None = None,
    ) -> list[MovimentacaoXp]:
        """`/historico-xp` — RF-003 / RF-012.

        `solicitante_cargo` é opcional apenas para consultas internas do próprio
        sistema; qualquer chamada vinda de usuário deve informá-lo (RN-008).
        """
        if solicitante_cargo is not None:
            exigir(solicitante_cargo, Acao.VER_HISTORICO_XP)
        return await repo_xp.historico(
            session, membro_id=membro.id, limite=limite, desde=desde
        )

    async def conciliar(self, session: AsyncSession, *, membro: Membro) -> tuple[int, int]:
        """Compara o saldo materializado com a soma da trilha (RN-005/RN-010).

        Divergência indica escrita fora dos serviços e deve ser investigada;
        a trilha `xp_audit` é a fonte de verdade.
        """
        soma = await repo_xp.total_movimentado(session, membro_id=membro.id)
        return membro.xp, soma

    # -- Interno -----------------------------------------------------------

    async def _movimentar(
        self,
        session: AsyncSession,
        *,
        membro: Membro,
        delta: int,
        motivo: str,
        autor: Membro | None,
        autor_descricao: str | None,
        acao: Acao,
        origem: OrigemAcao,
        guild_id: int | None,
    ) -> ResultadoXp:
        motivo_limpo = self._validar_motivo(motivo)

        # RN-004 / RN-008 — permissão antes de qualquer escrita.
        if autor is not None:
            exigir(cargo_por_slug(autor.cargo_slug), acao)
        elif origem is not OrigemAcao.SISTEMA:
            # Ação sem autor identificado só é aceita como automação do sistema.
            raise AutorNaoIdentificadoError(acao.value)

        membro = await self._bloquear(session, membro)

        saldo_anterior = membro.xp
        saldo_posterior = max(0, saldo_anterior + delta)
        delta_efetivo = saldo_posterior - saldo_anterior

        if delta_efetivo == 0:
            # Remover XP de quem já está zerado não gera linha de auditoria vazia.
            raise SaldoInalteradoError(membro.nome_exibicao, saldo_anterior)

        membro.xp = saldo_posterior

        movimentacao = await repo_xp.registrar(
            session,
            membro=membro,
            autor=autor,
            autor_descricao=autor_descricao or (autor.nome_exibicao if autor else "sistema"),
            quantidade=delta_efetivo,
            saldo_anterior=saldo_anterior,
            saldo_posterior=saldo_posterior,
            motivo=motivo_limpo,
            origem=origem,
            guild_id=guild_id,
        )

        promocao = await self._promocoes.avaliar(
            session,
            membro,
            autor_descricao=movimentacao.autor_descricao,
            origem=origem,
            guild_id=guild_id,
        )

        log.info(
            "XP %+d para membro=%s por %s (motivo=%r, saldo %d → %d)",
            delta_efetivo,
            membro.id,
            movimentacao.autor_descricao,
            motivo_limpo,
            saldo_anterior,
            saldo_posterior,
        )

        return ResultadoXp(
            membro=membro,
            movimentacao=movimentacao,
            saldo_anterior=saldo_anterior,
            saldo_atual=saldo_posterior,
            promocao=promocao,
        )

    @staticmethod
    async def _bloquear(session: AsyncSession, membro: Membro) -> Membro:
        """Serializa movimentações concorrentes sobre o mesmo membro (TD-002).

        `SELECT ... FOR UPDATE` no PostgreSQL; no SQLite a própria transação de
        escrita já serializa, e o dialeto ignora a cláusula.
        """
        if session.bind is not None and session.bind.dialect.name == "sqlite":
            return membro
        resultado = await session.execute(
            select(Membro).where(Membro.id == membro.id).with_for_update()
        )
        return resultado.scalar_one()

    @staticmethod
    def _validar_motivo(motivo: str) -> str:
        """RN-005 — motivo obrigatório e significativo."""
        limpo = (motivo or "").strip()
        if len(limpo) < MOTIVO_MIN_CARACTERES:
            raise MotivoObrigatorioError()
        return limpo[:500]

    @staticmethod
    def _validar_quantidade(quantidade: int) -> int:
        if not isinstance(quantidade, int) or quantidade <= 0:
            raise QuantidadeInvalidaError(quantidade)
        if quantidade > XP_MAXIMO_POR_OPERACAO:
            raise QuantidadeInvalidaError(quantidade)
        return quantidade
