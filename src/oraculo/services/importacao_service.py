"""Importação de membros da plataforma — RF-001 / RN-010 / RNF-004.

Princípios:

* **Idempotente.** Rodar duas vezes seguidas não muda nada na segunda; a
  correspondência usa `id_externo` e, na falta dele, `discord_id`.
* **Não destrutiva.** Membro que sumiu da plataforma nunca é apagado; no
  máximo é desativado (soft-delete), e só se explicitamente pedido (RN-010).
* **Auditável.** Cada execução grava um registro com o resumo, e cada mudança
  de cargo passa pelo `PromocaoService` — ou seja, entra no histórico normal.
* **Ensaiável.** `dry_run=True` percorre tudo e relata sem gravar nada.

A política de XP e cargo é explícita em `PoliticaImportacao`: por padrão a
plataforma manda no **cadastro** (nome, e-mail, vínculo) e o bot continua dono
do **XP e do cargo**, que é a leitura conservadora das RN-002/RN-003.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora
from oraculo.db.models import Membro, OrigemAcao
from oraculo.domain.hierarchy import CARGO_INICIAL, LORDE, Cargo, cargo_para_xp, cargo_por_slug
from oraculo.integrations.plataforma import FonteMembros, MembroExterno, normalizar
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria
from oraculo.services.promocao_service import PromocaoService

log = get_logger(__name__)

CARGO_MAXIMO_AUTOMATICO: Cargo = LORDE
"""Teto de mitigação: a importação nunca aplica, sozinha, cargo acima deste.

