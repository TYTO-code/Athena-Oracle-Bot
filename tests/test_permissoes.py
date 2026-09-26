"""Política de permissões — RN-004, RN-006, RN-007, RN-008, TD-007."""

from __future__ import annotations

import pytest

from oraculo.domain.errors import PermissaoNegadaError
from oraculo.domain.hierarchy import (
    ARMEIRO,
    DESAFIANTE_LEGIONARIO,
    NEOFITO,
    OFICIAL,
    OMNI,
    PATENTES,
    VETERANO,
    CargoInstitucional,
    Perfil,
)
from oraculo.domain.permissions import (
    Acao,
    descrever_requisito,
    exigir,
    pode_executar,
    requisito_minimo,
)

NEOFITO_ = Perfil(NEOFITO)
CONSELHEIRO = Perfil(NEOFITO, conselheiro=True)
ADMINISTRADOR = Perfil(NEOFITO, administrador=True)


def test_toda_acao_possui_politica():
    """RN-008 — nenhuma ação privilegiada pode ficar sem requisito."""
    for acao in Acao:
        assert requisito_minimo(acao) in (*PATENTES, *CargoInstitucional)


def test_nao_existe_acao_de_remover_xp():
    """XP é irrevogável (XP.md Art. 1º §1º)."""
    assert "remover_xp" not in {a.value for a in Acao}


@pytest.mark.parametrize("acao", [Acao.CONCEDER_XP, Acao.VER_HISTORICO_XP])
def test_xp_exige_cargo_conselheiro_nao_patente(acao):
    """RN-004 — XP não elege ninguém: nem Omni concede XP sem ser Conselheiro."""
    assert not pode_executar(NEOFITO_, acao)
    assert not pode_executar(Perfil(OMNI), acao)
    assert pode_executar(CONSELHEIRO, acao)
    assert pode_executar(ADMINISTRADOR, acao)


def test_reuniao_exige_veterano():
    """RN-006 — reunião a partir de Veterano (TD-007)."""
    assert not pode_executar(Perfil(ARMEIRO), Acao.CRIAR_REUNIAO)
    assert pode_executar(Perfil(VETERANO), Acao.CRIAR_REUNIAO)


def test_evento_e_comunicado_exigem_oficial():
    """RN-007 / RN-018 — evento oficial e comunicado a partir de Oficial."""
    for acao in (Acao.CRIAR_EVENTO, Acao.PUBLICAR_COMUNICADO):
        assert not pode_executar(Perfil(DESAFIANTE_LEGIONARIO), acao)
        assert pode_executar(Perfil(OFICIAL), acao)


def test_conselheiro_satisfaz_requisitos_de_patente():
    """Conselheiro eleito já é Comandante+ (Carta Art. III) — vale mesmo com patente baixa."""
    assert pode_executar(CONSELHEIRO, Acao.CRIAR_EVENTO)
    assert pode_executar(CONSELHEIRO, Acao.MENCIONAR_TODOS)


def test_consultas_liberadas_para_qualquer_membro():
    for acao in (Acao.VER_PERFIL, Acao.VER_RANKING, Acao.RESPONDER_RSVP, Acao.PERGUNTAR):
        assert pode_executar(NEOFITO_, acao)


def test_acoes_de_administracao_restritas():
    for acao in (
        Acao.ADMINISTRAR_SISTEMA,
        Acao.DEFINIR_CARGO_INSTITUCIONAL,
        Acao.CONFIRMAR_PATENTE,
        Acao.RECONCILIAR_CONTA,
    ):
        assert not pode_executar(CONSELHEIRO, acao)
        assert not pode_executar(Perfil(OMNI), acao)
        assert pode_executar(ADMINISTRADOR, acao)


def test_exigir_levanta_erro_com_contexto():
    with pytest.raises(PermissaoNegadaError) as excecao:
        exigir(NEOFITO_, Acao.CONCEDER_XP)
    erro = excecao.value
    assert erro.regra == "RN-008"
    assert erro.cargo_atual == "Neófito"
    assert erro.cargo_minimo == "cargo Conselheiro"


def test_descrever_requisito():
    assert descrever_requisito(NEOFITO) == "qualquer membro"
    assert descrever_requisito(OFICIAL) == "Oficial ou superior"
    assert descrever_requisito(CargoInstitucional.ADMINISTRADOR) == "cargo Administrador"
