"""Entrega de comunicados no Discord — RF-015 / RN-018.

Duas decisões de segurança moram aqui, e as duas são sobre quem é notificado:

* **O texto do comunicado vai no embed, nunca no `content`.** Menção escrita
  dentro de um embed não notifica ninguém — é regra do próprio Discord. Assim,
  um `@everyone` digitado no corpo do aviso aparece como texto e só; o ping
  depende do campo `mencao`, que passou pela política de permissões (RN-008).
* **`allowed_mentions` é sempre explícito.** O padrão do discord.py permite
  `@everyone` quando o bot tem a permissão no canal; aqui ele é derivado do
  campo `mencao` a cada envio, então o silêncio é o padrão de fato.
"""

from __future__ import annotations

import discord

from oraculo.db.models import Comunicado, TipoMencao
from oraculo.logging_config import get_logger

log = get_logger(__name__)

PREFIXO_MENCAO: dict[TipoMencao, str | None] = {
    TipoMencao.NENHUMA: None,
    TipoMencao.AQUI: "@here",
    TipoMencao.TODOS: "@everyone",
}


def permissoes_de_mencao(mencao: TipoMencao) -> discord.AllowedMentions:
    """Traduz o campo `mencao` no que o Discord tem permissão de notificar."""
    if mencao is TipoMencao.NENHUMA:
        return discord.AllowedMentions.none()
    # `@here` e `@everyone` são controlados pela mesma flag na API.
    return discord.AllowedMentions(everyone=True, users=False, roles=False, replied_user=False)


def montar_embed(comunicado: Comunicado) -> discord.Embed:
    embed = discord.Embed(
        title=f"📢 {comunicado.titulo}"[:256],
        description=comunicado.corpo[:4096],
        color=discord.Color.gold(),
        timestamp=comunicado.publicar_em,
    )
    embed.set_footer(text=f"Comunicado oficial do Clube TYTO · #{comunicado.id}")
    return embed


class CanalNaoEncontradoError(RuntimeError):
    """Canal configurado não existe, ou o bot não enxerga/escreve nele."""


class ComunicadorDiscord:
    """Publicador real — o que o ciclo em `cogs/comunicados.py` usa."""

    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot

    async def publicar(self, comunicado: Comunicado) -> int:
        canal = await self._resolver_canal(comunicado.canal_id)
        mencao = TipoMencao(comunicado.mencao)
        mensagem = await canal.send(
            content=PREFIXO_MENCAO[mencao],
            embed=montar_embed(comunicado),
            allowed_mentions=permissoes_de_mencao(mencao),
        )
        log.info("Comunicado %s publicado em %s.", comunicado.id, comunicado.canal_id)
        return mensagem.id

    async def _resolver_canal(self, canal_id: int) -> discord.abc.Messageable:
        canal = self._bot.get_channel(canal_id)
        if canal is None:
            try:
                canal = await self._bot.fetch_channel(canal_id)
            except discord.HTTPException as exc:
                raise CanalNaoEncontradoError(
                    f"Canal {canal_id} inacessível para o bot: {exc}"
                ) from exc
        if not isinstance(canal, discord.abc.Messageable):
            raise CanalNaoEncontradoError(
                f"Canal {canal_id} não aceita mensagens (é categoria ou canal de voz?)."
            )
        return canal
