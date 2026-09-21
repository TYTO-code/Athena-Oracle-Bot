"""Ligação do ciclo de publicação ao cliente Discord — RF-015.

O ciclo só pode começar depois do `on_ready`: antes disso o cliente não resolve
canal nenhum, e um publicador registrado cedo demais falharia em silêncio.
"""

from __future__ import annotations

import pytest

from oraculo.bot.client import OraculoBot
from oraculo.bot.comunicador import ComunicadorDiscord

EXTENSAO = "oraculo.bot.cogs.comunicados"


@pytest.fixture
async def bot_com_cog(settings):
    async def _criar(intervalo: int):
        cfg = settings.model_copy(update={"comunicados_intervalo_segundos": intervalo})
        cliente = OraculoBot(cfg)
        await cliente.load_extension(EXTENSAO)
        return cliente, cliente.get_cog("ComunicadosCog")

    criados: list[OraculoBot] = []

    async def fabrica(intervalo: int):
        cliente, cog = await _criar(intervalo)
        criados.append(cliente)
        return cliente, cog

    try:
        yield fabrica
    finally:
        for cliente in criados:
            cog = cliente.get_cog("ComunicadosCog")
            if cog is not None:
                await cog.cog_unload()
            await cliente.container.fechar()


async def test_ciclo_so_comeca_depois_do_on_ready(bot_com_cog):
    cliente, cog = await bot_com_cog(60)

    assert not cog.publicar_programados.is_running()
    assert not cliente.container.comunicados.habilitado, "sem cliente pronto, sem publicador"

    await cog.on_ready()

    assert cog.publicar_programados.is_running()
    assert cliente.container.comunicados.habilitado


async def test_on_ready_repetido_nao_duplica_o_ciclo(bot_com_cog):
    """Reconexão ao Discord dispara `on_ready` de novo — e não pode dobrar a publicação."""
    _, cog = await bot_com_cog(60)

    await cog.on_ready()
    await cog.on_ready()

    assert cog.publicar_programados.is_running()


async def test_intervalo_zero_desliga_o_ciclo(bot_com_cog):
    cliente, cog = await bot_com_cog(0)

    await cog.on_ready()

    assert not cog.publicar_programados.is_running()
    assert not cliente.container.comunicados.habilitado


async def test_publicador_registrado_e_o_do_discord(bot_com_cog):
    cliente, cog = await bot_com_cog(60)

    await cog.on_ready()

    assert isinstance(cog._servico._publicador, ComunicadorDiscord)
    assert cog._servico is cliente.container.comunicados


async def test_intervalo_configurado_vale_no_loop(bot_com_cog):
    _, cog = await bot_com_cog(15)

    await cog.on_ready()

    assert cog.publicar_programados.seconds == 15


async def test_volta_do_ciclo_e_pulada_sem_cliente_pronto(bot_com_cog, monkeypatch):
    """Reconexão em andamento: pular a volta é melhor que tentar publicar às cegas."""
    _, cog = await bot_com_cog(60)

    async def nunca(*_args, **_kwargs):
        raise AssertionError("o ciclo não pode publicar sem cliente pronto")

    monkeypatch.setattr(cog._servico, "publicar_pendentes", nunca)

    await cog.publicar_programados.coro(cog)
