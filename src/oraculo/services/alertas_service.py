"""Caixa de alertas do Grafana: a rota HTTP enfileira, o bot entrega por DM (D15).

API e bot rodam no mesmo processo (`python -m oraculo`), então uma fila em memória basta. Com
API e bot em processos separados os alertas não chegam ao bot: a rota avisa no log. A fila é
limitada; cheia, o alerta mais novo é descartado com log (o Grafana repete enquanto disparar).
"""

from __future__ import annotations

import asyncio

from oraculo.logging_config import get_logger

log = get_logger(__name__)

LIMITE_FILA = 50


class CaixaDeAlertas:
    def __init__(self, limite: int = LIMITE_FILA) -> None:
        self._fila: asyncio.Queue[str] = asyncio.Queue(maxsize=limite)

    def enfileirar(self, texto: str) -> bool:
        try:
            self._fila.put_nowait(texto)
            return True
        except asyncio.QueueFull:
            log.warning("Caixa de alertas cheia; alerta descartado.")
            return False

    def retirar_todos(self) -> list[str]:
        itens: list[str] = []
        while not self._fila.empty():
            itens.append(self._fila.get_nowait())
        return itens

    def devolver(self, texto: str) -> None:
        self.enfileirar(texto)


CAIXA_ALERTAS = CaixaDeAlertas()
