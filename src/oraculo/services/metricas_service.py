"""Métricas operacionais do bot — painel da Sprint 4 (RNF-001 / RNF-004).

Um único ponto coleta os números que interessam a quem opera o clube:
membros por patente e cargo, XP concedido, promoções, agenda, comunicados,
Comunidade/Dracmas, e quando rodaram o último backup e a última importação.
A mesma coleta alimenta o formato Prometheus (`/metrics`, para Grafana ou
qualquer coletor) e o painel HTML (`/painel`).

Só leitura agregada: nenhuma métrica expõe nome, e-mail ou identificador de
membro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora, como_utc
from oraculo.db.models import (
    Agendamento,
    Aldeao,
    Comunicado,
    Membro,
    MovimentacaoXp,
    Promocao,
    RegistroAuditoria,
    StatusAgendamento,
    StatusComunicado,
    TipoAgendamento,
)
from oraculo.domain.hierarchy import PATENTES


@dataclass(slots=True)
class Metrica:
    nome: str
    ajuda: str
    amostras: list[tuple[dict[str, str], float]] = field(default_factory=list)
    tipo: str = "gauge"

    def valor(self, **rotulos: str) -> float:
        """Valor de uma amostra pelos rótulos (0 se não houver) — usado no painel e nos testes."""
        for amostra_rotulos, valor in self.amostras:
            if amostra_rotulos == rotulos:
                return valor
        return 0.0


async def coletar(session: AsyncSession) -> list[Metrica]:
    agora_utc = agora()
    ativo = Membro.ativo.is_(True)

    por_patente = dict(
        (
            await session.execute(
                select(Membro.patente_slug, func.count()).where(ativo).group_by(Membro.patente_slug)
            )
        ).all()
    )
    conselheiros = await session.scalar(
        select(func.count()).select_from(Membro).where(ativo, Membro.conselheiro.is_(True))
    )
    administradores = await session.scalar(
        select(func.count()).select_from(Membro).where(ativo, Membro.administrador.is_(True))
    )
    xp_total = await session.scalar(select(func.coalesce(func.sum(Membro.xp), 0)).where(ativo))
    xp_24h = await session.scalar(
        select(func.coalesce(func.sum(MovimentacaoXp.quantidade), 0)).where(
            MovimentacaoXp.quantidade > 0,
            MovimentacaoXp.criado_em >= agora_utc - timedelta(hours=24),
        )
    )
    promocoes_7d = await session.scalar(
        select(func.count())
        .select_from(Promocao)
        .where(Promocao.criado_em >= agora_utc - timedelta(days=7))
    )
    agenda = dict(
        (
            await session.execute(
                select(Agendamento.tipo, func.count())
                .where(
                    Agendamento.status == StatusAgendamento.AGENDADO,
                    Agendamento.inicio_em >= agora_utc,
                )
                .group_by(Agendamento.tipo)
            )
        ).all()
    )
    comunicados = dict(
        (
            await session.execute(
                select(Comunicado.status, func.count()).group_by(Comunicado.status)
            )
        ).all()
    )
    aldeoes = dict(
        (
            await session.execute(select(Aldeao.suspenso, func.count()).group_by(Aldeao.suspenso))
        ).all()
    )
    dracmas = await session.scalar(select(func.coalesce(func.sum(Aldeao.saldo_dracmas), 0)))

    metricas = [
        Metrica(
            "oraculo_membros_ativos",
            "Membros do Clube ativos no bot.",
            [({}, float(sum(por_patente.values())))],
        ),
        Metrica(
            "oraculo_membros_por_patente",
            "Membros ativos por patente (XP.md Art. 2º).",
            [({"patente": p.slug}, float(por_patente.get(p.slug, 0))) for p in PATENTES],
        ),
        Metrica(
            "oraculo_membros_por_cargo",
            "Membros ativos com cargo institucional.",
            [
                ({"cargo": "conselheiro"}, float(conselheiros or 0)),
                ({"cargo": "administrador"}, float(administradores or 0)),
            ],
        ),
        Metrica("oraculo_xp_total", "Soma do XP dos membros ativos.", [({}, float(xp_total))]),
        Metrica(
            "oraculo_xp_concedido_24h", "XP concedido nas últimas 24 horas.", [({}, float(xp_24h))]
        ),
        Metrica(
            "oraculo_promocoes_7d",
            "Promoções de patente nos últimos 7 dias.",
            [({}, float(promocoes_7d or 0))],
        ),
        Metrica(
            "oraculo_agendamentos_futuros",
            "Reuniões e eventos agendados daqui para frente.",
            [({"tipo": t.value}, float(agenda.get(t, 0))) for t in TipoAgendamento],
        ),
        Metrica(
            "oraculo_comunicados",
            "Comunicados por situação.",
            [({"status": st.value}, float(comunicados.get(st, 0))) for st in StatusComunicado],
        ),
        Metrica(
            "oraculo_aldeoes",
            "Contas da Comunidade (Aldeões).",
            [
                ({"situacao": "ativa"}, float(aldeoes.get(False, 0))),
                ({"situacao": "suspensa"}, float(aldeoes.get(True, 0))),
            ],
        ),
        Metrica(
            "oraculo_dracmas_comunidade",
            "Soma dos saldos de Dracmas da Comunidade.",
            [({}, float(dracmas))],
        ),
    ]

    for acao, nome, ajuda in (
        ("backup.executado", "oraculo_ultimo_backup_timestamp_seconds", "Hora do último backup."),
        (
            "importacao.executada",
            "oraculo_ultima_importacao_timestamp_seconds",
            "Hora da última importação da plataforma.",
        ),
    ):
        quando = await session.scalar(
            select(func.max(RegistroAuditoria.criado_em)).where(RegistroAuditoria.acao == acao)
        )
        metricas.append(
            Metrica(nome, ajuda, [({}, como_utc(quando).timestamp() if quando else 0.0)])
        )
    return metricas


def _escapar_rotulo(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def formato_prometheus(metricas: list[Metrica]) -> str:
    """Exposição em texto do Prometheus (versão 0.0.4)."""
    linhas: list[str] = []
    for metrica in metricas:
        linhas.append(f"# HELP {metrica.nome} {metrica.ajuda}")
        linhas.append(f"# TYPE {metrica.nome} {metrica.tipo}")
        for rotulos, valor in metrica.amostras:
            sufixo = (
                "{" + ",".join(f'{k}="{_escapar_rotulo(v)}"' for k, v in rotulos.items()) + "}"
                if rotulos
                else ""
            )
            linhas.append(f"{metrica.nome}{sufixo} {valor:g}")
    return "\n".join(linhas) + "\n"
