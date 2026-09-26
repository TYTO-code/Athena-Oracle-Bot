"""Importação de membros da plataforma — RF-001 / RN-010 / RNF-004.

Princípios:

* **Idempotente.** Rodar duas vezes seguidas não muda nada na segunda; a
  correspondência usa `id_externo` e, na falta dele, `discord_id`.
* **Não destrutiva.** Membro que sumiu da plataforma nunca é apagado; no
  máximo é desativado (soft-delete), e só se explicitamente pedido (RN-010).
* **Auditável.** Cada execução grava um registro com o resumo, e cada mudança
  de patente passa pelo `PromocaoService` — ou seja, entra no histórico normal.
* **Ensaiável.** `dry_run=True` percorre tudo e relata sem gravar nada.

A política de XP e patente é explícita em `PoliticaImportacao`: por padrão a
plataforma manda no **cadastro** (nome, e-mail, vínculo) e o bot continua dono
do **XP e da patente**, que é a leitura conservadora das RN-002/RN-003.

Cargos institucionais (Conselheiro, Administrador) **nunca** vêm da
importação: são concedidos no bot por um Administrador (TD-007).

XP e patente são irrevogáveis (`Institucional/XP.md` Art. 1º): nenhuma
política faz a importação diminuir XP ou rebaixar patente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora
from oraculo.db.models import Membro, OrigemAcao
from oraculo.domain.hierarchy import (
    OFICIAL,
    PATENTE_INICIAL,
    Patente,
    patente_para_xp,
    patente_por_slug,
)
from oraculo.integrations.plataforma import FonteMembros, MembroExterno, normalizar
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria
from oraculo.services.promocao_service import PromocaoService

log = get_logger(__name__)

PATENTE_MAXIMA_AUTOMATICA: Patente = OFICIAL
"""Teto de mitigação: a importação nunca aplica, sozinha, patente acima desta.

