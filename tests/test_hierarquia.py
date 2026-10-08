"""Hierarquia TYTO — TD-004, TD-007, RN-001, RN-002 (`Institucional/XP.md` Art. 2º)."""

from __future__ import annotations

import pytest

from oraculo.domain.hierarchy import (
    ARMEIRO,
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
    XP_BASE,
    XP_MULTIPLICADOR,
    CargoInstitucional,
    Perfil,
    nomes_de_cargos_institucionais_discord,
    nomes_de_patentes_discord,
    normalizar_nome_papel,
    patente_do_papel,
    patente_para_xp,
    patente_por_slug,
    pelo_menos,
    proxima_patente,
    xp_faltante,
)


def test_escala_tem_os_17_patamares_do_xp_md_em_ordem():
    assert [p.nome for p in PATENTES] == [
        "Neófito",
        "Escudeiro",
        "Armeiro",
        "Veterano",
        "Mestre de Armas",
        "Desafiante Legionário",
        "Oficial",
        "Centurião",
        "Comandante",
        "Dom",
        "Lorde",
        "Senhor da Guerra",
        "Suserano",
        "Monarca",
        "Kyrios",
        "Invictus",
        "Dominus",
        "Renovek",
        "Omni",
    ]
    assert [p.ordem for p in PATENTES] == list(range(1, 20))
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
        (400, ESCUDEIRO),
        (399, NEOFITO),
        (400, ESCUDEIRO),
        (1_599, ESCUDEIRO),
        (1_600, ARMEIRO),
        (6_400, VETERANO),
        (409_599, DESAFIANTE_LEGIONARIO),
        (409_600, OFICIAL),
        (1_638_400, CENTURIAO),
        (6_553_599, CENTURIAO),
        (6_553_600, COMANDANTE),
        (400 * 4**16, RENOVEK),
        (400 * 4**17, OMNI),
        (10**15, OMNI),
    ],
)
def test_patente_para_xp(xp, esperado):
    """RN-002 — a patente é determinada exclusivamente pelo XP (XP.md Art. 1º §3º)."""
    assert patente_para_xp(xp) == esperado


def test_cada_patamar_vale_quatro_vezes_o_anterior():
    """XP.md Art. 2º §3º — regra única da escala: de Escudeiro em diante, 4× o patamar anterior."""
    assert NEOFITO.xp_minimo == 0
    assert ESCUDEIRO.xp_minimo == XP_BASE == 400
    for anterior, atual in zip(PATENTES[1:], PATENTES[2:], strict=False):
        assert atual.xp_minimo == anterior.xp_minimo * XP_MULTIPLICADOR == anterior.xp_minimo * 4


def test_limiar_exato_de_oficial():
    assert patente_para_xp(409_599) != OFICIAL
    assert patente_para_xp(409_600) == OFICIAL


def test_limiares_batem_com_a_plataforma():
    """Mesmos valores de CLAN_TIERS em TYTO.club e no backend — nunca discordam."""
    assert [p.xp_minimo for p in PATENTES[:6]] == [0, 400, 1_600, 6_400, 25_600, 102_400]
    assert COMANDANTE.xp_minimo == 6_553_600
    assert CENTURIAO.xp_minimo == 1_638_400
    assert OMNI.xp_minimo == 6_871_947_673_600


def test_proxima_patente_e_xp_faltante():
    assert proxima_patente(NEOFITO) == ESCUDEIRO
    assert proxima_patente(OMNI) is None
    assert xp_faltante(396) == 4
    assert xp_faltante(400) == 1_600 - 400
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


@pytest.mark.parametrize(
    ("nome_no_discord", "esperado"),
    [
        ("Escudeiro", "escudeiro"),
        ("🛡️ Escudeiro", "escudeiro"),
        ("⚔️│Mestre de Armas", "mestre de armas"),
        ("【Neófito】", "neofito"),
        ("Omni ⭐", "omni"),
        ("★ DOMINADOR ★", "dominador"),
        ("𝐎𝐦𝐧𝐢", "omni"),
        ("  Senhor   da\tGuerra 👑 ", "senhor da guerra"),
        ("Neofito", "neofito"),
    ],
)
def test_normaliza_nome_de_papel_do_discord(nome_no_discord, esperado):
    assert normalizar_nome_papel(nome_no_discord) == esperado


def test_toda_patente_e_reconhecida_com_emoji_e_enfeites():
    for patente in PATENTES:
        assert patente_do_papel(patente.nome) is patente
        assert patente_do_papel(f"🔥 {patente.nome.upper()} ✨") is patente
        assert patente_do_papel(f"【{patente.nome}】") is patente


def test_papel_que_nao_e_patente_nao_e_reconhecido():
    assert patente_do_papel("🎨 Designer") is None
    assert patente_do_papel("Escudeiro Mirim") is None


def test_nivel_divino_tem_cinco_titulos_cada_um_com_o_quadruplo_do_anterior():
    """XP.md Art. 2º — Kyrios, Invictus, Dominus, Renovek e Omni (patamares 15 a 19)."""
    divinos = PATENTES[14:]
    assert [p.nome for p in divinos] == ["Kyrios", "Invictus", "Dominus", "Renovek", "Omni"]
    for anterior, atual in zip(divinos, divinos[1:], strict=False):
        assert atual.xp_minimo == anterior.xp_minimo * 4


def test_dominador_agora_e_kyrios_slug_e_papel_antigos_ainda_resolvem():
    """O slug gravado e o papel do Discord antigos não somem do dia para a noite."""
    from oraculo.domain.hierarchy import KYRIOS, patente_por_slug

    assert patente_por_slug("dominador") is KYRIOS
    assert patente_por_slug("Dominador") is KYRIOS
    assert patente_por_slug("kyrios") is KYRIOS
    assert patente_do_papel("Dominador") is KYRIOS
    assert patente_do_papel("★ DOMINADOR ★") is KYRIOS
    assert KYRIOS.ordem == 15
