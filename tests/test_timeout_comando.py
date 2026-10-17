"""Teto de tempo do corpo de qualquer comando (`bot/permissions.py:requer`).

Sem isto, um banco ou o Firestore lento trava a interação do Discord esperando
resposta em vez de avisar o membro — mesmo raciocínio do timeout em
`/perguntar` (`integrations/llm.py`), só que aplicado a todo comando.
"""

from __future__ import annotations

import asyncio

import pytest

from oraculo.bot.permissions import _com_timeout
from oraculo.domain.errors import ComandoDemorouError


async def test_comando_lento_vira_erro_de_timeout(settings, monkeypatch):
    monkeypatch.setattr(settings, "comando_timeout_segundos", 0.05)
    monkeypatch.setattr("oraculo.bot.permissions.get_settings", lambda: settings)

    @_com_timeout
    async def lento() -> str:
        await asyncio.sleep(1)
        return "nunca chega aqui"

    with pytest.raises(ComandoDemorouError) as excecao:
        await lento()

    assert "0s" in str(excecao.value) or "demorou" in str(excecao.value)


async def test_comando_rapido_nao_e_afetado(settings, monkeypatch):
    monkeypatch.setattr(settings, "comando_timeout_segundos", 5)
    monkeypatch.setattr("oraculo.bot.permissions.get_settings", lambda: settings)

    @_com_timeout
    async def rapido(x: int) -> int:
        return x * 2

    assert await rapido(21) == 42


async def test_timeout_cancela_a_tarefa_interna(settings, monkeypatch):
    """O trabalho pendente é mesmo interrompido, não só ignorado."""
    monkeypatch.setattr(settings, "comando_timeout_segundos", 0.05)
    monkeypatch.setattr("oraculo.bot.permissions.get_settings", lambda: settings)

    chegou_ao_fim = False

    @_com_timeout
    async def lento() -> None:
        nonlocal chegou_ao_fim
        await asyncio.sleep(1)
        chegou_ao_fim = True  # pragma: no cover - não deve rodar

    with pytest.raises(ComandoDemorouError):
        await lento()

    await asyncio.sleep(0)  # dá chance a qualquer callback de cancelamento pendente
    assert chegou_ao_fim is False
