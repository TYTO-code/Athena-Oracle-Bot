"""Composição das dependências da aplicação.

Um único lugar constrói cache, integrações e serviços; bot, API e scripts
recebem o mesmo container, garantindo que todos apliquem exatamente as mesmas
regras de negócio (RN-008 em particular).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from oraculo.config import Settings, get_settings
from oraculo.integrations.cache import Cache, criar_cache
from oraculo.integrations.email_canal import CanalEmail
from oraculo.integrations.google_calendar import AgendaExterna, criar_agenda_externa
from oraculo.integrations.llm import criar_cliente_llm
from oraculo.integrations.plataforma import (
    FonteBuscaPorDiscord,
    FonteProjetosDoMembro,
    criar_fonte_membros,
)
from oraculo.integrations.projetos_db import BaseDeProjetos, criar_base_de_projetos
from oraculo.integrations.regras_corpus import carregar_corpus
from oraculo.logging_config import get_logger
from oraculo.services.acesso_service import AcessoService
from oraculo.services.agenda_service import AgendaService
from oraculo.services.comunicado_service import ComunicadoService
from oraculo.services.importacao_service import ImportacaoService
from oraculo.services.notificacao_service import NotificacaoService
from oraculo.services.pergunta_service import PerguntaService
from oraculo.services.promocao_service import PromocaoService, SincronizadorCargos
from oraculo.services.ranking_service import RankingService

log = get_logger(__name__)


@dataclass(slots=True)
class Container:
    """Serviços prontos para uso, já ligados às integrações configuradas."""

    settings: Settings
    cache: Cache
    agenda_externa: AgendaExterna
    notificacoes: NotificacaoService
    #: RN-020 — só entra quem tem cadastro de Clube na TYTO.club.
    acesso: AcessoService
    promocoes: PromocaoService
    ranking: RankingService
    agenda: AgendaService
    #: RF-015 — o publicador Discord só é registrado quando o cliente existe
    #: (ver `bot/cogs/comunicados.py`); até lá o serviço só programa e cancela.
    comunicados: ComunicadoService
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

        # RN-020 — a mesma fonte alimenta `/perguntar` (projetos) e o acesso ao
        # bot (consulta pontual de quem acabou de se cadastrar).
        fonte_membros = criar_fonte_membros(cfg)
        acesso = AcessoService(
            fonte_membros if isinstance(fonte_membros, FonteBuscaPorDiscord) else None,
            (
                ImportacaoService(
                    fonte_membros, mapa_campos=cfg.firebase_campos, promocoes=promocoes
                )
                if fonte_membros is not None
                else None
            ),
            mapa_campos=cfg.firebase_campos,
        )

        # RN-017 — `/perguntar` só existe com chave de API; regulamento e base de
        # projetos são opcionais e degradam de forma independente.
        cliente_llm = criar_cliente_llm(cfg)
        projetos = criar_base_de_projetos(cfg) if cliente_llm is not None else None
        perguntas: PerguntaService | None = None
        if cliente_llm is not None:
            fonte = fonte_membros
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
            acesso=acesso,
            promocoes=promocoes,
            ranking=RankingService(cache=cache, settings=cfg),
            agenda=AgendaService(agenda_externa=agenda_externa),
            comunicados=ComunicadoService(
                atraso_maximo=timedelta(hours=cfg.comunicados_atraso_maximo_horas)
            ),
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
