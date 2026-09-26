"""Filiação ao Clube: migração do saldo da Comunidade — F2-007.

`COMUNIDADE_E_CLUBE.md` Art. 4º §1º-A: ao migrar para o Clube, o saldo
**inteiro** do Aldeão é transferido para a conta de Membro; a linha de Aldeão
permanece (nunca é apagada) como referência histórica, com o saldo zerado.

Como os Dracmas do Clube vivem só na plataforma (decisão de F2-006), a conta
de Membro de destino é a da plataforma, identificada pelo `id_externo` do
vínculo Discord↔plataforma (RN-016).

Ordem das operações, escolhida para nunca perder nem duplicar Dracmas:

1. valida tudo localmente (conta existe, não migrada, não suspensa, membro
   vinculado à plataforma);
2. credita na plataforma — idempotente por `aldeao:<id>`;
3. só então zera o Aldeão, grava a saída no ledger e marca a migração.

Se o passo 3 falhar depois do 2, repetir a migração é seguro: a plataforma
reconhece a referência e não credita de novo.

**Fora deste serviço, de propósito:** a cobrança do ingresso no Clube (70.000,
Art. 4º §1º). A ordem entre ingresso e migração e de qual saldo ele sai estão
no texto de `COMUNIDADE_E_CLUBE.md`, que não está disponível neste repositório
— não se inventa regra de Regulamento (ver `.claude/rules/institucional-is-law.md`).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora
from oraculo.db.models import Aldeao, Membro, OrigemAcao, TipoMovimentacaoDracmas
from oraculo.domain.errors import (
    BusinessRuleError,
    ContaComunidadeMigradaError,
    ContaDracmasSuspensaError,
    IntegracaoIndisponivelError,
    RecursoNaoEncontradoError,
)
from oraculo.domain.permissions import Acao, exigir
from oraculo.integrations.economia_plataforma import EconomiaPlataforma
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria
from oraculo.repositories import dracmas as repo_dracmas

log = get_logger(__name__)


class MembroSemVinculoNaPlataformaError(BusinessRuleError):
    """Sem `id_externo` não há conta de Membro na plataforma para receber o saldo (RN-016)."""

    regra = "RN-016"

    def __init__(self, nome: str) -> None:
        super().__init__(
            f"{nome} ainda não está vinculado à plataforma (/vincular-conta) — não há conta "
            "de Membro para receber o saldo da Comunidade."
        )


@dataclass(slots=True)
class ResultadoMigracao:
    aldeao: Aldeao
    membro: Membro
    valor: int


class FiliacaoService:
    def __init__(self, economia: EconomiaPlataforma | None) -> None:
        self._economia = economia

    async def migrar_saldo_para_clube(
        self,
        session: AsyncSession,
        *,
        membro: Membro,
        autor: Membro,
        origem: OrigemAcao = OrigemAcao.DISCORD,
        guild_id: int | None = None,
    ) -> ResultadoMigracao:
        exigir(autor.perfil, Acao.MIGRAR_SALDO_COMUNIDADE)

        if membro.discord_id is None:
            raise RecursoNaoEncontradoError("Conta de Comunidade", "membro sem Discord")
        aldeao = await repo_dracmas.buscar_aldeao_por_discord(session, membro.discord_id)
        if aldeao is None:
            raise RecursoNaoEncontradoError("Conta de Comunidade", membro.discord_id)
        aldeao = await repo_dracmas.bloquear_aldeao(session, aldeao)

        if aldeao.migrado:
            raise ContaComunidadeMigradaError(aldeao.discord_id)
        if aldeao.suspenso or aldeao.saldo_dracmas < 0:
            # DRACMAS.md §4 — conta suspensa não movimenta até reversão manual.
            raise ContaDracmasSuspensaError(aldeao.discord_id)
        if not membro.id_externo:
            raise MembroSemVinculoNaPlataformaError(membro.nome_exibicao)

        valor = aldeao.saldo_dracmas
        referencia = f"aldeao:{aldeao.id}"

        if valor > 0:
            if self._economia is None:
                raise IntegracaoIndisponivelError(
                    "Plataforma",
                    "ORACULO_PLATAFORMA_API_URL/ORACULO_PLATAFORMA_API_CHAVE não configurados",
                )
            await self._economia.migrar_saldo_comunidade(
                id_externo=membro.id_externo, valor=valor, referencia=referencia
            )
            aldeao.saldo_dracmas = 0
            await repo_dracmas.registrar_movimentacao(
                session,
                aldeao=aldeao,
                tipo=TipoMovimentacaoDracmas.MIGRACAO_CLUBE,
                valor=-valor,
                saldo_anterior=valor,
                saldo_posterior=0,
                motivo=(
                    "Saldo migrado para o Clube na filiação "
                    "(COMUNIDADE_E_CLUBE.md Art. 4º §1º-A)"
                ),
                origem_referencia=f"plataforma:{membro.id_externo}",
                autor_descricao=autor.nome_exibicao,
            )

        aldeao.migrado_para_membro_id = membro.id
        aldeao.migrado_em = agora()
        await session.flush()

        await auditoria.registrar(
            session,
            acao="comunidade.saldo_migrado",
            resumo=(
                f"{membro.nome_exibicao}: {valor} Dracmas da Comunidade migrados para o Clube"
            ),
            ator=autor,
            alvo_tipo="membro",
            alvo_id=membro.id,
            dados={"aldeao_id": aldeao.id, "valor": valor, "referencia": referencia},
            origem=origem,
            guild_id=guild_id,
        )
        log.info("Saldo da Comunidade migrado: aldeao=%s valor=%d", aldeao.id, valor)
        return ResultadoMigracao(aldeao=aldeao, membro=membro, valor=valor)
