"""Entrega por DM dos alertas do Grafana (D15).

A rota `POST /webhooks/grafana` põe o texto na `CAIXA_ALERTAS`; este laço esvazia a caixa a cada
20 segundos e manda tudo numa DM para `ORACULO_ALERTAS_DISCORD_ID` (só Dayvid, de propósito).
Falha passageira do Discord devolve o texto à caixa; DM bloqueada descarta com log.
Sem `ORACULO_ALERTAS_DISCORD_ID` o laço não roda.
"""

from __future__ import annotations

import discord
from discord.ext import commands, tasks

from oraculo.logging_config import get_logger
from oraculo.services.alertas_service import CAIXA_ALERTAS, CaixaDeAlertas

log = get_logger(__name__)

LIMITE_DM = 1900


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
        self.destino: int | None = bot.settings.alertas_discord_id  # type: ignore[attr-defined]
        if self.destino is not None:
            self.laco.start()

    async def cog_unload(self) -> None:
        self.laco.cancel()

    async def _enviar(self, texto: str) -> None:
        assert self.destino is not None
        usuario = self.bot.get_user(self.destino) or await self.bot.fetch_user(self.destino)
        await usuario.send(texto, allowed_mentions=discord.AllowedMentions.none())

    @tasks.loop(seconds=20)
    async def laco(self) -> None:
        try:
            await entregar_alertas(self.caixa, self._enviar)
        except Exception:  # noqa: BLE001 — o laço não pode morrer por uma falha pontual
            log.exception("Alertas: falha no ciclo de entrega")

    @laco.before_loop
    async def _esperar_conexao(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlertasCog(bot))
