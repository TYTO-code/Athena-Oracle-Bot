"""Leitura dos projetos do membro no Firebase — RN-017.

A lista que sai daqui é o que autoriza (ou não) a leitura de um projeto. Um
formato não reconhecido tem que virar lista vazia, nunca um palpite: em
autorização, o silêncio é "não".
"""

from __future__ import annotations

from types import SimpleNamespace

from oraculo.integrations.plataforma import (
    FonteEmMemoria,
    _ids_da_subcolecao,
    normalizar,
)


class _DocFake:
    """Documento de subcoleção no formato mínimo que o código consome."""

    def __init__(self, doc_id: str, dados: dict | None = None) -> None:
        self.id = doc_id
        self._dados = dados or {}

    def to_dict(self) -> dict:
        return self._dados


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


# --- Subcoleção `membros/{id}/projetos` (formato do clube) -------------------


def test_subcolecao_usa_o_id_do_documento_como_id_do_projeto():
    docs = [_DocFake("proj-a"), _DocFake("proj-b")]

    assert _ids_da_subcolecao(docs) == ["proj-a", "proj-b"]


def test_subcolecao_respeita_vinculo_encerrado():
    """Quem sai de um projeto costuma ser desativado, não apagado."""
    docs = [
        _DocFake("proj-a"),
        _DocFake("proj-b", {"ativo": False}),
        _DocFake("proj-c", {"removido": True}),
    ]

    assert _ids_da_subcolecao(docs) == ["proj-a"]


def test_subcolecao_aceita_id_explicito_no_documento():
    docs = [_DocFake("registro-1", {"projetoId": "proj-a"})]

    assert _ids_da_subcolecao(docs) == ["proj-a"]


def test_subcolecao_vazia_nao_autoriza_nada():
    assert _ids_da_subcolecao([]) == []


def test_subcolecao_nao_repete_id():
    docs = [_DocFake("proj-a"), _DocFake("proj-a")]

    assert _ids_da_subcolecao(docs) == ["proj-a"]


# --- D4: fonte do site é project_stats.members ---------------------------------


class _ConsultaFake:
    def __init__(self, docs: list) -> None:
        self._docs = docs

    async def stream(self):
        for doc in self._docs:
            yield doc


class _ColecaoProjetosFake:
    def __init__(self, membros_por_projeto: dict[str, dict[str, str]]) -> None:
        self._dados = membros_por_projeto
        self.consultas: list[tuple[str, str, list[str]]] = []

    def where(self, campo: str, op: str, valores: list[str]) -> _ConsultaFake:
        self.consultas.append((campo, op, valores))
        uid = campo.removeprefix("members.")
        return _ConsultaFake(
            [_DocFake(pid) for pid, membros in self._dados.items() if membros.get(uid) in valores]
        )


class _ClienteFake:
    def __init__(self, projetos: _ColecaoProjetosFake) -> None:
        self.projetos = projetos

    def collection(self, nome: str):
        if nome == "project_stats":
            return self.projetos
        # O documento do membro só pode ser referenciado, nunca lido, quando o site responde.
        return SimpleNamespace(document=lambda _id: SimpleNamespace())


async def test_projetos_vem_de_project_stats_members(settings):
    from oraculo.integrations.plataforma import FirestoreMembros

    colecao = _ColecaoProjetosFake(
        {"beta": {"u1": "contributor"}, "alpha": {"u1": "leader"}, "gama": {"u2": "leader"}}
    )
    fonte = FirestoreMembros(settings)
    fonte._cliente = _ClienteFake(colecao)
    assert await fonte.projetos_de("u1") == ["alpha", "beta"]
    assert colecao.consultas[0][0] == "members.u1"


def test_uid_estranho_nao_vira_caminho_de_campo():
    from oraculo.integrations.plataforma import campo_de_membro

    assert campo_de_membro("abcXYZ_09-") == "members.abcXYZ_09-"
    assert campo_de_membro("a.b") is None
    assert campo_de_membro("`x`") is None
    assert campo_de_membro("") is None
