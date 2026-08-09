"""Acesso a dados. Os serviços dependem destes módulos, nunca de SQL solto."""

from oraculo.repositories import agenda, auditoria, membros, xp

__all__ = ["agenda", "auditoria", "membros", "xp"]