A plataforma (Firebase) não está sob o controle de permissões deste bot
(RN-008) — as regras de segurança do Firestore que decidem quem pode gravar
`cargo` ou `xp` em `membros` ficam fora deste repositório. Se essas regras
permitirem que o próprio usuário edite o documento, a importação aplicaria
uma promoção até Administrador sem que ninguém tivesse passado por
`/definir-cargo`, contornando RNF-003. Acima do teto, a importação apenas
registra a sugestão em auditoria (`importacao.cargo_pendente_confirmacao`) e
espera confirmação manual de um humano com permissão."""


class PoliticaImportacao(StrEnum):
    """Quem é dono de XP e cargo quando os dois lados divergem."""

    CADASTRO = "cadastro"
    """Importa apenas identidade (nome, e-mail, vínculo). Padrão."""

    CARGA_INICIAL = "carga_inicial"
    """Traz XP e cargo **apenas** para membros novos; existentes não mudam."""

    ESPELHO = "espelho"
    """O XP é um espelho da plataforma e o cargo decorre dele (RN-002).

    Nesta política o bot **não** é dono do XP: a cada importação o saldo é
    substituído pelo da plataforma. Por isso os comandos de escrita de XP ficam
    bloqueados (ver `Settings.xp_somente_leitura`) — sem isso, um
    `/conceder-xp` seria silenciosamente desfeito na sincronização seguinte.

    O cargo vem do campo `cargo` quando a plataforma o informa; caso contrário
    é recalculado a partir do XP. Campo ausente **nunca** rebaixa ninguém.
    """


@dataclass(slots=True)
class Relatorio:
    """Resultado de uma execução, pronto para log, CLI ou embed."""

    criados: int = 0
    atualizados: int = 0
    inalterados: int = 0
    reativados: int = 0
    desativados: int = 0
    promovidos: int = 0
    pendentes_confirmacao: int = 0
    sem_discord: int = 0
    invalidos: int = 0
    erros: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def total_lidos(self) -> int:
        return (
            self.criados
            + self.atualizados
            + self.inalterados
            + self.invalidos
            + len(self.erros)
        )

    def resumo(self) -> str:
        prefixo = "[ENSAIO] " if self.dry_run else ""
        return (
            f"{prefixo}{self.total_lidos} lidos · {self.criados} criados · "
            f"{self.atualizados} atualizados · {self.inalterados} sem mudança · "
            f"{self.promovidos} com cargo alterado · "
            f"{self.pendentes_confirmacao} aguardando confirmação manual · "
            f"{self.sem_discord} sem Discord · "
            f"{self.invalidos} inválidos · {len(self.erros)} erros"
        )


class ImportacaoService:
    def __init__(
        self,
        fonte: FonteMembros,
        *,
        politica: PoliticaImportacao = PoliticaImportacao.CADASTRO,
        mapa_campos: dict[str, str] | None = None,
        promocoes: PromocaoService | None = None,
    ) -> None:
        self._fonte = fonte
        self._politica = politica
        self._mapa = mapa_campos or {}
        self._promocoes = promocoes or PromocaoService()

    async def importar(
        self,
        session: AsyncSession,
        *,
        dry_run: bool = False,
        desativar_ausentes: bool = False,
        guild_id: int | None = None,
    ) -> Relatorio:
        relatorio = Relatorio(dry_run=dry_run)
        vistos: set[str] = set()

        async for documento in self._fonte.listar():
            externo = normalizar(documento, mapa=self._mapa)
            if externo is None:
                relatorio.invalidos += 1
                continue

            vistos.add(externo.id_externo)
            if not externo.identificavel_no_discord:
                relatorio.sem_discord += 1

            try:
                await self._aplicar(session, externo, relatorio, dry_run, guild_id)
            except Exception as exc:  # noqa: BLE001 — um registro ruim não aborta a carga
                log.exception("Falha ao importar membro %s", externo.id_externo)
                relatorio.erros.append(f"{externo.id_externo}: {type(exc).__name__}: {exc}")

        if desativar_ausentes:
            await self._desativar_ausentes(session, vistos, relatorio, dry_run)

        if dry_run:
            # Nada do que foi feito acima deve sobreviver ao ensaio.
            await session.rollback()
        else:
            await auditoria.registrar(
                session,
                acao="importacao.executada",
                resumo=relatorio.resumo(),
                alvo_tipo="plataforma",
                alvo_id="membros",
                dados={
                    "criados": relatorio.criados,
                    "atualizados": relatorio.atualizados,
                    "promovidos": relatorio.promovidos,
                    "pendentes_confirmacao": relatorio.pendentes_confirmacao,
                    "desativados": relatorio.desativados,
                    "politica": self._politica.value,
                    "erros": len(relatorio.erros),
                },
                origem=OrigemAcao.SISTEMA,
                guild_id=guild_id,
            )

        log.info("Importação concluída: %s", relatorio.resumo())
        return relatorio

    # -- Interno -----------------------------------------------------------

    async def _aplicar(
        self,
        session: AsyncSession,
        externo: MembroExterno,
        relatorio: Relatorio,
        dry_run: bool,
        guild_id: int | None,
    ) -> None:
        membro = await self._encontrar(session, externo)

        if membro is None:
            await self._criar(session, externo, relatorio, guild_id)
            return

        mudou = False

        if membro.id_externo != externo.id_externo:
            membro.id_externo = externo.id_externo
            mudou = True
        if externo.nome and membro.nome_exibicao != externo.nome:
            membro.nome_exibicao = externo.nome
            mudou = True
        if externo.email and membro.email != externo.email:
            membro.email = externo.email
            mudou = True
        if externo.discord_id and membro.discord_id != externo.discord_id:
            membro.discord_id = externo.discord_id
            mudou = True
        if externo.ativo and not membro.ativo:
            membro.ativo, membro.desativado_em = True, None
            relatorio.reativados += 1
            mudou = True

        if self._politica is PoliticaImportacao.ESPELHO:
            mudou |= await self._sobrescrever_progressao(
                session, membro, externo, relatorio, guild_id
            )

        membro.sincronizado_em = agora()
        if mudou:
            relatorio.atualizados += 1
        else:
            relatorio.inalterados += 1

        if not dry_run:
            await session.flush()

    async def _criar(
        self,
        session: AsyncSession,
        externo: MembroExterno,
        relatorio: Relatorio,
        guild_id: int | None,
    ) -> None:
        trazer_progressao = self._politica in (
            PoliticaImportacao.CARGA_INICIAL,
            PoliticaImportacao.ESPELHO,
        )
        xp_inicial = max(0, externo.xp or 0) if trazer_progressao else 0

        # Nasce sempre no cargo inicial: a subida vira uma promoção registrada,
        # e não um cargo que apareceu no banco sem nenhuma explicação (RN-003).
        membro = Membro(
            id_externo=externo.id_externo,
            discord_id=externo.discord_id,
            nome_exibicao=externo.nome,
            email=externo.email,
            cargo_slug=CARGO_INICIAL.slug,
            xp=xp_inicial,
            ativo=externo.ativo,
            sincronizado_em=agora(),
        )
        session.add(membro)
        await session.flush()
        relatorio.criados += 1

        if not trazer_progressao:
            return

        cargo_declarado = self._cargo_de(externo)
        automatica = cargo_declarado is None
        cargo_alvo = cargo_declarado or cargo_para_xp(xp_inicial)

        if cargo_alvo.slug == CARGO_INICIAL.slug:
            return

        if cargo_alvo.ordem > CARGO_MAXIMO_AUTOMATICO.ordem:
            await self._registrar_pendente(
                session,
                membro,
                cargo_atual=CARGO_INICIAL,
                cargo_sugerido=cargo_alvo,
                origem_dado="cargo" if cargo_declarado else "xp",
                relatorio=relatorio,
                guild_id=guild_id,
            )
            return

        await self._promocoes.aplicar(
            session,
            membro,
            cargo_novo=cargo_alvo,
            automatica=automatica,
            autor_descricao="importação da plataforma",
            motivo=(
                "Cargo trazido da plataforma do clube"
                if not automatica
                else "Progressão por XP trazido da plataforma (RN-002)"
            ),
            origem=OrigemAcao.SISTEMA,
            guild_id=guild_id,
        )
        relatorio.promovidos += 1

    async def _sobrescrever_progressao(
        self,
        session: AsyncSession,
        membro: Membro,
        externo: MembroExterno,
        relatorio: Relatorio,
        guild_id: int | None,
    ) -> bool:
        """Espelha o XP da plataforma e acerta o cargo (RN-002 / RN-003)."""
        mudou = False

        if externo.xp is not None and externo.xp != membro.xp:
            membro.xp = max(0, externo.xp)
            mudou = True

        cargo_declarado = self._cargo_de(externo)
        automatica = cargo_declarado is None
        cargo_atual = cargo_por_slug(membro.cargo_slug)
        cargo_alvo = cargo_declarado or cargo_para_xp(membro.xp)

        if cargo_alvo.slug == cargo_atual.slug:
            return mudou

        escalada = cargo_alvo.ordem > cargo_atual.ordem

        if automatica and not escalada:
            # avaliar() nunca rebaixa (REBAIXAMENTO_AUTOMATICO=False); replicado
            # aqui porque o cálculo de cargo_alvo já foi antecipado para o teto.
            return mudou

        if escalada and cargo_alvo.ordem > CARGO_MAXIMO_AUTOMATICO.ordem:
            await self._registrar_pendente(
                session,
                membro,
                cargo_atual=cargo_atual,
                cargo_sugerido=cargo_alvo,
                origem_dado="cargo" if cargo_declarado else "xp",
                relatorio=relatorio,
                guild_id=guild_id,
            )
            return mudou

        await self._promocoes.aplicar(
            session,
            membro,
            cargo_novo=cargo_alvo,
            automatica=automatica,
            autor_descricao="importação da plataforma",
            motivo=(
                "Sincronização com a plataforma do clube"
                if not automatica
                else "Progressão por XP trazido da plataforma (RN-002)"
            ),
            origem=OrigemAcao.SISTEMA,
            guild_id=guild_id,
        )
        relatorio.promovidos += 1
        mudou = True

        return mudou

    async def _registrar_pendente(
        self,
        session: AsyncSession,
        membro: Membro,
        *,
        cargo_atual: Cargo,
        cargo_sugerido: Cargo,
        origem_dado: str,
        relatorio: Relatorio,
        guild_id: int | None,
    ) -> None:
        """Bloqueia a importação de aplicar sozinha cargo acima do teto.

        Não muda `membro.cargo_slug` — só relata. A promoção real, se
        procedente, é feita por um humano com permissão via
        `/definir-cargo`, entrando no fluxo normal de auditoria.
        """
        relatorio.pendentes_confirmacao += 1
        log.warning(
            "Importação sugere promover %s (id=%s) de %s para %s via %s da plataforma; "
            "acima do teto automático (%s), aguardando confirmação manual.",
            membro.nome_exibicao,
            membro.id,
            cargo_atual.slug,
            cargo_sugerido.slug,
            origem_dado,
            CARGO_MAXIMO_AUTOMATICO.slug,
        )
        await auditoria.registrar(
            session,
            acao="importacao.cargo_pendente_confirmacao",
            resumo=(
                f"{membro.nome_exibicao}: sugestão {cargo_atual.nome} → {cargo_sugerido.nome} "
                f"via {origem_dado} da plataforma; acima de {CARGO_MAXIMO_AUTOMATICO.nome}, "
                "requer confirmação manual"
            ),
            ator_descricao="importação da plataforma",
            alvo_tipo="membro",
            alvo_id=membro.id,
            dados={
                "cargo_atual": cargo_atual.slug,
                "cargo_sugerido": cargo_sugerido.slug,
                "origem_dado": origem_dado,
            },
            origem=OrigemAcao.SISTEMA,
            guild_id=guild_id,
        )

    def _cargo_de(self, externo: MembroExterno) -> Cargo | None:
        """Cargo declarado pela plataforma, ou `None` para deixar o XP decidir.

        Devolver `None` (em vez do cargo inicial) é o que impede um campo
        ausente ou escrito errado de **rebaixar** o clube inteiro na próxima
        sincronização.
        """
        if not externo.cargo:
            return None
        try:
            return cargo_por_slug(externo.cargo)
        except KeyError:
            log.warning(
                "Cargo desconhecido %r no membro %s; cargo será derivado do XP.",
                externo.cargo,
                externo.id_externo,
            )
            return None

    @staticmethod
    async def _encontrar(session: AsyncSession, externo: MembroExterno) -> Membro | None:
        """Casa por `id_externo` e, na falta, por `discord_id` (primeira carga)."""
        membro = await session.scalar(
            select(Membro).where(Membro.id_externo == externo.id_externo)
        )
        if membro is not None or externo.discord_id is None:
            return membro
        return await session.scalar(
            select(Membro).where(Membro.discord_id == externo.discord_id)
        )

    @staticmethod
    async def _desativar_ausentes(
        session: AsyncSession, vistos: set[str], relatorio: Relatorio, dry_run: bool
    ) -> None:
        """RN-010 — quem saiu da plataforma é desativado, nunca apagado."""
        candidatos = await session.scalars(
            select(Membro).where(Membro.id_externo.is_not(None), Membro.ativo.is_(True))
        )
        for membro in candidatos:
            if membro.id_externo in vistos:
                continue
            membro.ativo = False
            membro.desativado_em = agora()
            relatorio.desativados += 1
        if not dry_run:
            await session.flush()
