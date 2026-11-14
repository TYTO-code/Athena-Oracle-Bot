"""Cliente da TYTO.club-API para o gerente dos projetos (docs/GERENTE_PLANO.md).

A API decide tudo (o que sai, para quem, quando, e o que cada pessoa pode ver); a Atena só busca
e entrega. Autenticação serviço-a-serviço pelo cabeçalho `X-Service-Key` (mesma chave de
`ATHENA_SERVICE_KEY` na API). A identidade de quem pergunta vai como o ID do Discord de quem
rodou o comando — a API resolve o usuário e aplica a matriz de permissão no servidor.

Nada aqui escreve dado da plataforma (RN-021): a única escrita é confirmar a entrega de uma
mensagem da fila do próprio gerente.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from oraculo.config import Settings, get_settings
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.logging_config import get_logger

log = get_logger(__name__)


class FonteGerente(Protocol):
    """Porta trocável por um dublê em teste."""

    async def fila(self, limite: int = 20) -> list[dict[str, Any]]: ...

    async def confirmar(self, item_id: str, status: str) -> None: ...

    async def consultar(self, recurso: str, discord_id: int, **params: str) -> dict[str, Any]: ...


class ClienteGerenteApi:
    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        if not cfg.gerente_habilitado:
            raise IntegracaoIndisponivelError(
                "TYTO.club-API", "ORACULO_TYTO_API_URL/ORACULO_TYTO_API_SERVICE_KEY não definidas."
            )
        self._base = str(cfg.tyto_api_url).rstrip("/") + "/api/internal/gerente"
        self._headers = {"X-Service-Key": str(cfg.tyto_api_service_key)}
        self._timeout = cfg.tyto_api_timeout

    async def _pedir(self, metodo: str, caminho: str, **kwargs: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as cliente:
                resposta = await cliente.request(metodo, self._base + caminho, **kwargs)
        except httpx.HTTPError as exc:
            log.warning("TYTO.club-API indisponível: %s", exc)
            raise IntegracaoIndisponivelError(
                "TYTO.club-API", "sem resposta da plataforma."
            ) from exc

        if resposta.status_code == 404 and caminho.startswith("/eu"):
            # Ninguém com este ID do Discord no site (ou dois perfis com o mesmo ID).
            return {"vinculado": False}
        if resposta.status_code >= 400:
            log.warning("TYTO.club-API respondeu %s em %s", resposta.status_code, caminho)
            raise IntegracaoIndisponivelError(
                "TYTO.club-API", f"a plataforma respondeu HTTP {resposta.status_code}."
            )
        corpo = resposta.json()
        return corpo.get("data", corpo) if isinstance(corpo, dict) else corpo

    async def fila(self, limite: int = 20) -> list[dict[str, Any]]:
        dados = await self._pedir("GET", "/outbox", params={"limit": limite})
        return list(dados or [])

    async def confirmar(self, item_id: str, status: str) -> None:
        await self._pedir("POST", f"/outbox/{item_id}/ack", json={"status": status})

    async def consultar(self, recurso: str, discord_id: int, **params: str) -> dict[str, Any]:
        """`recurso` ∈ {"eu", "status", "missoes"} — leitura já filtrada pela API."""
        caminho = "/eu" if recurso == "eu" else f"/eu/{recurso}"
        dados = await self._pedir("GET", caminho, params={"discordId": str(discord_id), **params})
        return dict(dados or {})


def criar_fonte_gerente(settings: Settings | None = None) -> FonteGerente | None:
    cfg = settings or get_settings()
    return ClienteGerenteApi(cfg) if cfg.gerente_habilitado else None
