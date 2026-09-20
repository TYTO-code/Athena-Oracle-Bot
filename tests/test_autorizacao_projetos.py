"""Leitura dos projetos do membro no Firebase — RN-017.

A lista que sai daqui é o que autoriza (ou não) a leitura de um projeto. Um
formato não reconhecido tem que virar lista vazia, nunca um palpite: em
autorização, o silêncio é "não".
"""

from __future__ import annotations

from oraculo.integrations.plataforma import FonteEmMemoria, normalizar


def test_lista_de_strings():
    externo = normalizar({"id": "u1", "nome": "A", "projetos": ["proj-a", "proj-b"]})

    assert externo.projetos == ["proj-a", "proj-b"]


def test_lista_de_objetos_com_id():
    externo = normalizar(
        {"id": "u1", "nome": "A", "projetos": [{"id": "proj-a"}, {"id": "proj-b"}]}
    )

    assert externo.projetos == ["proj-a", "proj-b"]


def test_mapa_id_para_booleano_respeita_o_desligado():
    """Formato comum no Firestore — `false` significa fora do projeto."""
    externo = normalizar({"id": "u1", "nome": "A", "projetos": {"proj-a": True, "proj-b": False}})

    assert externo.projetos == ["proj-a"]


def test_string_separada_por_virgula():
    externo = normalizar({"id": "u1", "nome": "A", "projetos": "proj-a, proj-b"})

    assert externo.projetos == ["proj-a", "proj-b"]


def test_campo_ausente_vira_lista_vazia():
    assert normalizar({"id": "u1", "nome": "A"}).projetos == []


def test_formato_inesperado_nao_vira_palpite():
    """Número solto, booleano, lixo: nada disso vira autorização."""
    assert normalizar({"id": "u1", "nome": "A", "projetos": True}).projetos == []
    assert normalizar({"id": "u1", "nome": "A", "projetos": 42}).projetos == []


def test_nome_do_campo_e_configuravel():
    externo = normalizar(
        {"id": "u1", "nome": "A", "squads": ["proj-a"]}, mapa={"projetos": "squads"}
    )

    assert externo.projetos == ["proj-a"]


async def test_fonte_em_memoria_resolve_projetos_por_id_externo():
    fonte = FonteEmMemoria([{"id": "u1", "nome": "A", "projetos": ["proj-a"]}])

    assert await fonte.projetos_de("u1") == ["proj-a"]


async def test_id_externo_desconhecido_nao_tem_projeto():
    fonte = FonteEmMemoria([{"id": "u1", "nome": "A", "projetos": ["proj-a"]}])

    assert await fonte.projetos_de("u-inexistente") == []
    assert await fonte.projetos_de("") == []
