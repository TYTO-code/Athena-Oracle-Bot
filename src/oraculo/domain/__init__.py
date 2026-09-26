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
    PATENTES,
    CargoInstitucional,
    Patente,
    Perfil,
    nomes_de_patentes_discord,
    patente_para_xp,
    patente_por_slug,
    proxima_patente,
    xp_faltante,
)
from oraculo.domain.permissions import Acao, pode_executar, requisito_minimo

__all__ = [
    "PATENTES",
    "Acao",
    "BusinessRuleError",
    "CargoInstitucional",
    "MotivoObrigatorioError",
    "OraculoError",
    "Patente",
    "Perfil",
    "PermissaoNegadaError",
    "QuantidadeInvalidaError",
    "RecursoNaoEncontradoError",
    "nomes_de_patentes_discord",
    "patente_para_xp",
    "patente_por_slug",
    "pode_executar",
    "proxima_patente",
    "requisito_minimo",
    "xp_faltante",
]
