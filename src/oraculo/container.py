"""Composição das dependências da aplicação.

Um único lugar constrói cache, integrações e serviços; bot, API e scripts
recebem o mesmo container, garantindo que todos apliquem exatamente as mesmas
regras de negócio (RN-008 em particular).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from oraculo.config import Settings, get_settings
from oraculo.integrations.cache import Cache, criar_cache
from oraculo.integrations.email_canal import CanalEmail
from oraculo.integrations.google_calendar import AgendaExterna, criar_agenda_externa
from oraculo.logging_config import get_logger
from oraculo.services.agenda_service import AgendaService
from oraculo.services.dracmas_service import DracmasService
from oraculo.services.notificacao_service import NotificacaoService
from oraculo.services.promocao_service import PromocaoService, SincronizadorCargos
from oraculo.services.ranking_service import RankingService
from oraculo.services.xp_service import XpService

log = get_logger(__name__)


@dataclass(slots=True)
class Container:
    """Serviços prontos para uso, já ligados às integrações configuradas."""

    settings: Settings
    cache: Cache
    agenda_externa: AgendaExterna
    notificacoes: NotificacaoService
    promocoes: PromocaoService
    xp: XpService
    ranking: RankingService
    agenda: AgendaService
    dracmas: DracmasService
    _fechados: bool = field(default=False, repr=False)

    @classmethod
    def criar(
        cls,
        settings: Settings | None = None,
        *,
        sincronizador_cargos: SincronizadorCargos | None = None,
    ) -> Container:
        cfg = settings or get_settings()
        cache = criar_cache(cfg)
        agenda_externa = criar_agenda_externa(cfg)

        notificacoes = NotificacaoService()
        if cfg.email_enabled:
            notificacoes.registrar_canal(CanalEmail(cfg))

        promocoes = PromocaoService(sincronizador=sincronizador_cargos)
        return cls(
            settings=cfg,
            cache=cache,
            agenda_externa=agenda_externa,
            notificacoes=notificacoes,
            promocoes=promocoes,
            xp=XpService(promocoes=promocoes, somente_leitura=cfg.xp_somente_leitura),
            ranking=RankingService(cache=cache, settings=cfg),
            agenda=AgendaService(agenda_externa=agenda_externa),
            dracmas=DracmasService(),
        )

    async def fechar(self) -> None:
        if self._fechados:
            return
        await self.cache.fechar()
        self._fechados = True
        log.info("Container encerrado.")
