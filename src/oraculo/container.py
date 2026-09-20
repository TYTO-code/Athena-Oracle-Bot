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
from oraculo.integrations.llm import criar_cliente_llm
from oraculo.integrations.plataforma import FonteProjetosDoMembro, criar_fonte_membros
from oraculo.integrations.projetos_db import BaseDeProjetos, criar_base_de_projetos
from oraculo.integrations.regras_corpus import carregar_corpus
from oraculo.logging_config import get_logger
from oraculo.services.agenda_service import AgendaService
from oraculo.services.dracmas_service import DracmasService
from oraculo.services.notificacao_service import NotificacaoService
from oraculo.services.pergunta_service import PerguntaService
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
    #: RN-017 — `None` quando `/perguntar` não está configurado (sem chave de API).
    perguntas: PerguntaService | None = None
    _projetos: BaseDeProjetos | None = field(default=None, repr=False)
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

        # RN-017 — `/perguntar` só existe com chave de API; regulamento e base de
        # projetos são opcionais e degradam de forma independente.
        cliente_llm = criar_cliente_llm(cfg)
        projetos = criar_base_de_projetos(cfg) if cliente_llm is not None else None
        perguntas: PerguntaService | None = None
        if cliente_llm is not None:
            fonte = criar_fonte_membros(cfg)
            perguntas = PerguntaService(
                cliente=cliente_llm,
                corpus=carregar_corpus(cfg),
                projetos=projetos,
                # A mesma fonte do Firestore sabe ler projetos de um membro; se a
                # plataforma não estiver configurada, ninguém tem projeto algum.
                fonte_projetos_do_membro=(
                    fonte if isinstance(fonte, FonteProjetosDoMembro) else None
                ),
                cache=cache,
                limite_hora=cfg.pergunta_limite_hora,
            )

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
            perguntas=perguntas,
            _projetos=projetos,
        )

    async def fechar(self) -> None:
        if self._fechados:
            return
        await self.cache.fechar()
        if self._projetos is not None:
            await self._projetos.fechar()
        self._fechados = True
        log.info("Container encerrado.")
