"""Hierarquia TYTO — TD-004, TD-007, RN-001, RN-002 (`Institucional/XP.md` Art. 2º)."""

from __future__ import annotations

import pytest

from oraculo.domain.hierarchy import (
    CENTURIAO,
    COMANDANTE,
    DESAFIANTE_LEGIONARIO,
    ESCUDEIRO,
    NEOFITO,
    OFICIAL,
    OMNI,
    PATENTES,
    RENOVEK,
    VETERANO,
    CargoInstitucional,
    Perfil,
    nomes_de_cargos_institucionais_discord,
    nomes_de_patentes_discord,
    patente_para_xp,
    patente_por_slug,
    pelo_menos,
    proxima_patente,
    xp_faltante,
)


def test_escala_tem_os_17_patamares_do_xp_md_em_ordem():
    assert [p.nome for p in PATENTES] == [
        "Neófito", "Escudeiro", "Armeiro", "Veterano", "Mestre de Armas",
        "Desafiante Legionário", "Oficial", "Centurião", "Comandante", "Dom", "Lorde",
        "Senhor da Guerra", "Suserano", "Monarca", "Dominador", "Renovek", "Omni",
    ]
    assert [p.ordem for p in PATENTES] == list(range(1, 18))
    limiares = [p.xp_minimo for p in PATENTES]
    assert limiares == sorted(limiares)
    assert len(set(limiares)) == len(limiares)


def test_nao_existem_niveis_do_legado_nem_da_hierarquia_anterior():
    """TD-004 / TD-007 — nem 'Novice' nem Membro/Cavalaria reaparecem como patente."""
    nomes = {p.nome.casefold() for p in PATENTES}
    assert nomes.isdisjoint({"novice", "membro", "cavalaria", "conselheiro", "administrador"})


@pytest.mark.parametrize(
    ("xp", "esperado"),
    [
        (0, NEOFITO),
        (103, NEOFITO),
        (104, ESCUDEIRO),
        (1_660, VETERANO),
        (105_999, DESAFIANTE_LEGIONARIO),
        (106_000, OFICIAL),
        (425_000, CENTURIAO),
        (1_702_400, COMANDANTE),
        (60_000_000_000, RENOVEK),
        (300_000_000_000, OMNI),
        (10**15, OMNI),
    ],
)
def test_patente_para_xp(xp, esperado):
    """RN-002 — a patente é determinada exclusivamente pelo XP (XP.md Art. 1º §3º)."""
    assert patente_para_xp(xp) == esperado


def test_limiar_exato_de_oficial():
    assert patente_para_xp(105_999) != OFICIAL
    assert patente_para_xp(106_000) == OFICIAL


def test_limiares_batem_com_a_plataforma():
    """Mesmos valores de CLAN_TIERS em TYTO.club — bot e plataforma nunca discordam."""
    assert COMANDANTE.xp_minimo == 1_702_400
    assert CENTURIAO.xp_minimo == 425_000
    assert OMNI.xp_minimo == 300_000_000_000


def test_proxima_patente_e_xp_faltante():
    assert proxima_patente(NEOFITO) == ESCUDEIRO
    assert proxima_patente(OMNI) is None
    assert xp_faltante(100) == 4
    assert xp_faltante(104) == 415 - 104
    assert xp_faltante(OMNI.xp_minimo) is None


def test_pelo_menos_compara_patentes():
    assert pelo_menos(OFICIAL, VETERANO)
    assert pelo_menos(VETERANO, VETERANO)
    assert not pelo_menos(ESCUDEIRO, VETERANO)


def test_papeis_de_patente_cobrem_toda_a_escala():
    """RN-001 / TD-005 — a remoção precisa alcançar todos os papéis de patente."""
    assert nomes_de_patentes_discord() == {p.nome for p in PATENTES}


def test_cargos_institucionais_sao_papeis_separados_das_patentes():
    assert nomes_de_cargos_institucionais_discord() == {"Conselheiro", "Administrador"}
    assert nomes_de_cargos_institucionais_discord().isdisjoint(nomes_de_patentes_discord())


def test_patente_por_slug_aceita_slug_e_nome():
    assert patente_por_slug("mestre-de-armas").nome == "Mestre de Armas"
    assert patente_por_slug("Centurião") == CENTURIAO
    with pytest.raises(KeyError):
        patente_por_slug("cavalaria")


def test_perfil_descreve_patente_e_cargos():
    assert Perfil(OFICIAL).descricao() == "Oficial"
    perfil = Perfil(COMANDANTE, conselheiro=True)
    assert perfil.descricao() == "Comandante · Conselheiro"
    assert perfil.possui(CargoInstitucional.CONSELHEIRO)
    assert not perfil.possui(CargoInstitucional.ADMINISTRADOR)
