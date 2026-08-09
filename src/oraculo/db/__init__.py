"""Camada de persistência (SQLAlchemy async) — TD-002 / ADR-001."""

from oraculo.db.base import (
    Base,
    criar_schema,
    encerrar_engine,
    get_engine,
    get_sessionmaker,
    sessao,
)

__all__ = [
    "Base",
    "criar_schema",
    "encerrar_engine",
    "get_engine",
    "get_sessionmaker",
    "sessao",
]
