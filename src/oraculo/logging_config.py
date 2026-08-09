"""Configuração de logging estruturado.

RNF-004 / RF-012 — a saída de log é a primeira camada de observabilidade; a
trilha de auditoria persistente fica em `services.audit_service`.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """Configura o logging raiz uma única vez por processo."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S%z"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Bibliotecas verbosas: mantém o log da aplicação legível.
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
