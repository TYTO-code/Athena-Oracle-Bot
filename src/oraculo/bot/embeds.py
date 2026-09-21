"""Embeds padronizados do Bot Oráculo — RF-010 / US-302."""

from __future__ import annotations

from datetime import datetime

import discord

from oraculo.db.base import como_utc
from oraculo.db.models import (
    Aldeao,
    Comunicado,
    MovimentacaoDracmas,
    MovimentacaoXp,
    StatusComunicado,
    TipoMencao,
)
from oraculo.repositories.membros import LinhaRanking
from oraculo.services.notificacao_service import Notificacao, Severidade
from oraculo.services.ranking_service import Perfil

COR = {
    Severidade.INFO: discord.Color.blurple(),
    Severidade.SUCESSO: discord.Color.green(),
    Severidade.ALERTA: discord.Color.orange(),
    Severidade.ERRO: discord.Color.red(),
}

MEDALHAS = {1: "🥇", 2: "🥈", 3: "🥉"}


def de_notificacao(notificacao: Notificacao) -> discord.Embed:
    embed = discord.Embed(
        title=notificacao.titulo,
        description=notificacao.corpo,
        color=COR[notificacao.severidade],
        timestamp=datetime.now().astimezone(),
    )
    for nome, valor in notificacao.campos.items():
        embed.add_field(name=nome, value=valor or "—", inline=True)
    return embed


def erro(mensagem: str, *, titulo: str = "Operação não realizada") -> discord.Embed:
    return discord.Embed(title=f"⚠️ {titulo}", description=mensagem, color=COR[Severidade.ERRO])


def sucesso(mensagem: str, *, titulo: str = "Feito") -> discord.Embed:
    return discord.Embed(title=titulo, description=mensagem, color=COR[Severidade.SUCESSO])


MARCA_STATUS_COMUNICADO = {
    StatusComunicado.AGENDADO: "🗓️",
    StatusComunicado.PUBLICANDO: "📡",
    StatusComunicado.PUBLICADO: "📢",
    StatusComunicado.CANCELADO: "🗑️",
    StatusComunicado.FALHOU: "⚠️",
}

MARCA_MENCAO = {
    TipoMencao.NENHUMA: "",
    TipoMencao.AQUI: " · @here",
    TipoMencao.TODOS: " · @everyone",
}


def lista_comunicados(comunicados: list[Comunicado]) -> discord.Embed:
    """`/comunicados` — RF-015. Mostra também cancelados e falhados: é neles
    que alguém precisa reparar, e RN-010 mantém a linha justamente para isso."""
    embed = discord.Embed(title="📢 Comunicados", color=COR[Severidade.INFO])
    if not comunicados:
        embed.description = "Nenhum comunicado registrado ainda."
        return embed

    for item in comunicados:
        status = StatusComunicado(item.status)
        mencao = TipoMencao(item.mencao)
        linhas = [
            f"<t:{int(como_utc(item.publicar_em).timestamp())}:F> · "
            f"<#{item.canal_id}>{MARCA_MENCAO[mencao]}"
        ]
        if item.motivo_cancelamento:
            linhas.append(f"Cancelado: {item.motivo_cancelamento}")
        if item.erro:
            linhas.append(f"⚠️ {item.erro}")
        embed.add_field(
            name=f"{MARCA_STATUS_COMUNICADO[status]} #{item.id} · {item.titulo}"[:256],
            value="\n".join(linhas)[:1024],
            inline=False,
        )
    return embed


def perfil(dados: Perfil) -> discord.Embed:
    """RF-002 — cargo, XP atual, próximo cargo, XP necessário e posição."""
    membro = dados.membro
    embed = discord.Embed(
        title=f"Perfil de {membro.nome_exibicao}",
        color=COR[Severidade.INFO],
        timestamp=datetime.now().astimezone(),
    )
    embed.add_field(name="Cargo", value=dados.cargo.nome, inline=True)
    embed.add_field(name="XP", value=f"{membro.xp:,}".replace(",", "."), inline=True)
    embed.add_field(name="Ranking", value=f"#{dados.posicao} de {dados.total_membros}", inline=True)

    if dados.no_topo:
        embed.add_field(name="Progressão", value="Topo da progressão automática 🏛️", inline=False)
    else:
        faltam = dados.xp_para_proximo or 0
        embed.add_field(name="Próximo cargo", value=dados.proximo.nome, inline=True)
        embed.add_field(name="XP necessário", value=f"{faltam} XP", inline=True)
        embed.add_field(name="Progresso", value=_barra(membro.xp, dados), inline=False)
    return embed


