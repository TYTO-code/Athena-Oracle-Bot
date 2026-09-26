"""Comunicados oficiais do clube — RF-015 / RN-018.

Três garantias que o serviço existe para sustentar:

1. **Quem pode falar pelo clube é decidido pela política central** (RN-008):
   publicar exige a patente Oficial+, e notificar o servidor inteiro
   (`@everyone`/`@here`) exige o cargo Conselheiro — um degrau acima, porque o
   custo de errar é o servidor inteiro recebendo um ping.
2. **Um comunicado programado publica uma vez, ou não publica** — nunca duas.
   A reserva (AGENDADO → PUBLICANDO, com commit antes de falar com o Discord) é
   o que sustenta isso mesmo se o processo morrer no meio do envio.
3. **Comunicado atrasado demais não vai ao ar sozinho.** Se o bot ficou fora do
   ar, o aviso de segunda não é publicado na quinta: ele é encerrado como
   `FALHOU` e aparece em `/comunicados` para alguém decidir o que fazer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora, como_utc
from oraculo.db.models import (
    Comunicado,
    Membro,
    OrigemAcao,
    StatusComunicado,
    TipoMencao,
)
from oraculo.domain.errors import BusinessRuleError
from oraculo.domain.permissions import Acao, exigir
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria
from oraculo.repositories import comunicados as repo
from oraculo.services.notificacao_service import Notificacao, Severidade

log = get_logger(__name__)

MAX_TENTATIVAS = 3
"""Falhas de envio toleradas antes de desistir e marcar o comunicado."""

RESERVA_MAXIMA = timedelta(minutes=10)
"""Tempo após o qual uma reserva sem resposta é considerada órfã (o processo
morreu entre reservar e publicar)."""

ATRASO_MAXIMO_PADRAO = timedelta(hours=6)
"""Atraso além do qual o comunicado deixa de fazer sentido e não é publicado."""


class DataDeComunicadoInvalidaError(BusinessRuleError):
    """Programação sem fuso horário ou no passado."""

    regra = "RN-018"


class CanalNaoConfiguradoError(BusinessRuleError):
    """Nenhum canal de comunicados informado nem configurado no ambiente."""

    regra = "RN-018"


class ComunicadoEncerradoError(BusinessRuleError):
    """Operação sobre comunicado já publicado, cancelado ou falhado (RN-010)."""

    regra = "RN-010"


@runtime_checkable
class PublicadorDeComunicado(Protocol):
    """Quem sabe entregar o comunicado no canal. Devolve o id da mensagem.

    Levantar exceção é a forma de sinalizar falha: o serviço trata a tentativa,
    registra o erro e decide entre tentar de novo e desistir.
    """

    async def publicar(self, comunicado: Comunicado) -> int: ...


@dataclass(slots=True)
class ResultadoCiclo:
    """O que um ciclo do publicador fez — usado em log e em teste."""

    publicados: list[int] = field(default_factory=list)
    expirados: list[int] = field(default_factory=list)
    falhados: list[int] = field(default_factory=list)
    reagendados: list[int] = field(default_factory=list)
    orfaos: list[int] = field(default_factory=list)

    @property
    def houve_trabalho(self) -> bool:
        return bool(
            self.publicados or self.expirados or self.falhados or self.reagendados or self.orfaos
        )


class ComunicadoService:
    def __init__(
        self,
        *,
        publicador: PublicadorDeComunicado | None = None,
        atraso_maximo: timedelta = ATRASO_MAXIMO_PADRAO,
    ) -> None:
        self._publicador = publicador
        self._atraso_maximo = atraso_maximo

    @property
    def habilitado(self) -> bool:
        """Sem publicador não há para onde publicar (ex.: processo só de API)."""
        return self._publicador is not None

    def registrar_publicador(self, publicador: PublicadorDeComunicado) -> None:
        """O publicador depende do cliente Discord, que nasce depois do container."""
        self._publicador = publicador

    # -- Criação -----------------------------------------------------------

    async def programar(
        self,
        session: AsyncSession,
        *,
        titulo: str,
        corpo: str,
        canal_id: int | None,
        autor: Membro,
        publicar_em: datetime,
        mencao: TipoMencao = TipoMencao.NENHUMA,
        guild_id: int | None = None,
        canal_padrao: int | None = None,
        origem: OrigemAcao = OrigemAcao.DISCORD,
    ) -> Comunicado:
        """Registra um comunicado para publicação futura (RN-018)."""
        perfil = autor.perfil
        exigir(perfil, Acao.PUBLICAR_COMUNICADO)
        if mencao is not TipoMencao.NENHUMA:
            exigir(perfil, Acao.MENCIONAR_TODOS)

        destino = canal_id or canal_padrao
        if destino is None:
            raise CanalNaoConfiguradoError(
                "Nenhum canal de comunicados definido. Informe o canal no comando ou "
                "configure ORACULO_DISCORD_COMUNICADOS_CHANNEL_ID no ambiente."
            )
        self._validar_data(publicar_em)

        comunicado = await repo.criar(
            session,
            titulo=titulo,
            corpo=corpo,
            canal_id=destino,
            autor=autor,
            publicar_em=publicar_em,
            mencao=mencao,
            guild_id=guild_id,
        )
        await auditoria.registrar(
            session,
            acao="comunicado.programado",
            resumo=(
                f"{autor.nome_exibicao} programou '{comunicado.titulo}' para "
                f"{publicar_em.isoformat()}"
            ),
            ator=autor,
            alvo_tipo="comunicado",
            alvo_id=comunicado.id,
            dados={
                "canal_id": str(destino),
                "publicar_em": publicar_em.isoformat(),
                "mencao": TipoMencao(mencao).value,
            },
            origem=origem,
            guild_id=guild_id,
        )
        return comunicado

    async def publicar_agora(
        self,
        session: AsyncSession,
        *,
        titulo: str,
        corpo: str,
        canal_id: int | None,
        autor: Membro,
        mencao: TipoMencao = TipoMencao.NENHUMA,
        guild_id: int | None = None,
        canal_padrao: int | None = None,
        origem: OrigemAcao = OrigemAcao.DISCORD,
    ) -> Comunicado:
        """Publica imediatamente, pelo mesmo caminho do agendado.

        Registro e envio ficam na mesma transação, de propósito: se algo falhar
        antes do commit, não sobra comunicado fantasma no banco. O risco
        espelhado — mensagem entregue e transação perdida — deixa um aviso no
        canal sem linha correspondente, e é o lado certo do trade-off: o
        contrário publicaria de novo no ciclo seguinte.

        A hora de publicação fica um instante à frente justamente para não
        criar um segundo caminho de publicação: o registro, a auditoria e as
        regras de menção são exatamente os mesmos do comunicado programado.
        """
        comunicado = await self.programar(
            session,
            titulo=titulo,
            corpo=corpo,
            canal_id=canal_id,
            autor=autor,
            publicar_em=agora() + timedelta(seconds=1),
            mencao=mencao,
            guild_id=guild_id,
            canal_padrao=canal_padrao,
            origem=origem,
        )
        comunicado.status = StatusComunicado.PUBLICANDO
        comunicado.reservado_em = agora()
        await session.flush()
        await self._entregar(session, comunicado, ResultadoCiclo())
        return comunicado

    # -- Cancelamento ------------------------------------------------------

    async def cancelar(
        self,
        session: AsyncSession,
        *,
        comunicado: Comunicado,
        solicitante: Membro,
        motivo: str,
        origem: OrigemAcao = OrigemAcao.DISCORD,
    ) -> Comunicado:
        """RN-010 — cancelamento lógico de um comunicado ainda não publicado."""
        if comunicado.autor_id != solicitante.id:
            exigir(solicitante.perfil, Acao.GERIR_COMUNICADO)

        if comunicado.status is not StatusComunicado.AGENDADO:
            raise ComunicadoEncerradoError(
                f"Comunicado já está como '{StatusComunicado(comunicado.status).value}'. "
                "Só dá para cancelar o que ainda não saiu."
            )

        comunicado.status = StatusComunicado.CANCELADO
        comunicado.cancelado_em = agora()
        comunicado.cancelado_por_id = solicitante.id
        comunicado.motivo_cancelamento = (motivo or "").strip()[:500] or "Sem motivo informado"

        await auditoria.registrar(
            session,
            acao="comunicado.cancelado",
            resumo=(
                f"{solicitante.nome_exibicao} cancelou '{comunicado.titulo}': "
                f"{comunicado.motivo_cancelamento}"
            ),
            ator=solicitante,
            alvo_tipo="comunicado",
            alvo_id=comunicado.id,
            dados={"motivo": comunicado.motivo_cancelamento},
            origem=origem,
            guild_id=comunicado.guild_id,
        )
        return comunicado

    # -- Publicação periódica ---------------------------------------------

    async def publicar_pendentes(
        self,
        session: AsyncSession,
        *,
        momento: datetime | None = None,
        limite: int = 5,
    ) -> ResultadoCiclo:
        """Um ciclo do publicador: encerra órfãos, reserva vencidos e entrega.

        **Dá commit no meio.** É proposital e é o ponto central do desenho: a
        reserva precisa estar gravada antes de o Discord ser chamado, e cada
        entrega precisa ser gravada antes da próxima, para que uma falha no
        terceiro comunicado não desfaça o registro dos dois já publicados —
        esses já estão no canal e não têm como ser "desfeitos" por rollback.
        """
        resultado = ResultadoCiclo()
        if self._publicador is None:
            return resultado

        instante = momento or agora()
        await self._encerrar_orfaos(session, instante, resultado)

        reservados = await repo.reservar_vencidos(session, momento=instante, limite=limite)
        await session.commit()  # a reserva precisa sobreviver a uma queda agora
        if not reservados:
            return resultado

        limite_atraso = instante - self._atraso_maximo
        for comunicado in reservados:
            if como_utc(comunicado.publicar_em) < limite_atraso:
                await self._expirar(session, comunicado, resultado)
            else:
                await self._entregar(session, comunicado, resultado)
            await session.commit()
        return resultado

    # -- Interno -----------------------------------------------------------

    async def _entregar(
        self, session: AsyncSession, comunicado: Comunicado, resultado: ResultadoCiclo
    ) -> None:
        assert self._publicador is not None  # noqa: S101 — garantido pelos chamadores
        try:
            mensagem_id = await self._publicador.publicar(comunicado)
        except Exception as exc:  # noqa: BLE001 — falha de rede não derruba o ciclo
            await self._registrar_falha(session, comunicado, exc, resultado)
            return

        comunicado.status = StatusComunicado.PUBLICADO
        comunicado.publicado_em = agora()
        comunicado.mensagem_id = mensagem_id
        comunicado.erro = None
        resultado.publicados.append(comunicado.id)

        await auditoria.registrar(
            session,
            acao="comunicado.publicado",
            resumo=f"Comunicado '{comunicado.titulo}' publicado no canal {comunicado.canal_id}",
            alvo_tipo="comunicado",
            alvo_id=comunicado.id,
            dados={
                "canal_id": str(comunicado.canal_id),
                "mensagem_id": str(mensagem_id),
                "mencao": TipoMencao(comunicado.mencao).value,
            },
            origem=OrigemAcao.SISTEMA,
            guild_id=comunicado.guild_id,
        )

    async def _registrar_falha(
        self,
        session: AsyncSession,
        comunicado: Comunicado,
        exc: Exception,
        resultado: ResultadoCiclo,
    ) -> None:
        comunicado.tentativas += 1
        comunicado.erro = f"{type(exc).__name__}: {exc}"[:2000]
        comunicado.reservado_em = None

        if comunicado.tentativas >= MAX_TENTATIVAS:
            comunicado.status = StatusComunicado.FALHOU
            resultado.falhados.append(comunicado.id)
            log.error(
                "Comunicado %s desistiu após %d tentativas: %s",
                comunicado.id,
                comunicado.tentativas,
                comunicado.erro,
            )
            await auditoria.registrar(
                session,
                acao="comunicado.falhou",
                resumo=f"Comunicado '{comunicado.titulo}' não pôde ser publicado",
                alvo_tipo="comunicado",
                alvo_id=comunicado.id,
                dados={"tentativas": comunicado.tentativas, "erro": comunicado.erro},
                origem=OrigemAcao.SISTEMA,
                guild_id=comunicado.guild_id,
            )
            return

        # Volta para a fila: o próximo ciclo tenta de novo.
        comunicado.status = StatusComunicado.AGENDADO
        resultado.reagendados.append(comunicado.id)
        log.warning(
            "Falha ao publicar comunicado %s (tentativa %d): %s",
            comunicado.id,
            comunicado.tentativas,
            comunicado.erro,
        )

    async def _expirar(
        self, session: AsyncSession, comunicado: Comunicado, resultado: ResultadoCiclo
    ) -> None:
        comunicado.status = StatusComunicado.FALHOU
        comunicado.reservado_em = None
        marcada = como_utc(comunicado.publicar_em).isoformat()
        comunicado.erro = (
            f"Não publicado: a hora marcada ({marcada}) passou há mais que o atraso "
            f"tolerado ({self._atraso_maximo}). Reprograme se ainda fizer sentido."
        )
        resultado.expirados.append(comunicado.id)

        await auditoria.registrar(
            session,
            acao="comunicado.expirado",
            resumo=f"Comunicado '{comunicado.titulo}' expirou sem ser publicado",
            alvo_tipo="comunicado",
            alvo_id=comunicado.id,
            dados={"publicar_em": comunicado.publicar_em.isoformat()},
            origem=OrigemAcao.SISTEMA,
            guild_id=comunicado.guild_id,
        )

    async def _encerrar_orfaos(
        self, session: AsyncSession, instante: datetime, resultado: ResultadoCiclo
    ) -> None:
        """Reservas que nunca voltaram — o processo caiu entre reservar e publicar.

        Encerradas como falha, **sem republicar**: não há como saber se a
        mensagem chegou ao canal antes da queda, e um `@everyone` repetido é
        pior que um comunicado que alguém precisa reenviar à mão.
        """
        esquecidas = await repo.listar_reservas_esquecidas(
            session, limite_em=instante - RESERVA_MAXIMA
        )
        for comunicado in esquecidas:
            comunicado.status = StatusComunicado.FALHOU
            comunicado.erro = (
                "Reserva sem resposta: o bot foi reiniciado durante a publicação. "
                "Confira o canal antes de reprogramar — a mensagem pode ter saído."
            )
            resultado.orfaos.append(comunicado.id)
            await auditoria.registrar(
                session,
                acao="comunicado.reserva_orfa",
                resumo=f"Comunicado '{comunicado.titulo}' ficou preso em publicação",
                alvo_tipo="comunicado",
                alvo_id=comunicado.id,
                origem=OrigemAcao.SISTEMA,
                guild_id=comunicado.guild_id,
            )
        if esquecidas:
            await session.commit()

    @staticmethod
    def _validar_data(publicar_em: datetime) -> None:
        if publicar_em.tzinfo is None:
            raise DataDeComunicadoInvalidaError(
                "Informe a data/hora com fuso horário (timezone-aware)."
            )
        if publicar_em <= agora():
            raise DataDeComunicadoInvalidaError("A publicação deve estar no futuro.")

    @staticmethod
    def aviso_de_falha(comunicado: Comunicado) -> Notificacao:
        """Notificação para o canal de logs quando um comunicado não sai (RF-012)."""
        return Notificacao(
            titulo="Comunicado não publicado",
            corpo=comunicado.erro or "Falha sem detalhe registrado.",
            severidade=Severidade.ALERTA,
            campos={"Título": comunicado.titulo, "ID": f"#{comunicado.id}"},
            guild_id=comunicado.guild_id,
        )
