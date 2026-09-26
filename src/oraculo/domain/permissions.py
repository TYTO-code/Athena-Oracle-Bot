"""Política de permissões — RN-008.

Todo acesso a comando privilegiado é validado contra esta tabela, que é a
**única** fonte de verdade. Cogs e endpoints não decidem permissão sozinhos.

Com a unificação de TD-007, cada ação exige **um** de dois tipos de requisito
(ver `hierarchy.py`):

* uma **patente mínima** (XP.md Art. 2º) — "Veterano+", "Oficial+"; ou
* um **cargo institucional** — Conselheiro ou Administrador.

Regras de satisfação:

* Administrador satisfaz qualquer requisito (é a função de governança do bot).
* Conselheiro satisfaz os requisitos de patente — um Conselheiro eleito já
  está em Comandante+ (Carta Art. III), acima de toda patente exigida aqui.
* Patente nunca satisfaz um requisito de cargo institucional: XP não elege
  ninguém ao Conselho.

Mapa aprovado pelo Clube TYTO ao resolver TD-007 (reuniões Veterano+, eventos
e comunicados Oficial+, XP/auditoria/@everyone para Conselheiro, sistema para
Administrador).
"""

from __future__ import annotations

from enum import StrEnum

from oraculo.domain.errors import PermissaoNegadaError
from oraculo.domain.hierarchy import (
    NEOFITO,
    OFICIAL,
    VETERANO,
    CargoInstitucional,
    Patente,
    Perfil,
    pelo_menos,
)

Requisito = Patente | CargoInstitucional
"""O que uma ação exige: uma patente mínima ou um cargo institucional."""


class Acao(StrEnum):
    """Ações privilegiadas do sistema, ligadas aos RF/RN correspondentes."""

    # Consulta — RF-002, RF-004, RF-009
    VER_PERFIL = "ver_perfil"
    VER_RANKING = "ver_ranking"
    RESPONDER_RSVP = "responder_rsvp"

    # Pergunta ao Oráculo — RN-017. Aberta a todo membro: o que cada pessoa pode
    # *ler* não é decidido por patente, e sim pelos projetos em que ela está
    # (verificado no Firebase a cada pergunta, em `pergunta_service.py`).
    PERGUNTAR = "perguntar"

    # XP — RF-003, RN-004, RN-005. Não existe "remover XP": XP é irrevogável
    # (XP.md Art. 1º §1º).
    CONCEDER_XP = "conceder_xp"
    VER_HISTORICO_XP = "ver_historico_xp"

    # Agenda — RF-007, RF-008, RN-006, RN-007
    CRIAR_REUNIAO = "criar_reuniao"
    GERIR_REUNIAO = "gerir_reuniao"
    CRIAR_EVENTO = "criar_evento"
    GERIR_EVENTO = "gerir_evento"

    # Comunicados — RF-015, RN-018. `MENCIONAR_TODOS` é um degrau acima de
    # publicar de propósito: escrever no canal atinge quem for ler; `@everyone`
    # atinge o servidor inteiro no celular de cada um.
    PUBLICAR_COMUNICADO = "publicar_comunicado"
    GERIR_COMUNICADO = "gerir_comunicado"
    MENCIONAR_TODOS = "mencionar_todos"

    # Governança — RF-012, RNF-003, RNF-004
    DEFINIR_CARGO_INSTITUCIONAL = "definir_cargo_institucional"
    CONFIRMAR_PATENTE = "confirmar_patente"
    VER_AUDITORIA = "ver_auditoria"
    ADMINISTRAR_SISTEMA = "administrar_sistema"

    # Vínculo de conta — RN-016
    RECONCILIAR_CONTA = "reconciliar_conta"


_POLITICA: dict[Acao, Requisito] = {
    Acao.VER_PERFIL: NEOFITO,
    Acao.VER_RANKING: NEOFITO,
    Acao.RESPONDER_RSVP: NEOFITO,
    Acao.PERGUNTAR: NEOFITO,
    Acao.CONCEDER_XP: CargoInstitucional.CONSELHEIRO,
    Acao.VER_HISTORICO_XP: CargoInstitucional.CONSELHEIRO,
    Acao.CRIAR_REUNIAO: VETERANO,
    Acao.GERIR_REUNIAO: VETERANO,
    Acao.CRIAR_EVENTO: OFICIAL,
    Acao.GERIR_EVENTO: OFICIAL,
    Acao.PUBLICAR_COMUNICADO: OFICIAL,
    Acao.GERIR_COMUNICADO: OFICIAL,
    Acao.MENCIONAR_TODOS: CargoInstitucional.CONSELHEIRO,
    Acao.DEFINIR_CARGO_INSTITUCIONAL: CargoInstitucional.ADMINISTRADOR,
    Acao.CONFIRMAR_PATENTE: CargoInstitucional.ADMINISTRADOR,
    Acao.VER_AUDITORIA: CargoInstitucional.CONSELHEIRO,
    Acao.ADMINISTRAR_SISTEMA: CargoInstitucional.ADMINISTRADOR,
    Acao.RECONCILIAR_CONTA: CargoInstitucional.ADMINISTRADOR,
}


def requisito_minimo(acao: Acao) -> Requisito:
    """Patente mínima ou cargo institucional exigido para executar `acao`."""
    try:
        return _POLITICA[acao]
    except KeyError as exc:  # pragma: no cover - proteção contra ação nova sem política
        raise KeyError(
            f"Ação {acao!r} sem política de permissão definida (RN-008). "
            "Toda ação privilegiada precisa constar em `_POLITICA`."
        ) from exc


def satisfaz(perfil: Perfil, requisito: Requisito) -> bool:
    """True se `perfil` atende `requisito` (regras no docstring do módulo)."""
    if perfil.administrador:
        return True
    if isinstance(requisito, CargoInstitucional):
        return perfil.possui(requisito)
    return perfil.conselheiro or pelo_menos(perfil.patente, requisito)


def descrever_requisito(requisito: Requisito) -> str:
    """Texto para o usuário: "Oficial ou superior", "cargo Conselheiro"."""
    if isinstance(requisito, CargoInstitucional):
        return f"cargo {requisito.nome}"
    if requisito == NEOFITO:
        return "qualquer membro"
    return f"{requisito.nome} ou superior"


def pode_executar(perfil: Perfil, acao: Acao) -> bool:
    """True se `perfil` satisfaz o requisito de `acao` (RN-008)."""
    return satisfaz(perfil, requisito_minimo(acao))


def exigir(perfil: Perfil, acao: Acao) -> None:
    """Valida a permissão e levanta `PermissaoNegadaError` quando insuficiente.

    Usado pelos serviços de domínio, para que a regra valha inclusive quando a
    chamada não vem de um comando do Discord (ex.: webhook, job, script).
    """
    if not pode_executar(perfil, acao):
        raise PermissaoNegadaError(
            acao=acao.value,
            cargo_atual=perfil.descricao(),
            cargo_minimo=descrever_requisito(requisito_minimo(acao)),
        )


def acoes_disponiveis(perfil: Perfil) -> tuple[Acao, ...]:
    """Ações que `perfil` pode executar — útil para `/ajuda` e para auditoria."""
    return tuple(acao for acao in Acao if pode_executar(perfil, acao))
