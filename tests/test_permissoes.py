"""Política de permissões — RN-004, RN-006, RN-007, RN-008."""

from __future__ import annotations

import pytest

from oraculo.domain.errors import PermissaoNegadaError
from oraculo.domain.hierarchy import (
    ADMINISTRADOR,
    CAVALARIA,
    CONSELHEIRO,
    HIERARQUIA,
    LORDE,
    MEMBRO,
)
from oraculo.domain.permissions import Acao, cargo_minimo, exigir, pode_executar


def test_toda_acao_possui_politica():
    """RN-008 — nenhuma ação privilegiada pode ficar sem cargo mínimo."""
    for acao in Acao:
        assert cargo_minimo(acao) in HIERARQUIA


@pytest.mark.parametrize("acao", [Acao.CONCEDER_XP, Acao.REMOVER_XP, Acao.VER_HISTORICO_XP])
def test_xp_exige_conselheiro(acao):
    """RN-004 — somente Conselheiro+ movimenta XP."""
    assert not pode_executar(MEMBRO, acao)
    assert not pode_executar(CAVALARIA, acao)
    assert not pode_executar(LORDE, acao)
    assert pode_executar(CONSELHEIRO, acao)
    assert pode_executar(ADMINISTRADOR, acao)


def test_reuniao_exige_cavalaria():
    """RN-006 (leitura 'Cavalaria+', conforme RF-007/UC-004/glossário)."""
    assert not pode_executar(MEMBRO, Acao.CRIAR_REUNIAO)
    assert pode_executar(CAVALARIA, Acao.CRIAR_REUNIAO)


def test_evento_oficial_exige_lorde():
    """RN-007 — Cavalaria não cria evento oficial."""
    assert not pode_executar(CAVALARIA, Acao.CRIAR_EVENTO)
    assert pode_executar(LORDE, Acao.CRIAR_EVENTO)


def test_consultas_liberadas_para_membro():
    for acao in (Acao.VER_PERFIL, Acao.VER_RANKING, Acao.RESPONDER_RSVP):
        assert pode_executar(MEMBRO, acao)


def test_acoes_de_administracao_restritas():
    assert not pode_executar(CONSELHEIRO, Acao.ADMINISTRAR_SISTEMA)
    assert not pode_executar(CONSELHEIRO, Acao.DEFINIR_CARGO_MANUAL)
    assert pode_executar(ADMINISTRADOR, Acao.ADMINISTRAR_SISTEMA)


def test_exigir_levanta_erro_com_contexto():
    with pytest.raises(PermissaoNegadaError) as excecao:
        exigir(MEMBRO, Acao.CONCEDER_XP)
    erro = excecao.value
    assert erro.regra == "RN-008"
    assert erro.cargo_atual == "Membro"
    assert erro.cargo_minimo == "Conselheiro"
