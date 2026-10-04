"""Espelho dos membros da TYTO.club — RF-001 / RN-010 / RN-020 / RN-021.

A plataforma é a **única fonte da verdade** e o bot só a consulta (RN-021): esta
importação lê o Firestore e copia para o banco *do bot* (um cache de leitura);
nada é escrito de volta na plataforma.

Princípios:

* **Só membros do Clube (RN-020).** Quem não é elegível — conta suspensa,
  conta de mercador, sem o ID numérico do Discord no perfil — não entra; quem
  já estava e deixou de ser elegível é desativado e perde o acesso.
* **Espelho.** Nome, e-mail, vínculo de Discord, XP, patente e cargos
  (Conselheiro/Administrador) vêm da plataforma. Nada é concedido no bot.
* **Idempotente.** Rodar duas vezes seguidas não muda nada na segunda; a
  correspondência usa `id_externo` e, na falta dele, `discord_id`.
* **Não destrutiva.** Ninguém é apagado: perder elegibilidade é soft-delete
  (RN-010), e reativa sozinho quando voltar a ser elegível.
* **Auditável.** Cada execução grava um resumo; mudanças de patente passam pelo
  `PromocaoService` e mudanças de cargo geram auditoria própria.
* **Ensaiável.** `dry_run=True` percorre tudo e relata sem gravar nada.

XP e patente são irrevogáveis (`Institucional/XP.md` Art. 1º): um XP menor na
plataforma não rebaixa ninguém no bot — a divergência vai para a auditoria.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora
from oraculo.db.models import Membro, OrigemAcao
from oraculo.domain.hierarchy import (
    PATENTE_INICIAL,
    Patente,
    patente_para_xp,
    patente_por_slug,
)
from oraculo.integrations.plataforma import FonteMembros, MembroExterno, normalizar
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria
from oraculo.repositories import xp as repo_xp
from oraculo.services.promocao_service import PromocaoService

log = get_logger(__name__)

@dataclass(slots=True)
class Relatorio:
    """Resultado de uma execução, pronto para log, CLI ou embed."""

    criados: int = 0
    atualizados: int = 0
    inalterados: int = 0
    reativados: int = 0
    desativados: int = 0
    promovidos: int = 0
    nao_elegiveis: int = 0
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
            + self.nao_elegiveis
            + self.invalidos
            + len(self.erros)
        )

    def resumo(self) -> str:
        prefixo = "[ENSAIO] " if self.dry_run else ""
        return (
            f"{prefixo}{self.total_lidos} lidos · {self.criados} criados · "
            f"{self.atualizados} atualizados · {self.inalterados} sem mudança · "
            f"{self.promovidos} com patente alterada · "
            f"{self.nao_elegiveis} fora do Clube · {self.desativados} desativados · "
            f"{self.reativados} reativados · "
            f"{self.sem_discord} sem Discord · "
            f"{self.invalidos} inválidos · {len(self.erros)} erros"
        )


class ConflitoDeDiscordIdError(Exception):
    """O `discordId` já pertence a outro membro — ninguém herda a conta de outrem."""


LIMITE_DESATIVACAO_EM_MASSA = 0.5
"""Fração de ativos que uma única leitura pode desativar por "ausência". Acima
disso (e de 5 pessoas) a leitura é tratada como suspeita — coleção errada ou
leitura parcial — e nada é desativado."""


class ImportacaoService:
    def __init__(
        self,
        fonte: FonteMembros,
        *,
        mapa_campos: dict[str, str] | None = None,
        promocoes: PromocaoService | None = None,
    ) -> None:
        self._fonte = fonte
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
                # Savepoint por registro: uma violação de unicidade desfaz só ele,
                # sem deixar a sessão inteira em `PendingRollback`. No ensaio não se
                # usa: o driver do SQLite confirma a transação ao liberar o savepoint,
                # e o ensaio precisa poder ser revertido por inteiro.
                async with contextlib.AsyncExitStack() as pilha:
                    if not dry_run:
                        await pilha.enter_async_context(session.begin_nested())
                    await self._aplicar(session, externo, relatorio, dry_run, guild_id)
            except Exception as exc:  # noqa: BLE001 — um registro ruim não aborta a carga
                log.exception("Falha ao importar membro %s", externo.id_externo)
                relatorio.erros.append(f"{externo.id_externo}: {type(exc).__name__}: {exc}")

        # Uma leitura que não trouxe ninguém é falha da fonte, não "o Clube
        # esvaziou": desativar todo mundo por isso trancaria o bot inteiro.
        if desativar_ausentes and vistos:
            await self._desativar_ausentes(session, vistos, relatorio, dry_run)
        elif desativar_ausentes:
            relatorio.erros.append("leitura vazia: nenhuma desativação por ausência aplicada")

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
                    "nao_elegiveis": relatorio.nao_elegiveis,
                    "desativados": relatorio.desativados,
                    "erros": len(relatorio.erros),
                },
                origem=OrigemAcao.SISTEMA,
                guild_id=guild_id,
            )

        log.info("Importação concluída: %s", relatorio.resumo())
        return relatorio

    async def importar_um(
        self,
        session: AsyncSession,
        externo: MembroExterno,
        *,
        guild_id: int | None = None,
    ) -> Membro | None:
        """Espelha **um** membro já lido (consulta ao vivo do acesso, RN-020).

        Devolve o membro ativo no bot, ou `None` se ele não é elegível.
        """
        relatorio = Relatorio()
        try:
            await self._aplicar(session, externo, relatorio, False, guild_id)
            await session.flush()
        except ConflitoDeDiscordIdError:
            log.warning(
                "Acesso recusado: discordId %s já pertence a outro membro.", externo.discord_id
            )
            return None
        membro = await self._encontrar(session, externo)
        return membro if membro is not None and membro.ativo else None

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

        if not externo.elegivel:
            # RN-020 — fora do Clube: não entra; quem já estava perde o acesso.
            if membro is not None and membro.ativo:
                membro.ativo, membro.desativado_em = False, agora()
                membro.sincronizado_em = agora()
                relatorio.desativados += 1
                await self._auditar_acesso(
                    session, membro, "importacao.membro_desativado",
                    "deixou de ser elegível na plataforma (suspenso, sem Discord ou fora do Clube)",
                    guild_id,
                )
                if not dry_run:
                    await session.flush()
            else:
                relatorio.nao_elegiveis += 1
            return

        await self._garantir_discord_livre(session, externo, membro)

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
        if not membro.ativo:
            membro.ativo, membro.desativado_em = True, None
            relatorio.reativados += 1
            mudou = True
            await self._auditar_acesso(
                session, membro, "importacao.membro_reativado",
                "voltou a ser elegível na plataforma", guild_id,
            )

        mudou |= await self._espelhar_cargos(session, membro, externo, guild_id)
        mudou |= await self._espelhar_progressao(session, membro, externo, relatorio, guild_id)

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
        # Nasce na patente inicial: a subida vira uma promoção registrada, e não
        # uma patente que apareceu no banco sem nenhuma explicação (RN-003).
        membro = Membro(
            id_externo=externo.id_externo,
            discord_id=externo.discord_id,
            nome_exibicao=externo.nome,
            email=externo.email,
            patente_slug=PATENTE_INICIAL.slug,
            xp=max(0, externo.xp or 0),
            conselheiro=externo.conselheiro,
            administrador=externo.administrador,
            ativo=True,
            sincronizado_em=agora(),
        )
        session.add(membro)
        await session.flush()
        relatorio.criados += 1

        await self._subir_patente(session, membro, externo, relatorio, guild_id)

    @staticmethod
    async def _garantir_discord_livre(
        session: AsyncSession, externo: MembroExterno, membro: Membro | None
    ) -> None:
        """Recusa o espelho se o `discordId` já está com outra conta (RN-020)."""
        dono = await session.scalar(
            select(Membro).where(Membro.discord_id == externo.discord_id)
        )
        if dono is not None and (membro is None or dono.id != membro.id):
            raise ConflitoDeDiscordIdError(
                f"discordId {externo.discord_id} de {externo.id_externo} já pertence a "
                f"{dono.id_externo or dono.id}"
            )

    @staticmethod
    async def _auditar_acesso(
        session: AsyncSession, membro: Membro, acao: str, motivo: str, guild_id: int | None
    ) -> None:
        await auditoria.registrar(
            session,
            acao=acao,
            resumo=f"{membro.nome_exibicao}: {motivo}",
            ator_descricao="importação da plataforma",
            alvo_tipo="membro",
            alvo_id=membro.id,
            dados={"id_externo": membro.id_externo},
            origem=OrigemAcao.SISTEMA,
            guild_id=guild_id,
        )

    @staticmethod
    async def _espelhar_cargos(
        session: AsyncSession, membro: Membro, externo: MembroExterno, guild_id: int | None
    ) -> bool:
        """Copia Conselheiro/Administrador da plataforma (o bot não os concede)."""
        if (membro.conselheiro, membro.administrador) == (
            externo.conselheiro,
            externo.administrador,
        ):
            return False

        await auditoria.registrar(
            session,
            acao="importacao.cargo_espelhado",
            resumo=(
                f"{membro.nome_exibicao}: Conselheiro {membro.conselheiro}→{externo.conselheiro}, "
                f"Administrador {membro.administrador}→{externo.administrador} (plataforma)"
            ),
            ator_descricao="importação da plataforma",
            alvo_tipo="membro",
            alvo_id=membro.id,
            dados={
                "conselheiro": externo.conselheiro,
                "administrador": externo.administrador,
            },
            origem=OrigemAcao.SISTEMA,
            guild_id=guild_id,
        )
        membro.conselheiro = externo.conselheiro
        membro.administrador = externo.administrador
        return True

    async def _espelhar_progressao(
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
            # A subida entra na trilha `xp_audit` como espelho da plataforma:
            # é ela que alimenta o ranking por período (RF-004).
            await repo_xp.registrar(
                session,
                membro=membro,
                autor=None,
                autor_descricao="importação da plataforma",
                quantidade=externo.xp - membro.xp,
                saldo_anterior=membro.xp,
                saldo_posterior=externo.xp,
                motivo="XP espelhado da plataforma (TYTO.club)",
                origem=OrigemAcao.SISTEMA,
                guild_id=guild_id,
            )
            membro.xp = externo.xp
            mudou = True
        elif externo.xp is not None and externo.xp < membro.xp:
            await auditoria.registrar(
                session,
                acao="importacao.xp_menor_ignorado",
                resumo=(
                    f"{membro.nome_exibicao}: plataforma informa {externo.xp} XP, abaixo dos "
                    f"{membro.xp} XP já espelhados; XP é irrevogável (XP.md Art. 1º §1º)"
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
        # Só adota um registro que ainda **não** pertence a outra conta da
        # plataforma: quem preenche o `discordId` de outra pessoa não herda o
        # XP, a patente nem os cargos dela.
        return await session.scalar(
            select(Membro).where(
                Membro.discord_id == externo.discord_id, Membro.id_externo.is_(None)
            )
        )

    @staticmethod
    async def _desativar_ausentes(
        session: AsyncSession, vistos: set[str], relatorio: Relatorio, dry_run: bool
    ) -> None:
        """RN-010 — quem saiu da plataforma é desativado, nunca apagado."""
        candidatos = await session.scalars(
            select(Membro).where(Membro.id_externo.is_not(None), Membro.ativo.is_(True))
        )
        ativos = list(candidatos)
        ausentes = [m for m in ativos if m.id_externo not in vistos]
        if len(ausentes) > 5 and len(ausentes) > len(ativos) * LIMITE_DESATIVACAO_EM_MASSA:
            relatorio.erros.append(
                f"{len(ausentes)} de {len(ativos)} membros ausentes na leitura: suspeito "
                "(coleção errada ou leitura parcial); nenhuma desativação aplicada"
            )
            return
        for membro in ausentes:
            membro.ativo = False
            membro.desativado_em = agora()
            relatorio.desativados += 1
            await ImportacaoService._auditar_acesso(
                session, membro, "importacao.membro_desativado",
                "ausente da plataforma", None,
            )
        if not dry_run:
            await session.flush()
