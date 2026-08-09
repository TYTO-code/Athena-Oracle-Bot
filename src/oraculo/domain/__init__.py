"""Camada de domínio: hierarquia TYTO, permissões e erros de negócio."""

from oraculo.domain.errors import (
    BusinessRuleError,
    MotivoObrigatorioError,
    OraculoError,
    PermissaoNegadaError,
    QuantidadeInvalidaError,
    RecursoNaoEncontradoError,
)
from oraculo.domain.hierarchy import (
    HIERARQUIA,
    Cargo,
    cargo_para_xp,
    cargo_por_slug,
    nomes_de_cargos_discord,
    proximo_cargo,
    xp_faltante,
)
from oraculo.domain.permissions import Acao, cargo_minimo, pode_executar

__all__ = [
    "HIERARQUIA",
    "Acao",
    "BusinessRuleError",
    "Cargo",
    "MotivoObrigatorioError",
    "OraculoError",
    "PermissaoNegadaError",
    "QuantidadeInvalidaError",
    "RecursoNaoEncontradoError",
    "cargo_minimo",
    "cargo_para_xp",
    "cargo_por_slug",
    "nomes_de_cargos_discord",
    "pode_executar",
    "proximo_cargo",
    "xp_faltante",
]
