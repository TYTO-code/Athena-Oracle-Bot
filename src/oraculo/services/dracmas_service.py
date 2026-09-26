"""Carteira de Dracmas da camada Comunidade — `Institucional/DRACMAS.md` e `COMUNIDADE_E_CLUBE.md`.

**Escopo:** só a camada Comunidade (`Aldeao`). Decisão de arquitetura (F2-006): os Dracmas do
Clube vivem **só na plataforma** (TYTO.club-API), que já cobra a taxa mensal de manutenção —
o bot não mantém um segundo saldo de Clube. Na filiação, o saldo do Aldeão é transferido para a
plataforma por `filiacao_service.py` (`COMUNIDADE_E_CLUBE.md` Art. 4º §1º-A), e a conta de
Aldeão migrada não recebe nem movimenta mais nada aqui. `Membro.dracmas` fica sem uso.

**Decisão de implementação — conciliação Art. 3º §1º × §3º:**
`COMUNIDADE_E_CLUBE.md` Art. 3º §1º diz que o ingresso custa 30.000 Dracmas; o §3º diz que um
prêmio em Dracmas a um Visitante "constitui, ao mesmo tempo, ingresso automático na Comunidade
— não há Dracmas sem conta que os receba (Art. 1º §1º)". A leitura adotada aqui: o §3º descreve
a *necessidade mecânica* de abrir a conta (não existe onde guardar o crédito sem ela), não uma
isenção da taxa do §1º — a isenção é uma coisa à parte, prevista explicitamente no §2º só para
casos nomeados (ex.: 1º colocado do Torneio de Hacking, `TORNEIOS.md` Art. 7º §5º). Por isso,
`creditar()` sempre cobra os 30.000 de ingresso na mesma operação que cria a conta, salvo quando
o chamador passa `dispensa_taxa_ingresso=True` para um desses casos nomeados — e essa cobrança
pode deixar o saldo negativo e suspender a conta na hora, o que é consistente com por que o §2º
precisou existir como exceção: sem um custo padrão, não haveria nada para a exceção dispensar.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora
from oraculo.db.models import Aldeao, MovimentacaoDracmas, TipoMovimentacaoDracmas
from oraculo.domain.errors import (
    ContaComunidadeMigradaError,
    ContaDracmasSuspensaError,
    MotivoDracmasObrigatorioError,
    QuantidadeDracmasInvalidaError,
    SaldoDracmasInsuficienteError,
)
from oraculo.logging_config import get_logger
from oraculo.repositories import dracmas as repo_dracmas

log = get_logger(__name__)

#: COMUNIDADE_E_CLUBE.md Art. 3º §1º.
CUSTO_INGRESSO_COMUNIDADE = 30_000
#: COMUNIDADE_E_CLUBE.md Art. 4º §1º — ainda sem comando (fase do Clube não implementada aqui).
CUSTO_INGRESSO_CLUBE = 70_000

MOTIVO_MIN_CARACTERES = 3


@dataclass(slots=True)
class ResultadoDracmas:
    """Retorno de uma operação de carteira, pronto para virar embed/resposta."""

    aldeao: Aldeao
    movimentacao: MovimentacaoDracmas
    saldo_anterior: int
    saldo_atual: int
    criado_agora: bool = False
    movimentacao_ingresso: MovimentacaoDracmas | None = None
    suspenso_agora: bool = False

    @property
    def ingresso_cobrado(self) -> bool:
        return self.movimentacao_ingresso is not None


class DracmasService:
    """Casos de uso de crédito, débito e doação de Dracmas na camada Comunidade."""

    async def creditar(
        self,
        session: AsyncSession,
        *,
        discord_id: int,
        valor: int,
        tipo: TipoMovimentacaoDracmas,
        motivo: str,
        origem_referencia: str | None = None,
        autor_descricao: str = "sistema",
        dispensa_taxa_ingresso: bool = False,
    ) -> ResultadoDracmas:
        """Credita Dracmas a `discord_id`, criando a conta de Aldeão se ainda não existir.

        Ver o docstring do módulo para a regra de cobrança automática de ingresso no primeiro
        crédito.
        """
        valor = self._validar_valor(valor)
        motivo_limpo = self._validar_motivo(motivo)

        aldeao = await repo_dracmas.buscar_aldeao_por_discord(session, discord_id)
        criado_agora = aldeao is None
        if aldeao is None:
            aldeao = await repo_dracmas.criar_aldeao(session, discord_id=discord_id)
        else:
            aldeao = await repo_dracmas.bloquear_aldeao(session, aldeao)
            if aldeao.migrado:
                raise ContaComunidadeMigradaError(discord_id)
        # Diferente de `debitar`, crédito nunca é bloqueado por `aldeao.suspenso` — é o único
        # jeito de um saldo negativo se recuperar; DRACMAS.md §4 só exige decisão administrativa
        # para *reverter* a suspensão em si, não impede a conta de receber Dracmas enquanto isso.

        saldo_anterior = aldeao.saldo_dracmas
        saldo_posterior = saldo_anterior + valor
        aldeao.saldo_dracmas = saldo_posterior

        movimentacao = await repo_dracmas.registrar_movimentacao(
            session,
            aldeao=aldeao,
            tipo=tipo,
            valor=valor,
            saldo_anterior=saldo_anterior,
            saldo_posterior=saldo_posterior,
            motivo=motivo_limpo,
            origem_referencia=origem_referencia,
            autor_descricao=autor_descricao,
        )

        resultado = ResultadoDracmas(
            aldeao=aldeao,
            movimentacao=movimentacao,
            saldo_anterior=saldo_anterior,
            saldo_atual=saldo_posterior,
            criado_agora=criado_agora,
        )

        if criado_agora and not dispensa_taxa_ingresso:
            resultado = await self._cobrar_ingresso(session, resultado)

        log.info(
            "Dracmas +%d para aldeao=%s (tipo=%s, motivo=%r, saldo %d → %d, criado_agora=%s)",
            valor,
            aldeao.discord_id,
            tipo.value,
            motivo_limpo,
            saldo_anterior,
            resultado.saldo_atual,
            criado_agora,
        )
        return resultado

    async def debitar(
        self,
        session: AsyncSession,
        *,
        aldeao: Aldeao,
        valor: int,
        tipo: TipoMovimentacaoDracmas,
        motivo: str,
        origem_referencia: str | None = None,
        autor_descricao: str = "sistema",
    ) -> ResultadoDracmas:
        """Debita Dracmas de uma conta já existente. O saldo pode ficar negativo — é esse
        resultado que aciona a suspensão automática (`DRACMAS.md` §4), não algo que este método
        previne.
        """
        valor = self._validar_valor(valor)
        motivo_limpo = self._validar_motivo(motivo)

        aldeao = await repo_dracmas.bloquear_aldeao(session, aldeao)
        if aldeao.migrado:
            raise ContaComunidadeMigradaError(aldeao.discord_id)
        if aldeao.suspenso:
            raise ContaDracmasSuspensaError(aldeao.discord_id)

        saldo_anterior = aldeao.saldo_dracmas
        saldo_posterior = saldo_anterior - valor
        aldeao.saldo_dracmas = saldo_posterior

        suspenso_agora = False
        if saldo_posterior < 0:
            aldeao.suspenso = True
            aldeao.suspenso_em = agora()
            suspenso_agora = True

        movimentacao = await repo_dracmas.registrar_movimentacao(
            session,
            aldeao=aldeao,
            tipo=tipo,
            valor=-valor,
            saldo_anterior=saldo_anterior,
            saldo_posterior=saldo_posterior,
            motivo=motivo_limpo,
            origem_referencia=origem_referencia,
            autor_descricao=autor_descricao,
        )

        if suspenso_agora:
            log.warning(
                "Conta de Dracmas suspensa: aldeao=%s saldo caiu para %d após débito de %d "
                "(tipo=%s) — reversão exige decisão administrativa (DRACMAS.md §4).",
                aldeao.discord_id,
                saldo_posterior,
                valor,
                tipo.value,
            )

        return ResultadoDracmas(
            aldeao=aldeao,
            movimentacao=movimentacao,
            saldo_anterior=saldo_anterior,
            saldo_atual=saldo_posterior,
            suspenso_agora=suspenso_agora,
        )

    async def debitar_exigindo_saldo(
        self,
        session: AsyncSession,
        *,
        aldeao: Aldeao,
        valor: int,
        tipo: TipoMovimentacaoDracmas,
        motivo: str,
        origem_referencia: str | None = None,
        autor_descricao: str = "sistema",
    ) -> ResultadoDracmas:
        """Como `debitar`, mas recusa a operação se o saldo não cobrir o valor — para comandos
        voluntários (ex.: doação) onde deixar o doador negativo não faz sentido de negócio, ao
        contrário de uma cobrança compulsória (ex.: ingresso, taxa)."""
        if aldeao.saldo_dracmas < valor:
            raise SaldoDracmasInsuficienteError(aldeao.saldo_dracmas, valor)
        return await self.debitar(
            session,
            aldeao=aldeao,
            valor=valor,
            tipo=tipo,
            motivo=motivo,
            origem_referencia=origem_referencia,
            autor_descricao=autor_descricao,
        )

    async def doar(
        self,
        session: AsyncSession,
        *,
        discord_id_origem: int,
        discord_id_destino: int,
        valor: int,
        motivo: str,
        autor_descricao: str,
    ) -> tuple[ResultadoDracmas, ResultadoDracmas]:
        """`DRACMAS.md` §2 "Doação livre entre membros", generalizada a qualquer titular de saldo
        da camada Comunidade — debita de quem doa, credita a quem recebe (criando a conta do
        destinatário se for a primeira vez, com a mesma cobrança de ingresso de `creditar`)."""
        origem = await repo_dracmas.buscar_aldeao_por_discord(session, discord_id_origem)
        if origem is None:
            raise SaldoDracmasInsuficienteError(0, valor)

        resultado_debito = await self.debitar_exigindo_saldo(
            session,
            aldeao=origem,
            valor=valor,
            tipo=TipoMovimentacaoDracmas.DOACAO,
            motivo=motivo,
            origem_referencia=f"doacao_de:{discord_id_origem}",
            autor_descricao=autor_descricao,
        )
        resultado_credito = await self.creditar(
            session,
            discord_id=discord_id_destino,
            valor=valor,
            tipo=TipoMovimentacaoDracmas.DOACAO,
            motivo=motivo,
            origem_referencia=f"doacao_para:{discord_id_destino}",
            autor_descricao=autor_descricao,
        )
        return resultado_debito, resultado_credito

    # -- Consultas ---------------------------------------------------------

    async def saldo_de(self, session: AsyncSession, discord_id: int) -> Aldeao | None:
        return await repo_dracmas.buscar_aldeao_por_discord(session, discord_id)

    async def extrato_de(
        self, session: AsyncSession, discord_id: int, *, limite: int = 20
    ) -> list[MovimentacaoDracmas]:
        aldeao = await repo_dracmas.buscar_aldeao_por_discord(session, discord_id)
        if aldeao is None:
            return []
        return await repo_dracmas.historico_de_aldeao(session, aldeao_id=aldeao.id, limite=limite)

    # -- Interno -------------------------------------------------------------

    async def _cobrar_ingresso(
        self, session: AsyncSession, resultado: ResultadoDracmas
    ) -> ResultadoDracmas:
        resultado_ingresso = await self.debitar(
            session,
            aldeao=resultado.aldeao,
            valor=CUSTO_INGRESSO_COMUNIDADE,
            tipo=TipoMovimentacaoDracmas.INGRESSO_COMUNIDADE,
            motivo="Ingresso na Comunidade (COMUNIDADE_E_CLUBE.md Art. 3º §1º)",
            autor_descricao="sistema",
        )
        return ResultadoDracmas(
            aldeao=resultado_ingresso.aldeao,
            movimentacao=resultado.movimentacao,
            saldo_anterior=resultado.saldo_anterior,
            saldo_atual=resultado_ingresso.saldo_atual,
            criado_agora=resultado.criado_agora,
            movimentacao_ingresso=resultado_ingresso.movimentacao,
            suspenso_agora=resultado_ingresso.suspenso_agora,
        )

    @staticmethod
    def _validar_valor(valor: int) -> int:
        if not isinstance(valor, int) or valor <= 0:
            raise QuantidadeDracmasInvalidaError(valor)
        return valor

    @staticmethod
    def _validar_motivo(motivo: str) -> str:
        limpo = (motivo or "").strip()
        if len(limpo) < MOTIVO_MIN_CARACTERES:
            raise MotivoDracmasObrigatorioError()
        return limpo[:500]
