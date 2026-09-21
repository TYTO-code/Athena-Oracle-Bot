"""Quem o comunicado tem direito de notificar — RN-018.

O ponto destes testes não é o embed ficar bonito: é garantir que um `@everyone`
só sai quando alguém com cargo para isso pediu, e nunca porque a palavra
apareceu no texto do aviso.
"""

from __future__ import annotations

import discord
import pytest

from oraculo.bot.cogs.comunicados import texto_do_corpo
from oraculo.bot.comunicador import (
    PREFIXO_MENCAO,
    CanalNaoEncontradoError,
    ComunicadorDiscord,
    montar_embed,
    permissoes_de_mencao,
)
from oraculo.db.base import agora
from oraculo.db.models import Comunicado, TipoMencao


class CanalFalso(discord.abc.Messageable):
    def __init__(self) -> None:
        self.enviados: list[dict] = []

    async def _get_channel(self):  # pragma: no cover - exigido pela ABC
        return self

    async def send(self, content=None, *, embed=None, allowed_mentions=None):
        self.enviados.append(
            {"content": content, "embed": embed, "allowed_mentions": allowed_mentions}
        )
        return type("Mensagem", (), {"id": 4242})()


class BotFalso:
    def __init__(self, canal=None) -> None:
        self.canal = canal

    def get_channel(self, _id):
        return self.canal


def comunicado(*, corpo="Assembleia amanhã.", mencao=TipoMencao.NENHUMA) -> Comunicado:
    return Comunicado(
        id=7,
        titulo="Assembleia",
        corpo=corpo,
        canal_id=123,
        mencao=mencao,
        publicar_em=agora(),
        autor_id=1,
    )


# -- Menções ----------------------------------------------------------------


async def test_sem_mencao_nao_notifica_ninguem():
    canal = CanalFalso()
    await ComunicadorDiscord(BotFalso(canal)).publicar(comunicado())

    enviado = canal.enviados[0]
    assert enviado["content"] is None
    assert enviado["allowed_mentions"].everyone is False


@pytest.mark.parametrize(
    ("mencao", "prefixo"),
    [(TipoMencao.AQUI, "@here"), (TipoMencao.TODOS, "@everyone")],
)
async def test_mencao_pedida_vai_no_content(mencao, prefixo):
    canal = CanalFalso()
    await ComunicadorDiscord(BotFalso(canal)).publicar(comunicado(mencao=mencao))

    enviado = canal.enviados[0]
    assert enviado["content"] == prefixo
    assert enviado["allowed_mentions"].everyone is True


async def test_everyone_escrito_no_corpo_nao_notifica():
    """A defesa é estrutural: o texto vai no embed, e menção dentro de embed
    não notifica. Quem digita o aviso não consegue forçar um ping."""
    canal = CanalFalso()
    texto = "Pessoal @everyone @here <@1234> compareçam!"

    await ComunicadorDiscord(BotFalso(canal)).publicar(comunicado(corpo=texto))

    enviado = canal.enviados[0]
    assert enviado["content"] is None
    assert texto in enviado["embed"].description
    assert enviado["allowed_mentions"].everyone is False
    assert enviado["allowed_mentions"].users is False
    assert enviado["allowed_mentions"].roles is False


async def test_permissoes_sao_sempre_explicitas():
    """O padrão do discord.py permite `@everyone`; aqui nada é deixado ao padrão."""
    for mencao in TipoMencao:
        permissoes = permissoes_de_mencao(mencao)
        assert isinstance(permissoes, discord.AllowedMentions)
        assert permissoes.users is False
        assert permissoes.roles is False


async def test_todo_tipo_de_mencao_tem_prefixo_definido():
    """Um valor novo no enum sem prefixo quebraria o envio em produção."""
    assert set(PREFIXO_MENCAO) == set(TipoMencao)


# -- Conteúdo ---------------------------------------------------------------


async def test_corpo_vai_para_a_descricao_do_embed():
    embed = montar_embed(comunicado(corpo="Linha 1\nLinha 2"))

    assert embed.description == "Linha 1\nLinha 2"
    assert "Assembleia" in embed.title


async def test_barra_n_digitado_vira_quebra_de_linha():
    """Slash command não aceita Enter: `\\n` é como se escreve parágrafo."""
    assert texto_do_corpo("Primeira.\\nSegunda.") == "Primeira.\nSegunda."


# -- Canal ------------------------------------------------------------------


async def test_canal_invisivel_vira_erro_tratavel():
    class BotSemCanal:
        def get_channel(self, _id):
            return None

        async def fetch_channel(self, _id):
            resposta = type("Resposta", (), {"status": 404, "reason": "Not Found"})()
            raise discord.HTTPException(resposta, "Unknown Channel")

    with pytest.raises(CanalNaoEncontradoError):
        await ComunicadorDiscord(BotSemCanal()).publicar(comunicado())


async def test_canal_que_nao_aceita_mensagem_vira_erro_tratavel():
    """Categoria ou canal de voz configurado por engano não pode virar traceback."""
    with pytest.raises(CanalNaoEncontradoError):
        await ComunicadorDiscord(BotFalso(object())).publicar(comunicado())
