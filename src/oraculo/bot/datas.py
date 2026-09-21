"""Leitura de data/hora digitada em slash command.

Vive fora dos cogs porque mais de um comando pede data (agenda e comunicados) e
todos precisam do **mesmo** conjunto de formatos aceitos e do mesmo fuso: uma
segunda implementação seria uma segunda definição de "25/12 às 19:30".
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from oraculo.config import get_settings
from oraculo.domain.errors import BusinessRuleError
from oraculo.services.agenda_service import DataInvalidaError

FORMATOS_DATA = ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M")


def interpretar_data(
    texto: str, *, excecao: type[BusinessRuleError] = DataInvalidaError
) -> datetime:
    """Converte a data digitada para `datetime` com o fuso do clube.

    `excecao` permite que cada comando reporte a regra que o governa — a
    mensagem para quem digitou é a mesma, a rastreabilidade não.
    """
    fuso = ZoneInfo(get_settings().google_timezone)
    limpo = texto.strip()
    for formato in FORMATOS_DATA:
        try:
            return datetime.strptime(limpo, formato).replace(tzinfo=fuso)  # noqa: DTZ007
        except ValueError:
            continue
    raise excecao(f"Data inválida: {texto!r}. Use `DD/MM/AAAA HH:MM` (ex.: 25/12/2026 19:30).")
