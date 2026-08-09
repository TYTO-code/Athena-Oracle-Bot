"""Política de permissões por cargo.

RN-008 — todo acesso a comando privilegiado é validado contra esta tabela, que
é a **única** fonte de verdade. Cogs e endpoints não decidem permissão sozinhos.

> **Divergência documentada (RN-006):** o catálogo de regras diz "somente cargos
> *superiores* à Cavalaria podem criar reuniões", enquanto RF-007, UC-004 e o
> glossário dizem "Cavalaria+". Implementado como **Cavalaria+** (maioria dos
> artefatos). Para adotar a leitura estrita, troque `CAVALARIA` por `LORDE` em
> `_POLITICA[Acao.CRIAR_REUNIAO]` — nenhuma outra alteração é necessária.
"""

from __future__ import annotations

from enum import StrEnum

from oraculo.domain.errors import PermissaoNegadaError
from oraculo.domain.hierarchy import (
    ADMINISTRADOR,
    CAVALARIA,
    CONSELHEIRO,
    LORDE,
    MEMBRO,
    Cargo,
    pelo_menos,
)


class Acao(StrEnum):
    """Ações privilegiadas do sistema, ligadas aos RF/RN correspondentes."""

    # Consulta — RF-002, RF-004, RF-009
    VER_PERFIL = "ver_perfil"
    VER_RANKING = "ver_ranking"
    RESPONDER_RSVP = "responder_rsvp"

    # XP — RF-003, RN-004, RN-005
    CONCEDER_XP = "conceder_xp"
    REMOVER_XP = "remover_xp"
    VER_HISTORICO_XP = "ver_historico_xp"

    # Agenda — RF-007, RF-008, RN-006, RN-007
    CRIAR_REUNIAO = "criar_reuniao"
    GERIR_REUNIAO = "gerir_reuniao"
    CRIAR_EVENTO = "criar_evento"
    GERIR_EVENTO = "gerir_evento"

    # Governança — RF-012, RNF-003, RNF-004
    DEFINIR_CARGO_MANUAL = "definir_cargo_manual"
    VER_AUDITORIA = "ver_auditoria"
    ADMINISTRAR_SISTEMA = "administrar_sistema"


_POLITICA: dict[Acao, Cargo] = {
    Acao.VER_PERFIL: MEMBRO,
    Acao.VER_RANKING: MEMBRO,
    Acao.RESPONDER_RSVP: MEMBRO,
    Acao.CONCEDER_XP: CONSELHEIRO,
    Acao.REMOVER_XP: CONSELHEIRO,
    Acao.VER_HISTORICO_XP: CONSELHEIRO,
    Acao.CRIAR_REUNIAO: CAVALARIA,
    Acao.GERIR_REUNIAO: CAVALARIA,
    Acao.CRIAR_EVENTO: LORDE,
    Acao.GERIR_EVENTO: LORDE,
    Acao.DEFINIR_CARGO_MANUAL: ADMINISTRADOR,
    Acao.VER_AUDITORIA: CONSELHEIRO,
    Acao.ADMINISTRAR_SISTEMA: ADMINISTRADOR,
}


def cargo_minimo(acao: Acao) -> Cargo:
    """Cargo mínimo exigido para executar `acao`."""
    try:
        return _POLITICA[acao]
    except KeyError as exc:  # pragma: no cover - proteção contra ação nova sem política
        raise KeyError(
            f"Ação {acao!r} sem política de permissão definida (RN-008). "
            "Toda ação privilegiada precisa constar em `_POLITICA`."
        ) from exc


def pode_executar(cargo: Cargo, acao: Acao) -> bool:
    """True se `cargo` satisfaz o mínimo exigido por `acao` (RN-008)."""
    return pelo_menos(cargo, cargo_minimo(acao))


def exigir(cargo: Cargo, acao: Acao) -> None:
    """Valida a permissão e levanta `PermissaoNegadaError` quando insuficiente.

    Usado pelos serviços de domínio, para que a regra valha inclusive quando a
    chamada não vem de um comando do Discord (ex.: webhook, job, script).
    """
    if not pode_executar(cargo, acao):
        raise PermissaoNegadaError(
            acao=acao.value,
            cargo_atual=cargo.nome,
            cargo_minimo=cargo_minimo(acao).nome,
        )


def acoes_disponiveis(cargo: Cargo) -> tuple[Acao, ...]:
    """Ações que `cargo` pode executar — útil para `/ajuda` e para auditoria."""
    return tuple(acao for acao in Acao if pode_executar(cargo, acao))
