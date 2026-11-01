"""Cog de boas-vindas: decide se/onde publica, sem travar a entrada do membro em nenhuma falha.

Testado com um "bot" e um "membro" fakes mínimos (sem subir o cliente Discord de verdade) — o cog só
lê `bot.settings`, chama `bot.get_channel`/`bot.fetch_channel` e envia no canal resolvido.
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from PIL import Image

from oraculo.bot.cogs.boas_vindas import BoasVindasCog

CANAL_ID = 932671175069429862


def _avatar_png() -> bytes:
    saida = io.BytesIO()
    Image.new("RGB", (64, 64), (1, 2, 3)).save(saida, format="PNG")
    return saida.getvalue()


def _membro(avatar_bytes: bytes = b"") -> SimpleNamespace:
    leitura = AsyncMock(return_value=avatar_bytes or _avatar_png())
    avatar = SimpleNamespace(replace=lambda **_: SimpleNamespace(read=leitura))
    return SimpleNamespace(id=42, mention="<@42>", display_avatar=avatar)


class _CanalFalso(discord.abc.Messageable):
    def __init__(self) -> None:
        self.send = AsyncMock()

    async def _get_channel(self):  # pragma: no cover - exigido pela interface, não usado aqui
        raise NotImplementedError


async def test_sem_canal_configurado_nao_faz_nada():
    bot = SimpleNamespace(settings=SimpleNamespace(discord_boas_vindas_channel_id=None))
    cog = BoasVindasCog(bot)

    await cog.on_member_join(_membro())  # não deve levantar nem precisar de get_channel


async def test_publica_banner_no_canal_configurado():
    canal = _CanalFalso()
    bot = SimpleNamespace(
        settings=SimpleNamespace(discord_boas_vindas_channel_id=CANAL_ID),
        get_channel=lambda cid: canal if cid == CANAL_ID else None,
    )
    cog = BoasVindasCog(bot)

    await cog.on_member_join(_membro())

    canal.send.assert_awaited_once()
    _, kwargs = canal.send.await_args
    assert "<@42>" in kwargs["content"]
    assert isinstance(kwargs["file"], discord.File)


async def test_canal_nao_encontrado_nao_levanta():
    resposta_404 = SimpleNamespace(status=404, reason="x")
    bot = SimpleNamespace(
        settings=SimpleNamespace(discord_boas_vindas_channel_id=CANAL_ID),
        get_channel=lambda cid: None,
        fetch_channel=AsyncMock(side_effect=discord.NotFound(resposta_404, "não existe")),
    )
    cog = BoasVindasCog(bot)

    await cog.on_member_join(_membro())


async def test_avatar_invalido_nao_levanta_nem_publica():
    canal = _CanalFalso()
    bot = SimpleNamespace(
        settings=SimpleNamespace(discord_boas_vindas_channel_id=CANAL_ID),
        get_channel=lambda cid: canal,
    )
    cog = BoasVindasCog(bot)

    await cog.on_member_join(_membro(avatar_bytes=b"nao e uma imagem"))

    canal.send.assert_not_awaited()
