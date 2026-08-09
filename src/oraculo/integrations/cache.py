"""Cache de leitura para rankings e dados frequentes — US-404 / RNF-001.

Redis quando `ORACULO_REDIS_URL` está definido; caso contrário, um cache em
memória com o mesmo contrato. A aplicação nunca depende do Redis estar de pé:
qualquer falha degrada para consulta direta ao banco em vez de derrubar o
comando (RNF-002).
"""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

from oraculo.config import Settings, get_settings
from oraculo.logging_config import get_logger

log = get_logger(__name__)


class Cache(Protocol):
    """Contrato mínimo de cache usado pelos serviços."""

    async def obter(self, chave: str) -> Any | None: ...

    async def definir(self, chave: str, valor: Any, ttl: int) -> None: ...

    async def invalidar(self, prefixo: str) -> None: ...

    async def fechar(self) -> None: ...


class CacheMemoria:
    """Fallback local — suficiente para dev, testes e deploy single-node."""

    def __init__(self) -> None:
        self._dados: dict[str, tuple[float, Any]] = {}

    async def obter(self, chave: str) -> Any | None:
        item = self._dados.get(chave)
        if item is None:
            return None
        expira_em, valor = item
        if expira_em < time.monotonic():
            self._dados.pop(chave, None)
            return None
        return valor

    async def definir(self, chave: str, valor: Any, ttl: int) -> None:
        self._dados[chave] = (time.monotonic() + ttl, valor)

    async def invalidar(self, prefixo: str) -> None:
        for chave in [c for c in self._dados if c.startswith(prefixo)]:
            self._dados.pop(chave, None)

    async def fechar(self) -> None:
        self._dados.clear()


class CacheRedis:
    """Cache distribuído; exigido em deploy multi-instância (RNF-001)."""

    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis  # import tardio: dependência opcional em dev

        self._redis = Redis.from_url(url, decode_responses=True)

    async def obter(self, chave: str) -> Any | None:
        try:
            bruto = await self._redis.get(chave)
        except Exception:  # noqa: BLE001 — cache indisponível não derruba comando
            log.warning("Redis indisponível na leitura de %s; seguindo sem cache.", chave)
            return None
        return json.loads(bruto) if bruto else None

    async def definir(self, chave: str, valor: Any, ttl: int) -> None:
        try:
            await self._redis.set(chave, json.dumps(valor, default=str), ex=ttl)
        except Exception:  # noqa: BLE001
            log.warning("Redis indisponível na escrita de %s; ignorando.", chave)

    async def invalidar(self, prefixo: str) -> None:
        try:
            async for chave in self._redis.scan_iter(match=f"{prefixo}*"):
                await self._redis.delete(chave)
        except Exception:  # noqa: BLE001
            log.warning("Falha ao invalidar cache com prefixo %s.", prefixo)

    async def fechar(self) -> None:
        try:
            await self._redis.aclose()
        except Exception as exc:  # noqa: BLE001 — encerramento não deve falhar
            log.debug("Erro ao fechar conexão Redis: %s", exc)


def criar_cache(settings: Settings | None = None) -> Cache:
    """Escolhe a implementação conforme a configuração do ambiente."""
    cfg = settings or get_settings()
    if cfg.redis_url:
        log.info("Cache: Redis.")
        return CacheRedis(cfg.redis_url)
    if cfg.is_production:
        log.warning(
            "Cache em memória em produção: sem ORACULO_REDIS_URL o cache não é "
            "compartilhado entre instâncias (RNF-001)."
        )
    else:
        log.info("Cache: memória local.")
    return CacheMemoria()