def ranking(linhas: list[LinhaRanking], *, titulo: str) -> discord.Embed:
    """RF-004 / UC-002."""
    embed = discord.Embed(title=titulo, color=COR[Severidade.INFO])
    if not linhas:
        embed.description = "Nenhum membro com XP no período selecionado."
        return embed
    embed.description = "\n".join(
        f"{MEDALHAS.get(linha.posicao, f'`{linha.posicao:>2}`')} "
        f"**{linha.nome_exibicao}** — {linha.xp} XP"
        for linha in linhas
    )
    return embed


def historico_xp(movimentacoes: list[MovimentacaoXp], *, nome: str) -> discord.Embed:
    """RF-003 / RF-012 — trilha de auditoria legível (TD-006)."""
    embed = discord.Embed(title=f"Histórico de XP — {nome}", color=COR[Severidade.INFO])
    if not movimentacoes:
        embed.description = "Nenhuma movimentação registrada."
        return embed
    for mov in movimentacoes:
        sinal = "＋" if mov.quantidade > 0 else "－"
        embed.add_field(
            name=f"{sinal}{abs(mov.quantidade)} XP · {mov.criado_em:%d/%m/%Y %H:%M}",
            value=f"por **{mov.autor_descricao}** — {mov.motivo}\nsaldo: {mov.saldo_posterior}",
            inline=False,
        )
    return embed


def saldo_dracmas(aldeao: Aldeao | None, *, nome: str) -> discord.Embed:
    """`/saldo` — Comunidade. Sem `Aldeao` ainda, explica como a conta é aberta
    (`COMUNIDADE_E_CLUBE.md` Art. 3º §3º: só no primeiro crédito de Dracmas)."""
    if aldeao is None:
        return discord.Embed(
            title=f"Saldo de Dracmas — {nome}",
            description=(
                "Você ainda não tem conta na Comunidade. Ela é criada automaticamente no "
                "primeiro crédito de Dracmas que você receber (prêmio de torneio, bônus de "
                "venda do Mercador, ou uma doação)."
            ),
            color=COR[Severidade.INFO],
        )
    embed = discord.Embed(
        title=f"Saldo de Dracmas — {nome}",
        color=COR[Severidade.ALERTA] if aldeao.suspenso else COR[Severidade.INFO],
    )
    embed.add_field(name="Saldo", value=f"{aldeao.saldo_dracmas:,}".replace(",", "."), inline=True)
    if aldeao.suspenso:
        embed.add_field(
            name="⚠️ Conta suspensa",
            value="Saldo negativo (DRACMAS.md §4) — reversão exige decisão administrativa.",
            inline=False,
        )
    return embed


def extrato_dracmas(movimentacoes: list[MovimentacaoDracmas], *, nome: str) -> discord.Embed:
    """`/extrato-dracmas` — mesmo formato de `historico_xp`, adaptado à carteira de Dracmas."""
    embed = discord.Embed(title=f"Extrato de Dracmas — {nome}", color=COR[Severidade.INFO])
    if not movimentacoes:
        embed.description = "Nenhuma movimentação registrada."
        return embed
    for mov in movimentacoes:
        sinal = "＋" if mov.valor > 0 else "－"
        embed.add_field(
            name=f"{sinal}{abs(mov.valor)} Dracmas · {mov.criado_em:%d/%m/%Y %H:%M}",
            value=f"{mov.tipo.value} — {mov.motivo}\nsaldo: {mov.saldo_posterior}",
            inline=False,
        )
    return embed


def _barra(xp: int, dados: Perfil, largura: int = 20) -> str:
    """Barra de progresso entre o cargo atual e o próximo."""
    base = dados.cargo.xp_minimo or 0
    alvo = dados.proximo.xp_minimo if dados.proximo else None
    if alvo is None or alvo <= base:
        return "—"
    fracao = min(1.0, max(0.0, (xp - base) / (alvo - base)))
    preenchido = int(fracao * largura)
    return f"`{'█' * preenchido}{'░' * (largura - preenchido)}` {fracao:.0%}"
