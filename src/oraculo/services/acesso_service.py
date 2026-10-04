"""Acesso ao bot — RN-020: só quem tem cadastro de membro na TYTO.club.

O banco do bot é um espelho da plataforma, atualizado a cada ciclo de
sincronização. Quem acabou de preencher o ID do Discord no perfil ainda não está
nele; para não fazê-lo esperar horas, o acesso faz **uma consulta pontual** à
plataforma quando o membro não é encontrado.

Duas defesas contra abuso, já que qualquer pessoa no servidor pode rodar um
comando e disparar essa consulta:

* **cache negativo** — um ID recusado não volta a ser consultado por
  `ttl_negativo` segundos, então repetir o comando não gera leituras no
  Firestore;
* **nunca cria registro de quem não é elegível** — só `ImportacaoService`
  grava, e só para quem passa em `MembroExterno.elegivel`.

Nada aqui escreve na plataforma (RN-021).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import Membro
from oraculo.domain.errors import NaoCadastradoError
from oraculo.integrations.plataforma import FonteBuscaPorDiscord, normalizar
from oraculo.logging_config import get_logger
from oraculo.repositories import membros as repo_membros
from oraculo.services.importacao_service import ImportacaoService

log = get_logger(__name__)

LIMITE_CACHE_NEGATIVO = 2000
"""Teto de entradas: um servidor aberto não pode inflar a memória do bot."""


class AcessoService:
    def __init__(
        self,
        fonte: FonteBuscaPorDiscord | None = None,
        importacao: ImportacaoService | None = None,
        *,
        mapa_campos: dict[str, str] | None = None,
        ttl_negativo: float = 60.0,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fonte = fonte
        self._importacao = importacao
        self._mapa = mapa_campos or {}
        self._ttl = ttl_negativo
        self._relogio = relogio
        self._recusados: dict[int, float] = {}

    async def membro_cadastrado(
        self, session: AsyncSession, discord_id: int, *, guild_id: int | None = None
    ) -> Membro:
        """Membro ativo do Clube para `discord_id`, ou `NaoCadastradoError`."""
        try:
            return await repo_membros.obter_cadastrado_por_discord(session, discord_id)
        except NaoCadastradoError:
            if self._fonte is None or self._importacao is None:
                raise

        agora = self._relogio()
        if self._recusados.get(discord_id, 0.0) > agora:
            raise NaoCadastradoError()

        documento = await self._fonte.buscar_por_discord(discord_id)
        externo = normalizar(documento, mapa=self._mapa) if documento is not None else None

        membro = None
        if externo is not None and externo.elegivel and externo.discord_id == discord_id:
            membro = await self._importacao.importar_um(session, externo, guild_id=guild_id)

        if membro is None:
            self._recusar(discord_id, agora)
            raise NaoCadastradoError()

        log.info("Acesso: membro %s cadastrado na plataforma, espelhado sob demanda.", membro.id)
        return membro

    def _recusar(self, discord_id: int, agora: float) -> None:
        if len(self._recusados) >= LIMITE_CACHE_NEGATIVO:
            self._recusados = {k: v for k, v in self._recusados.items() if v > agora}
            if len(self._recusados) >= LIMITE_CACHE_NEGATIVO:
                self._recusados.clear()
        self._recusados[discord_id] = agora + self._ttl
