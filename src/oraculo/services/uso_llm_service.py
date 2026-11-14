"""Custo da API do Claude: registro de cada chamada, teto diário e orçamento do mês (D15).

* `registrar(uso)` — chamado pelo cliente da Anthropic depois de cada resposta: soma tokens e
  custo estimado na tabela `uso_llm_diario` (sobrevive a reinício) e nos contadores do `/metrics`.
* `verificar()` — chamado antes de cada pergunta: recusa quando o dia ou o mês chegou ao teto.

Falha ao gravar o uso nunca derruba a resposta ao membro (só vira log); falha ao *ler* o uso,
no `verificar`, recusa a pergunta: sem saber quanto já se gastou, o lado seguro é não gastar.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora
from oraculo.domain.custo_llm import UsoLLM, custo_usd, orcamento_esgotado
from oraculo.domain.errors import OrcamentoDeIaEsgotadoError
from oraculo.logging_config import get_logger
from oraculo.observabilidade import REGISTRO, Registro
from oraculo.repositories import uso_llm

log = get_logger(__name__)

AbrirSessao = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def _dia(momento: datetime) -> str:
    return momento.strftime("%Y-%m-%d")


@dataclass(slots=True)
class UsoLlmService:
    abrir_sessao: AbrirSessao
    teto_diario_usd: float = 0.10
    orcamento_mensal_usd: float = 5.0
    registro: Registro = field(default_factory=lambda: REGISTRO)
    relogio: Callable[[], datetime] = agora

    async def registrar(self, uso: UsoLLM) -> None:
        custo = custo_usd(uso)
        reg = self.registro
        reg.contar(
            "oraculo_llm_chamadas_total",
            "Chamadas à API do Claude.",
            modelo=uso.modelo,
            resultado="ok",
        )
        for tipo, valor in (
            ("entrada", uso.entrada),
            ("saida", uso.saida),
            ("cache_escrita", uso.cache_escrita),
            ("cache_leitura", uso.cache_leitura),
        ):
            reg.contar(
                "oraculo_llm_tokens_total",
                "Tokens da API do Claude.",
                valor,
                modelo=uso.modelo,
                tipo=tipo,
            )
        reg.contar(
            "oraculo_llm_custo_usd_total",
            "Custo estimado da API do Claude (US$).",
            custo,
            modelo=uso.modelo,
        )
        try:
            async with self.abrir_sessao() as session:
                await uso_llm.somar(session, _dia(self.relogio()), uso, round(custo * 1_000_000))
        except Exception:  # noqa: BLE001 — registrar custo não pode quebrar a resposta
            log.exception("Não consegui gravar o uso da API do Claude.")

    def registrar_falha(self, modelo: str, resultado: str) -> None:
        self.registro.contar(
            "oraculo_llm_chamadas_total",
            "Chamadas à API do Claude.",
            modelo=modelo,
            resultado=resultado,
        )

    async def custos(self, session: AsyncSession) -> tuple[float, float]:
        """(custo de hoje, custo do mês) em US$, a partir da tabela."""
        hoje = _dia(self.relogio())
        dia = await uso_llm.microdolares_do_dia(session, hoje)
        mes = await uso_llm.microdolares_do_mes(session, hoje[:7])
        return dia / 1_000_000, mes / 1_000_000

    async def verificar(self) -> None:
        try:
            async with self.abrir_sessao() as session:
                hoje, mes = await self.custos(session)
        except Exception as exc:  # noqa: BLE001
            log.exception("Não consegui ler o uso da API do Claude; recuso por segurança.")
            raise OrcamentoDeIaEsgotadoError("diario") from exc
        motivo = orcamento_esgotado(hoje, mes, self.teto_diario_usd, self.orcamento_mensal_usd)
        if motivo is not None:
            self.registro.contar(
                "oraculo_llm_recusas_orcamento_total",
                "Perguntas recusadas porque o orçamento de IA acabou.",
                motivo=motivo,
            )
            raise OrcamentoDeIaEsgotadoError(motivo)


__all__ = ["AbrirSessao", "UsoLlmService"]
