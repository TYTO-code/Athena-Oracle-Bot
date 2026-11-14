"""Entrega das mensagens do gerente dos projetos (fase 3 de docs/GERENTE_PLANO.md).

A TYTO.club-API decide o que sai e quando (inclusive o silêncio das 22h às 8h no fuso de quem
recebe); aqui só se busca o lote pronto, entrega por DM ou no canal da comunidade e confirma.
Nenhum texto é gerado aqui, muito menos por IA: a mensagem chega pronta, montada por modelo.

Confirmação:
* `sent`   — entregue.
* `failed` — DM fechada ou usuário inexistente (decisão do membro, não erro): não insiste.
* `retry`  — falha transitória do Discord: volta para a fila (a API fecha após 3 tentativas).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.integrations.gerente_api import FonteGerente
from oraculo.logging_config import get_logger
from oraculo.observabilidade import contar_mensagem

log = get_logger(__name__)


class ResultadoEnvio:
    ENTREGUE = "sent"
    RECUSADO = "failed"
    TENTAR_DE_NOVO = "retry"


class Remetente(Protocol):
    """Quem fala com o Discord (o bot real ou um dublê)."""

    async def enviar_dm(self, discord_id: int, texto: str) -> str: ...

    async def publicar_no_canal(self, texto: str) -> str: ...


@dataclass(slots=True)
class RelatorioEntrega:
    entregues: int = 0
    recusadas: int = 0
    adiadas: int = 0


@dataclass(slots=True)
class GerenteEntregaService:
    fonte: FonteGerente
    remetente: Remetente
    lote: int = 20

    async def entregar_pendentes(self) -> RelatorioEntrega:
        relatorio = RelatorioEntrega()
        try:
            itens = await self.fonte.fila(self.lote)
        except IntegracaoIndisponivelError:
            log.warning("Gerente: fila indisponível; tento de novo no próximo ciclo.")
            contar_mensagem("fila", "indisponivel")
            return relatorio

        for item in itens:
            resultado = await self._entregar(item)
            contar_mensagem(item.get("kind"), resultado)
            try:
                await self.fonte.confirmar(str(item.get("id")), resultado)
            except IntegracaoIndisponivelError:
                # Sem confirmação o item volta no próximo lote. Melhor que perder a mensagem;
                # o risco (repetir uma DM) só existe se a API cair entre o envio e a confirmação.
                log.warning("Gerente: não confirmei a entrega de %s.", item.get("id"))
            if resultado == ResultadoEnvio.ENTREGUE:
                relatorio.entregues += 1
            elif resultado == ResultadoEnvio.RECUSADO:
                relatorio.recusadas += 1
            else:
                relatorio.adiadas += 1
        return relatorio

    async def _entregar(self, item: dict[str, Any]) -> str:
        texto = str(item.get("text") or "").strip()
        alvo = item.get("target") or {}
        if not texto:
            return ResultadoEnvio.RECUSADO
        if alvo.get("kind") == "canal":
            return await self.remetente.publicar_no_canal(texto)
        if alvo.get("kind") == "dm":
            try:
                discord_id = int(str(alvo.get("discordId")))
            except ValueError:
                return ResultadoEnvio.RECUSADO
            return await self.remetente.enviar_dm(discord_id, texto)
        return ResultadoEnvio.RECUSADO