A plataforma (Firebase) não está sob o controle de permissões deste bot
(RN-008) — as regras de segurança do Firestore que decidem quem pode gravar
`tier` ou `xp` ficam fora deste repositório. Oficial é a patente mais alta que
libera privilégio no bot (eventos e comunicados); acima dela, a importação só
registra a sugestão em auditoria (`importacao.patente_pendente_confirmacao`) e
espera um Administrador rodar `/confirmar-patente`, que aplica a patente que o
XP determina — nunca uma escolhida à mão."""


class PoliticaImportacao(StrEnum):
    """Quem é dono de XP e patente quando os dois lados divergem."""

    CADASTRO = "cadastro"
    """Importa apenas identidade (nome, e-mail, vínculo). Padrão."""

    CARGA_INICIAL = "carga_inicial"
    """Traz XP e patente **apenas** para membros novos; existentes não mudam."""

    ESPELHO = "espelho"
    """O XP é um espelho da plataforma e a patente decorre dele (RN-002).

    Nesta política o bot **não** é dono do XP: a cada importação o saldo sobe
    para o da plataforma. Por isso os comandos de escrita de XP ficam
    bloqueados (ver `Settings.xp_somente_leitura`) — sem isso, um
    `/conceder-xp` seria silenciosamente desfeito na sincronização seguinte.

    Um XP **menor** na plataforma não é espelhado: XP é irrevogável (XP.md
    Art. 1º §1º); a divergência vai para a auditoria. A patente vem do campo
    `patente` quando a plataforma o informa e é maior que a do XP; caso
    contrário, do XP. Nada disso **nunca** rebaixa ninguém.
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
            f"{self.promovidos} com patente alterada · "
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

        # Nasce sempre na patente inicial: a subida vira uma promoção registrada,
        # e não uma patente que apareceu no banco sem nenhuma explicação (RN-003).
        membro = Membro(
            id_externo=externo.id_externo,
            discord_id=externo.discord_id,
            nome_exibicao=externo.nome,
            email=externo.email,
            patente_slug=PATENTE_INICIAL.slug,
            xp=xp_inicial,
            ativo=externo.ativo,
            sincronizado_em=agora(),
        )
        session.add(membro)
        await session.flush()
        relatorio.criados += 1

        if trazer_progressao:
            await self._subir_patente(session, membro, externo, relatorio, guild_id)

    async def _sobrescrever_progressao(
        self,
        session: AsyncSession,
        membro: Membro,
        externo: MembroExterno,
        relatorio: Relatorio,
        guild_id: int | None,
    ) -> bool:
        """Espelha o XP da plataforma e sobe a patente (RN-002 / RN-003)."""
        mudou = False

        if externo.xp is not None and externo.xp > membro.xp:
            membro.xp = externo.xp
            mudou = True
        elif externo.xp is not None and externo.xp < membro.xp:
            await auditoria.registrar(
                session,
                acao="importacao.xp_menor_ignorado",
                resumo=(
                    f"{membro.nome_exibicao}: plataforma informa {externo.xp} XP, abaixo dos "
                    f"{membro.xp} XP já concedidos; XP é irrevogável (XP.md Art. 1º §1º)"
                ),
                ator_descricao="importação da plataforma",
                alvo_tipo="membro",
                alvo_id=membro.id,
                dados={"xp_bot": membro.xp, "xp_plataforma": externo.xp},
                origem=OrigemAcao.SISTEMA,
                guild_id=guild_id,
            )

        mudou |= await self._subir_patente(session, membro, externo, relatorio, guild_id)
        return mudou

    async def _subir_patente(
        self,
        session: AsyncSession,
        membro: Membro,
        externo: MembroExterno,
        relatorio: Relatorio,
        guild_id: int | None,
    ) -> bool:
        """Aplica a maior entre a patente declarada e a do XP — só se for subida."""
        declarada = self._patente_de(externo)
        pelo_xp = patente_para_xp(membro.xp)
        alvo = max(declarada, pelo_xp) if declarada else pelo_xp
        atual = patente_por_slug(membro.patente_slug)

        if alvo <= atual:
            # Patente é irrevogável: nada aqui rebaixa (XP.md Art. 1º §3º).
            return False

        origem_dado = "patente" if declarada and declarada > pelo_xp else "xp"

        if alvo > PATENTE_MAXIMA_AUTOMATICA:
            await self._registrar_pendente(
                session,
                membro,
                patente_atual=atual,
                patente_sugerida=alvo,
                origem_dado=origem_dado,
                relatorio=relatorio,
                guild_id=guild_id,
            )
            return False

        await self._promocoes.aplicar(
            session,
            membro,
            patente_nova=alvo,
            automatica=origem_dado == "xp",
            autor_descricao="importação da plataforma",
            motivo=(
                "Patente trazida da plataforma do clube"
                if origem_dado == "patente"
                else "Progressão por XP trazido da plataforma (RN-002)"
            ),
            origem=OrigemAcao.SISTEMA,
            guild_id=guild_id,
        )
        relatorio.promovidos += 1
        return True

    async def _registrar_pendente(
        self,
        session: AsyncSession,
        membro: Membro,
        *,
        patente_atual: Patente,
        patente_sugerida: Patente,
        origem_dado: str,
        relatorio: Relatorio,
        guild_id: int | None,
    ) -> None:
        """Bloqueia a importação de aplicar sozinha patente acima do teto.

        Não muda `membro.patente_slug` — só relata. A promoção real, se
        procedente, é feita por um Administrador via `/confirmar-patente`,
        entrando no fluxo normal de auditoria.
        """
        relatorio.pendentes_confirmacao += 1
        log.warning(
            "Importação sugere promover %s (id=%s) de %s para %s via %s da plataforma; "
            "acima do teto automático (%s), aguardando confirmação manual.",
            membro.nome_exibicao,
            membro.id,
            patente_atual.slug,
            patente_sugerida.slug,
            origem_dado,
            PATENTE_MAXIMA_AUTOMATICA.slug,
        )
        await auditoria.registrar(
            session,
            acao="importacao.patente_pendente_confirmacao",
            resumo=(
                f"{membro.nome_exibicao}: sugestão {patente_atual.nome} → "
                f"{patente_sugerida.nome} via {origem_dado} da plataforma; acima de "
                f"{PATENTE_MAXIMA_AUTOMATICA.nome}, requer /confirmar-patente"
            ),
            ator_descricao="importação da plataforma",
            alvo_tipo="membro",
            alvo_id=membro.id,
            dados={
                "patente_atual": patente_atual.slug,
                "patente_sugerida": patente_sugerida.slug,
                "origem_dado": origem_dado,
            },
            origem=OrigemAcao.SISTEMA,
            guild_id=guild_id,
        )

    def _patente_de(self, externo: MembroExterno) -> Patente | None:
        """Patente declarada pela plataforma, ou `None` para deixar o XP decidir.

        Valor ausente ou desconhecido (inclusive nomes da hierarquia anterior a
        TD-007, como "cavalaria") vira `None` — nunca a patente inicial, o que
        rebaixaria o clube inteiro na próxima sincronização.
        """
        if not externo.patente:
            return None
        try:
            return patente_por_slug(externo.patente)
        except KeyError:
            log.warning(
                "Patente desconhecida %r no membro %s; patente será derivada do XP.",
                externo.patente,
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
