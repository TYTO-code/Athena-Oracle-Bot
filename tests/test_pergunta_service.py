"""`/perguntar`: autorização, isolamento entre projetos e freio de custo — RN-017.

O teste central aqui não é "a resposta está certa" — é **o que chegou a ser
enviado ao modelo**. Por isso o cliente é um dublê que guarda o prompt: se o
dado de um projeto alheio aparecer nele, a falha é de segurança, e nenhuma
instrução de prompt conserta isso depois.

Nada aqui chama a API de verdade (nem custa nada).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from oraculo.db.models import Membro, RegistroAuditoria
from oraculo.domain.errors import (
    IntegracaoIndisponivelError,
    LimiteDePerguntasError,
    PerguntaVaziaError,
)
from oraculo.integrations.cache import CacheMemoria
from oraculo.integrations.llm import Prompt
from oraculo.integrations.projetos_db import Decisao, ProjetoContexto
from oraculo.integrations.regras_corpus import Corpus
from oraculo.services.pergunta_service import PerguntaService


class ClienteFalso:
    """Guarda o prompt em vez de chamar a API."""

    def __init__(self, resposta: str = "resposta do oráculo") -> None:
        self.resposta = resposta
        self.prompt: Prompt | None = None

    async def responder(self, prompt: Prompt) -> str:
        self.prompt = prompt
        return self.resposta


class ProjetosFalsos:
    """Base externa dublê — registra com quais IDs foi consultada."""

    def __init__(self, por_id: dict[str, ProjetoContexto] | None = None) -> None:
        self.por_id = por_id or {}
        self.consultas: list[list[str]] = []

    async def contexto(self, projetos_autorizados: list[str]) -> list[ProjetoContexto]:
        self.consultas.append(list(projetos_autorizados))
        return [self.por_id[p] for p in projetos_autorizados if p in self.por_id]

    async def fechar(self) -> None:  # pragma: no cover - simetria de interface
        return None


class FonteProjetosFalsa:
    def __init__(self, mapa: dict[str, list[str]] | None = None, erro: Exception | None = None):
        self.mapa = mapa or {}
        self.erro = erro

    async def projetos_de(self, id_externo: str) -> list[str]:
        if self.erro is not None:
            raise self.erro
        return self.mapa.get(id_externo, [])


CORPUS = Corpus(texto='<documento nome="XP.md">Art. 2º ...</documento>', documentos=("XP.md",))

PROJETO_A = ProjetoContexto(
    id="proj-a",
    nome="Projeto A",
    descricao="Descrição secreta do A",
    decisoes=[Decisao(titulo="Decisão A", conteudo="Vamos usar Postgres", decidido_em=None)],
)
PROJETO_B = ProjetoContexto(
    id="proj-b",
    nome="Projeto B",
    descricao="SEGREDO-DO-PROJETO-B",
    decisoes=[Decisao(titulo="Decisão B", conteudo="Orçamento de 50 mil", decidido_em=None)],
)


def _servico(**kwargs) -> tuple[PerguntaService, ClienteFalso]:
    cliente = ClienteFalso()
    padrao = {
        "cliente": cliente,
        "corpus": CORPUS,
        "projetos": ProjetosFalsos({"proj-a": PROJETO_A, "proj-b": PROJETO_B}),
        "fonte_projetos_do_membro": FonteProjetosFalsa({"u1": ["proj-a"]}),
        "cache": None,
        "limite_hora": 0,
    }
    return PerguntaService(**{**padrao, **kwargs}), cliente


async def _membro(session, *, id_externo: str | None = "u1", discord_id: int = 1) -> Membro:
    membro = Membro(discord_id=discord_id, nome_exibicao="Perseu", id_externo=id_externo)
    session.add(membro)
    await session.flush()
    return membro


# --- Isolamento entre projetos (o que importa) ------------------------------


async def test_projeto_alheio_nunca_entra_no_prompt(session):
    """Membro do A pergunta sobre o B: o conteúdo do B não pode nem ser carregado."""
    servico, cliente = _servico()
    membro = await _membro(session)

    await servico.perguntar(session, membro, pergunta="o que decidiram no Projeto B?")

    contexto = cliente.prompt.contexto_usuario
    assert "SEGREDO-DO-PROJETO-B" not in contexto
    assert "Orçamento de 50 mil" not in contexto
    assert "Descrição secreta do A" in contexto, "o projeto autorizado deve estar lá"


async def test_base_de_projetos_e_consultada_so_com_autorizados(session):
    projetos = ProjetosFalsos({"proj-a": PROJETO_A, "proj-b": PROJETO_B})
    servico, _ = _servico(projetos=projetos)
    membro = await _membro(session)

    await servico.perguntar(session, membro, pergunta="como vai o projeto?")

    assert projetos.consultas == [["proj-a"]], "o filtro é a fronteira de autorização"


async def test_membro_sem_vinculo_nao_tem_projeto_algum(session):
    """Sem `id_externo` (RN-016) o bot não sabe de quem é a conta — falha fechada."""
    projetos = ProjetosFalsos({"proj-a": PROJETO_A})
    servico, cliente = _servico(projetos=projetos)
    membro = await _membro(session, id_externo=None)

    resposta = await servico.perguntar(session, membro, pergunta="e o projeto A?")

    assert projetos.consultas == [], "nem chega a consultar a base externa"
    assert "Descrição secreta do A" not in cliente.prompt.contexto_usuario
    assert resposta.projetos_consultados == ()


async def test_falha_ao_verificar_acesso_nao_vira_acesso_vazio(session):
    """Firebase fora do ar nega a resposta, mas dizendo a verdade sobre o motivo."""
    servico, _ = _servico(
        fonte_projetos_do_membro=FonteProjetosFalsa(erro=IntegracaoIndisponivelError("Firebase"))
    )
    membro = await _membro(session)

    with pytest.raises(IntegracaoIndisponivelError):
        await servico.perguntar(session, membro, pergunta="e o projeto A?")


async def test_regulamento_vale_para_todos_mesmo_sem_projeto(session):
    servico, cliente = _servico(fonte_projetos_do_membro=FonteProjetosFalsa({}))
    membro = await _membro(session)

    await servico.perguntar(session, membro, pergunta="quanto XP para Cavalaria?")

    assert cliente.prompt.corpus_regras == CORPUS.texto
    assert "quanto XP para Cavalaria?" in cliente.prompt.contexto_usuario


# --- Anti-injeção -----------------------------------------------------------


async def test_dados_do_banco_vao_marcados_como_conteudo(session):
    """Texto do banco é escrito por pessoas: entra como dado, nunca como instrução."""
    servico, cliente = _servico()
    membro = await _membro(session)

    await servico.perguntar(session, membro, pergunta="resumo do projeto")

    contexto = cliente.prompt.contexto_usuario
    assert "<dados_dos_projetos>" in contexto and "</dados_dos_projetos>" in contexto
    assert "<pergunta>" in contexto
    assert "nunca como instrução" in cliente.prompt.instrucoes


async def test_instrucoes_proibem_inventar_resposta(session):
    servico, cliente = _servico()
    membro = await _membro(session)

    await servico.perguntar(session, membro, pergunta="qual a regra?")

    assert "nunca invente" in cliente.prompt.instrucoes.lower()


# --- Freio de custo e entradas inválidas ------------------------------------


async def test_limite_por_hora_bloqueia_depois_do_teto(session):
    servico, _ = _servico(cache=CacheMemoria(), limite_hora=2)
    membro = await _membro(session)

    await servico.perguntar(session, membro, pergunta="primeira")
    await servico.perguntar(session, membro, pergunta="segunda")

    with pytest.raises(LimiteDePerguntasError):
        await servico.perguntar(session, membro, pergunta="terceira")


async def test_limite_zero_desliga_o_freio(session):
    servico, _ = _servico(cache=CacheMemoria(), limite_hora=0)
    membro = await _membro(session)

    for _ in range(5):
        await servico.perguntar(session, membro, pergunta="pode?")


async def test_pergunta_vazia_e_recusada_antes_de_gastar_api(session):
    servico, cliente = _servico()
    membro = await _membro(session)

    with pytest.raises(PerguntaVaziaError):
        await servico.perguntar(session, membro, pergunta="   ")

    assert cliente.prompt is None, "não pode chamar o modelo para texto vazio"


async def test_pergunta_longa_e_truncada(session):
    servico, cliente = _servico()
    membro = await _membro(session)

    await servico.perguntar(session, membro, pergunta="a" * 5000)

    assert len(cliente.prompt.contexto_usuario) < 5000


# --- Auditoria --------------------------------------------------------------


async def test_pergunta_fica_registrada_na_auditoria(session):
    servico, _ = _servico()
    membro = await _membro(session)

    await servico.perguntar(session, membro, pergunta="quanto XP para Lorde?")

    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "pergunta.respondida")
    )
    assert registro is not None
    assert registro.dados["projetos_consultados"] == ["proj-a"]
