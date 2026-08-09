"""Ranking e perfil — UC-002 / RF-002, RF-004.

O ranking é a consulta mais chamada do bot; por isso passa por cache com TTL
curto (US-404 / RNF-001). A invalidação ocorre em toda movimentação de XP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.config import Settings, get_settings
from oraculo.db.base import agora
from oraculo.db.models import Membro
from oraculo.domain.hierarchy import Cargo, cargo_por_slug, proximo_cargo, xp_faltante
from oraculo.integrations.cache import Cache, CacheMemoria
from oraculo.repositories import membros as repo_membros
from oraculo.repositories.membros import LinhaRanking

PREFIXO_CACHE = "ranking:"

PERIODOS = {
    "semana": timedelta(days=7),
    "mes": timedelta(days=30),
    "trimestre": timedelta(days=90),
}


@dataclass(slots=True)
class Perfil:
    """Dados de `/perfil` — RF-002."""

    membro: Membro
    cargo: Cargo
    proximo: Cargo | None
    xp_para_proximo: int | None
    posicao: int
    total_membros: int

    @property
    def no_topo(self) -> bool:
        return self.proximo is None


class RankingService:
    def __init__(self, cache: Cache | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._cache = cache or CacheMemoria()

    async def perfil(self, session: AsyncSession, membro: Membro) -> Perfil:
        """RF-002 — cargo, XP atual, próximo cargo, XP necessário e ranking."""
        cargo = cargo_por_slug(membro.cargo_slug)
        return Perfil(
            membro=membro,
            cargo=cargo,
            proximo=proximo_cargo(cargo),
            xp_para_proximo=xp_faltante(membro.xp, cargo),
            posicao=await repo_membros.posicao_no_ranking(session, membro),
            total_membros=await repo_membros.total_ativos(session),
        )

    async def ranking(
        self,
        session: AsyncSession,
        *,
        limite: int = 10,
        periodo: str | None = None,
        guild_id: int | None = None,
    ) -> list[LinhaRanking]:
        """RF-004 / UC-002 — geral, por servidor ou por período."""
        limite = max(1, min(limite, 50))
        chave = f"{PREFIXO_CACHE}{periodo or 'geral'}:{guild_id or 'todos'}:{limite}"

        if (em_cache := await self._cache.obter(chave)) is not None:
            return [LinhaRanking(*linha) for linha in em_cache]

        desde = None
        if periodo:
            janela = PERIODOS.get(periodo.lower())
            if janela is None:
                validos = ", ".join(PERIODOS)
                raise ValueError(f"Período inválido: {periodo!r}. Use um de: {validos}.")
            desde = agora() - janela

        linhas = await repo_membros.ranking(
            session, limite=limite, desde=desde, guild_id=guild_id
        )
        await self._cache.definir(
            chave, [list(linha) for linha in linhas], ttl=self._settings.ranking_cache_ttl
        )
        return linhas

    async def invalidar(self) -> None:
        """Chamada após qualquer movimentação de XP para evitar ranking velho."""
        await self._cache.invalidar(PREFIXO_CACHE)
