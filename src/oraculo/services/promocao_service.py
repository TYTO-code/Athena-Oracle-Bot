"""Promoção automática e cargo único — UC-003 / RN-001, RN-002, RN-003.

O legado acumulava cargos porque atribuía o novo sem remover os anteriores
(TD-005). Aqui a ordem é invariável e explícita:

1. remover **todos** os cargos TYTO do membro no Discord;
2. atribuir o novo cargo;
3. registrar a promoção no histórico imutável;
4. notificar.

A sincronização com o Discord é injetada como porta (`SincronizadorCargos`),
o que mantém a regra testável sem gateway e permite que uma falha de rede no
Discord não desfaça a promoção já registrada no banco.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import Membro, OrigemAcao, Promocao
from oraculo.domain.hierarchy import Cargo, cargo_para_xp, cargo_por_slug
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria

log = get_logger(__name__)

#: Rebaixar automaticamente quando o XP cai abaixo do limiar do cargo atual.
#: O Documento Único descreve apenas a promoção (RN-002/RN-003); manter em
#: `False` evita perda de cargo por correção de lançamento. Alterar aqui caso o
#: Clube TYTO decida que a progressão é simétrica.
REBAIXAMENTO_AUTOMATICO = False


@runtime_checkable
class SincronizadorCargos(Protocol):
    """Porta de sincronização de cargos com o Discord (RF-006)."""

    async def sincronizar(
        self, *, discord_id: int, cargo: Cargo, guild_id: int | None = None
    ) -> None:
        """Remove todos os cargos TYTO do membro e atribui apenas `cargo`."""
        ...


@dataclass(slots=True)
class ResultadoPromocao:
    """Resultado da avaliação de progressão após uma mudança de XP."""

    promovido: bool
    cargo_anterior: Cargo
    cargo_atual: Cargo
    registro: Promocao | None = None
    sincronizado: bool = False
    erro_sincronizacao: str | None = None


class PromocaoService:
    """Avalia e aplica mudanças de cargo decorrentes do XP."""

    def __init__(self, sincronizador: SincronizadorCargos | None = None) -> None:
        self._sincronizador = sincronizador

    async def avaliar(
        self,
        session: AsyncSession,
        membro: Membro,
        *,
        autor_descricao: str = "sistema",
        origem: OrigemAcao = OrigemAcao.SISTEMA,
        guild_id: int | None = None,
    ) -> ResultadoPromocao:
        """RN-002 — verifica se o XP atual muda o cargo e aplica a mudança."""
        cargo_atual = cargo_por_slug(membro.cargo_slug)
        cargo_alvo = cargo_para_xp(membro.xp)

        if not self._deve_mudar(cargo_atual, cargo_alvo):
            return ResultadoPromocao(False, cargo_atual, cargo_atual)

        return await self.aplicar(
            session,
            membro,
            cargo_novo=cargo_alvo,
            automatica=True,
            autor_descricao=autor_descricao,
            motivo="Progressão automática por XP (RN-002)",
            origem=origem,
            guild_id=guild_id,
        )

    async def aplicar(
        self,
        session: AsyncSession,
        membro: Membro,
        *,
        cargo_novo: Cargo,
        automatica: bool,
        autor_descricao: str,
        motivo: str,
        origem: OrigemAcao = OrigemAcao.SISTEMA,
        guild_id: int | None = None,
    ) -> ResultadoPromocao:
        """RN-001 / RN-003 — troca o cargo único, registra e sincroniza."""
        cargo_anterior = cargo_por_slug(membro.cargo_slug)

        # RN-001: uma única coluna de cargo — não há como acumular (TD-005).
        membro.cargo_slug = cargo_novo.slug

        registro = Promocao(
            membro_id=membro.id,
            cargo_anterior=cargo_anterior.slug,
            cargo_novo=cargo_novo.slug,
            xp_no_momento=membro.xp,
            automatica=automatica,
            autor_descricao=autor_descricao,
            motivo=motivo,
        )
        session.add(registro)
        await session.flush()

        sincronizado, erro = await self._sincronizar(membro, cargo_novo, guild_id)
        registro.sincronizado_discord = sincronizado
        registro.erro_sincronizacao = erro

        await auditoria.registrar(
            session,
            acao="promocao.aplicada" if cargo_novo > cargo_anterior else "cargo.rebaixado",
            resumo=(
                f"{membro.nome_exibicao}: {cargo_anterior.nome} → {cargo_novo.nome} "
                f"({membro.xp} XP)"
            ),
            ator_descricao=autor_descricao,
            alvo_tipo="membro",
            alvo_id=membro.id,
            dados={
                "cargo_anterior": cargo_anterior.slug,
                "cargo_novo": cargo_novo.slug,
                "xp": membro.xp,
                "automatica": automatica,
                "sincronizado_discord": sincronizado,
            },
            origem=origem,
            guild_id=guild_id,
        )

        log.info(
            "Cargo alterado: membro=%s %s → %s (xp=%d, sync=%s)",
            membro.id,
            cargo_anterior.slug,
            cargo_novo.slug,
            membro.xp,
            sincronizado,
        )
        return ResultadoPromocao(
            promovido=True,
            cargo_anterior=cargo_anterior,
            cargo_atual=cargo_novo,
            registro=registro,
            sincronizado=sincronizado,
            erro_sincronizacao=erro,
        )

    @staticmethod
    def _deve_mudar(cargo_atual: Cargo, cargo_alvo: Cargo) -> bool:
        if cargo_alvo.ordem > cargo_atual.ordem:
            return True
        if cargo_alvo.ordem < cargo_atual.ordem:
            # Cargos não automáticos (Administrador) nunca são perdidos por XP.
            return REBAIXAMENTO_AUTOMATICO and cargo_atual.automatico
        return False

    async def _sincronizar(
        self, membro: Membro, cargo: Cargo, guild_id: int | None
    ) -> tuple[bool, str | None]:
        """Aplica o cargo no Discord; falha de integração não anula a promoção."""
        if self._sincronizador is None or membro.discord_id is None:
            return False, None if self._sincronizador is None else "membro sem discord_id"
        try:
            await self._sincronizador.sincronizar(
                discord_id=membro.discord_id, cargo=cargo, guild_id=guild_id
            )
        except Exception as exc:  # noqa: BLE001 — registrado para reprocessamento
            log.exception("Falha ao sincronizar cargo no Discord (membro=%s)", membro.id)
            return False, f"{type(exc).__name__}: {exc}"[:500]
        return True, None
