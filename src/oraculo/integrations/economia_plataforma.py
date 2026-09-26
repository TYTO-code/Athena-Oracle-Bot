"""Economia do Clube na plataforma (TYTO.club-API) — F2-006 / F2-007.

Os Dracmas de quem é do Clube vivem só na plataforma; o bot guarda apenas a
camada Comunidade. A única escrita que o bot faz lá é a migração de saldo na
filiação (`COMUNIDADE_E_CLUBE.md` Art. 4º §1º-A), pela rota interna
`POST /api/internal/community-migrations`, autenticada por chave de serviço.

A rota é idempotente por `referencia` (a conta de Aldeão de origem): repetir
depois de uma falha de rede nunca credita duas vezes.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from oraculo.config import Settings
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.logging_config import get_logger

log = get_logger(__name__)


class EconomiaPlataforma(Protocol):
    async def migrar_saldo_comunidade(
        self, *, id_externo: str, valor: int, referencia: str
    ) -> None:
        """Credita `valor` na conta de Membro `id_externo`; idempotente por `referencia`."""
        ...


class EconomiaPlataformaHttp:
    def __init__(self, base_url: str, chave: str, *, timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._chave = chave
        self._timeout = timeout

    async def migrar_saldo_comunidade(
        self, *, id_externo: str, valor: int, referencia: str
    ) -> None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                resposta = await cliente.post(
                    f"{self._base_url}/api/internal/community-migrations",
                    headers={"X-Service-Key": self._chave},
                    json={"userId": id_externo, "amount": valor, "communityRef": referencia},
                )
        except httpx.HTTPError as exc:
            raise IntegracaoIndisponivelError("Plataforma", str(exc)) from exc

        if resposta.status_code not in (200, 201):
            try:
                mensagem = resposta.json().get("message") or resposta.text
            except ValueError:
                mensagem = resposta.text
            raise IntegracaoIndisponivelError(
                "Plataforma", f"migração recusada (HTTP {resposta.status_code}): {mensagem}"[:300]
            )


def criar_economia_plataforma(cfg: Settings) -> EconomiaPlataforma | None:
    """`None` sem URL/chave configuradas — a migração fica indisponível, nada mais."""
    if not (cfg.plataforma_api_url and cfg.plataforma_api_chave):
        return None
    return EconomiaPlataformaHttp(cfg.plataforma_api_url, cfg.plataforma_api_chave)
