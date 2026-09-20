"""Montagem de `/perguntar` no container — RN-017.

Cada peça degrada sozinha: sem chave de API o comando some; sem regulamento ou
sem base de projetos ele continua existindo, respondendo o que ainda dá.
"""

from __future__ import annotations

from oraculo.config import Settings
from oraculo.container import Container


def _cfg(**kwargs) -> Settings:
    padrao = {
        "_env_file": None,
        "database_url": "sqlite+aiosqlite:///:memory:",
        "discord_token": "token-de-teste",
        "clickup_webhook_secret": "segredo-de-teste",
        "google_enabled": False,
        "redis_url": None,
    }
    return Settings(**{**padrao, **kwargs})


async def test_sem_chave_de_api_o_servico_nao_e_montado():
    container = Container.criar(_cfg())

    assert container.perguntas is None
    await container.fechar()


async def test_com_chave_o_servico_sobe(tmp_path):
    (tmp_path / "XP.md").write_text("Art. 2º", encoding="utf-8")

    container = Container.criar(_cfg(anthropic_api_key="sk-teste", regras_dir=tmp_path))

    assert container.perguntas is not None
    assert container.perguntas.corpus.documentos == ("XP.md",)
    await container.fechar()


async def test_sem_firebase_ninguem_tem_projeto():
    """Sem plataforma configurada não há como autorizar — e é assim que deve ser."""
    container = Container.criar(_cfg(anthropic_api_key="sk-teste"))

    assert container.perguntas is not None
    assert container.perguntas.fonte_projetos_do_membro is None
    assert container.perguntas.projetos is None
    await container.fechar()


async def test_com_firebase_a_fonte_de_autorizacao_e_ligada():
    container = Container.criar(
        _cfg(anthropic_api_key="sk-teste", firebase_project_id="clube-tyto")
    )

    assert container.perguntas is not None
    assert container.perguntas.fonte_projetos_do_membro is not None
    await container.fechar()


async def test_limite_de_perguntas_vem_da_configuracao():
    container = Container.criar(_cfg(anthropic_api_key="sk-teste", pergunta_limite_hora=3))

    assert container.perguntas.limite_hora == 3
    await container.fechar()
