"""Hierarquia TYTO — TD-004, RN-001, RN-002."""

from __future__ import annotations

import pytest

from oraculo.domain.hierarchy import (
    ADMINISTRADOR,
    CAVALARIA,
    CONSELHEIRO,
    HIERARQUIA,
    LORDE,
    MEMBRO,
    cargo_para_xp,
    cargo_por_slug,
    nomes_de_cargos_discord,
    pelo_menos,
    proximo_cargo,
    xp_faltante,
)


def test_hierarquia_esta_ordenada_e_sem_duplicatas():
    ordens = [cargo.ordem for cargo in HIERARQUIA]
    assert ordens == sorted(ordens)
    assert len({c.slug for c in HIERARQUIA}) == len(HIERARQUIA)


def test_nao_existem_niveis_do_legado():
    """TD-004 — os níveis arbitrários ('Novice' etc.) não podem reaparecer."""
    nomes = {cargo.nome.casefold() for cargo in HIERARQUIA}
    assert nomes == {"membro", "cavalaria", "lorde", "conselheiro", "administrador"}


@pytest.mark.parametrize(
    ("xp", "esperado"),
    [
        (-100, MEMBRO),
        (0, MEMBRO),
        (499, MEMBRO),
        (500, CAVALARIA),
        (1_499, CAVALARIA),
        (1_500, LORDE),
        (3_499, LORDE),
        (3_500, CONSELHEIRO),
        (10_000_000, CONSELHEIRO),
    ],
)
def test_cargo_para_xp(xp, esperado):
    """RN-002 — progressão determinada apenas pelo XP acumulado."""
    assert cargo_para_xp(xp) is esperado


def test_administrador_nunca_e_alcancado_por_xp():
    assert cargo_para_xp(10**9) is not ADMINISTRADOR
    assert ADMINISTRADOR.automatico is False


def test_proximo_cargo_e_xp_faltante():
    assert proximo_cargo(MEMBRO) is CAVALARIA
    assert proximo_cargo(CONSELHEIRO) is None
    assert xp_faltante(300) == 200
    assert xp_faltante(500) == 1_000
    assert xp_faltante(4_000) is None


def test_pelo_menos_implementa_comparacao_de_cargos():
    assert pelo_menos(LORDE, CAVALARIA)
    assert pelo_menos(CAVALARIA, CAVALARIA)
    assert not pelo_menos(MEMBRO, CAVALARIA)


def test_cargos_gerenciados_no_discord_cobrem_toda_a_hierarquia():
    """RN-001 / TD-005 — a remoção precisa alcançar todos os cargos TYTO."""
    assert nomes_de_cargos_discord() == {cargo.nome for cargo in HIERARQUIA}


def test_cargo_por_slug_aceita_slug_e_nome():
    assert cargo_por_slug("cavalaria") is CAVALARIA
    assert cargo_por_slug("Cavalaria") is CAVALARIA
    with pytest.raises(KeyError):
        cargo_por_slug("novice")
