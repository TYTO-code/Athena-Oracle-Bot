"""Entrega por DM dos alertas do Grafana (D15).

A rota `POST /webhooks/grafana` põe o texto na `CAIXA_ALERTAS`; este laço esvazia a caixa a cada
20 segundos e manda tudo por DM a quem tem o cargo de Rex na plataforma (a TYTO.club-API diz
quem é, e a resposta vale por 10 minutos). Se a plataforma não responder ou o Rex não tiver ID do
Discord no cadastro, vai para `ORACULO_ALERTAS_DISCORD_ID`, que é só a reserva.
Falha passageira do Discord devolve o texto à caixa; DM bloqueada descarta com log.
Sem a plataforma configurada e sem a reserva o laço não roda.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import discord
from discord.ext import commands, tasks

from oraculo.domain.alertas_grafana import escolher_destinos
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.integrations.gerente_api import FonteGerente, criar_fonte_gerente
from oraculo.logging_config import get_logger
from oraculo.services.alertas_service import CAIXA_ALERTAS, CaixaDeAlertas

log = get_logger(__name__)

LIMITE_DM = 1900
VALIDADE_DESTINO_SEGUNDOS = 600


class Destinatarios:
    """Resolve quem recebe os alertas, guardando a última resposta da plataforma."""

    def __init__(
        self,
        fonte: FonteGerente | None,
        reserva: int | None,
        agora: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fonte = fonte
        self._reserva = reserva
        self._agora = agora
        self._do_rex: list[int] | None = None
        self._lido_em: float | None = None

    async def resolver(self) -> list[int]:
        vencido = self._lido_em is None or self._agora() - self._lido_em > VALIDADE_DESTINO_SEGUNDOS
        if self._fonte is not None and vencido:
            try:
                self._do_rex = await self._fonte.destino_alertas()
                self._lido_em = self._agora()
            except IntegracaoIndisponivelError:
                log.warning("Alertas: plataforma sem resposta; uso o último destino conhecido.")
        return escolher_destinos(self._do_rex, self._reserva)


async def entregar_alertas(caixa: CaixaDeAlertas, enviar) -> int:  # type: ignore[no-untyped-def]
    """Esvazia a caixa e envia cada texto; devolve à caixa o que falhar de forma passageira."""
    entregues = 0
    pendentes = caixa.retirar_todos()
    for i, texto in enumerate(pendentes):
        try:
            await enviar(texto[:LIMITE_DM])
            entregues += 1
        except (discord.Forbidden, discord.NotFound):
            log.warning("Alertas: DM recusada pelo Discord; alerta descartado.")
        except discord.HTTPException as exc:
            log.warning("Alertas: DM falhou (%s); volta para a caixa.", exc)
            for resto in pendentes[i:]:
                caixa.devolver(resto)
            break
    return entregues


class AlertasCog(commands.Cog):
    def __init__(self, bot: commands.Bot, caixa: CaixaDeAlertas = CAIXA_ALERTAS) -> None:
        self.bot = bot
        self.caixa = caixa
        cfg = bot.settings  # type: ignore[attr-defined]
        self.destinatarios = Destinatarios(criar_fonte_gerente(cfg), cfg.alertas_discord_id)
        self._destinos: list[int] = []
        if cfg.gerente_habilitado or cfg.alertas_discord_id is not None:
            self.laco.start()

    async def cog_unload(self) -> None:
        self.laco.cancel()

    async def _enviar(self, texto: str) -> None:
        """Manda a cada destinatário; só falha se ninguém recebeu (aí vale o erro do último)."""
        erro: discord.HTTPException | None = None
        entregue = False
        for destino in self._destinos:
            try:
                usuario = self.bot.get_user(destino) or await self.bot.fetch_user(destino)
                await usuario.send(texto, allowed_mentions=discord.AllowedMentions.none())
                entregue = True
            except discord.HTTPException as exc:
                erro = exc
        if not entregue and erro is not None:
            raise erro

    @tasks.loop(seconds=20)
    async def laco(self) -> None:
        try:
            self._destinos = await self.destinatarios.resolver()
            if not self._destinos:
                return  # sem destinatário ainda: os alertas esperam na caixa
            await entregar_alertas(self.caixa, self._enviar)
        except Exception:  # noqa: BLE001 — o laço não pode morrer por uma falha pontual
            log.exception("Alertas: falha no ciclo de entrega")

    @laco.before_loop
    async def _esperar_conexao(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlertasCog(bot))
