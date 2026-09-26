"""Promoção de patente e patente única — UC-003 / RN-001, RN-002, RN-003.

A patente é determinada **exclusivamente** pelo XP (`Institucional/XP.md`
Art. 1º §3º) e é irrevogável: este serviço só sobe patente, nunca desce. Não
existe definição manual de patente — o máximo que um humano faz é
**confirmar** a patente que o XP já determina, quando a importação a reteve
(`importacao_service.PATENTE_MAXIMA_AUTOMATICA`).

O legado acumulava cargos porque atribuía o novo sem remover os anteriores
(TD-005). Aqui a ordem é invariável e explícita:

1. remover **todos** os papéis de patente do membro no Discord;
2. atribuir o papel da nova patente;
3. registrar a promoção no histórico imutável;
4. notificar.

A sincronização com o Discord é injetada como porta (`SincronizadorCargos`),
o que mantém a regra testável sem gateway e permite que uma falha de rede no
Discord não desfaça a promoção já registrada no banco.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import Membro, OrigemAcao, Promocao
from oraculo.domain.hierarchy import CargoInstitucional, Patente, patente_para_xp, patente_por_slug
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria

log = get_logger(__name__)


@runtime_checkable
class SincronizadorCargos(Protocol):
    """Porta de sincronização de papéis com o Discord (RF-006)."""

    async def sincronizar(
        self, *, discord_id: int, patente: Patente, guild_id: int | None = None
    ) -> None:
        """Remove todos os papéis de patente do membro e atribui apenas `patente`."""
        ...

    async def definir_cargo_institucional(
        self,
        *,
        discord_id: int,
        cargo: CargoInstitucional,
        ativo: bool,
        guild_id: int | None = None,
    ) -> None:
        """Adiciona (`ativo=True`) ou remove o papel de um cargo institucional."""
        ...


@dataclass(slots=True)
class ResultadoPromocao:
    """Resultado da avaliação de progressão após uma mudança de XP."""

    promovido: bool
    patente_anterior: Patente
    patente_atual: Patente
    registro: Promocao | None = None
    sincronizado: bool = False
    erro_sincronizacao: str | None = None


class PromocaoService:
    """Avalia e aplica promoções de patente decorrentes do XP."""

    def __init__(self, sincronizador: SincronizadorCargos | None = None) -> None:
        self._sincronizador = sincronizador

    @property
    def sincronizador(self) -> SincronizadorCargos | None:
        return self._sincronizador

    async def avaliar(
        self,
        session: AsyncSession,
        membro: Membro,
        *,
        autor_descricao: str = "sistema",
        origem: OrigemAcao = OrigemAcao.SISTEMA,
        guild_id: int | None = None,
    ) -> ResultadoPromocao:
        """RN-002 — verifica se o XP atual eleva a patente e aplica a promoção."""
        atual = patente_por_slug(membro.patente_slug)
        alvo = patente_para_xp(membro.xp)

        # Só sobe: patente é irrevogável (XP.md Art. 1º §3º).
        if alvo <= atual:
            return ResultadoPromocao(False, atual, atual)

        return await self.aplicar(
            session,
            membro,
            patente_nova=alvo,
            automatica=True,
            autor_descricao=autor_descricao,
            motivo="Progressão automática por XP (RN-002)",
            origem=origem,
            guild_id=guild_id,
        )

    async def aplicar(
        self,
        session: AsyncSession,
        membro: Membro,
        *,
        patente_nova: Patente,
        automatica: bool,
        autor_descricao: str,
        motivo: str,
        origem: OrigemAcao = OrigemAcao.SISTEMA,
        guild_id: int | None = None,
    ) -> ResultadoPromocao:
        """RN-001 / RN-003 — troca a patente única, registra e sincroniza.

        Recusa qualquer patente que não seja superior à atual: não há caminho
        de código que rebaixe um membro.
        """
        anterior = patente_por_slug(membro.patente_slug)
        if patente_nova <= anterior:
            raise ValueError(
                f"Patente {patente_nova.nome} não é superior a {anterior.nome}; "
                "patente é irrevogável (XP.md Art. 1º §3º)."
            )

        # RN-001: uma única coluna de patente — não há como acumular (TD-005).
        membro.patente_slug = patente_nova.slug

        registro = Promocao(
            membro_id=membro.id,
            cargo_anterior=anterior.slug,
            cargo_novo=patente_nova.slug,
            xp_no_momento=membro.xp,
            automatica=automatica,
            autor_descricao=autor_descricao,
            motivo=motivo,
        )
        session.add(registro)
        await session.flush()

        sincronizado, erro = await self._sincronizar(membro, patente_nova, guild_id)
        registro.sincronizado_discord = sincronizado
        registro.erro_sincronizacao = erro

        await auditoria.registrar(
            session,
            acao="promocao.aplicada",
            resumo=(
                f"{membro.nome_exibicao}: {anterior.nome} → {patente_nova.nome} "
                f"({membro.xp} XP)"
            ),
            ator_descricao=autor_descricao,
            alvo_tipo="membro",
            alvo_id=membro.id,
            dados={
                "patente_anterior": anterior.slug,
                "patente_nova": patente_nova.slug,
                "xp": membro.xp,
                "automatica": automatica,
                "sincronizado_discord": sincronizado,
            },
            origem=origem,
            guild_id=guild_id,
        )

        log.info(
            "Patente alterada: membro=%s %s → %s (xp=%d, sync=%s)",
            membro.id,
            anterior.slug,
            patente_nova.slug,
            membro.xp,
            sincronizado,
        )
        return ResultadoPromocao(
            promovido=True,
            patente_anterior=anterior,
            patente_atual=patente_nova,
            registro=registro,
            sincronizado=sincronizado,
            erro_sincronizacao=erro,
        )

    async def confirmar(
        self,
        session: AsyncSession,
        membro: Membro,
        *,
        autor_descricao: str,
        origem: OrigemAcao = OrigemAcao.DISCORD,
        guild_id: int | None = None,
    ) -> ResultadoPromocao:
        """Aplica a patente que o XP já determina, retida pela importação.

        Um Administrador nunca escolhe a patente — só libera a que o XP
        registrado manda (XP.md Art. 1º §3º). Sem nada a liberar, não muda nada.
        """
        atual = patente_por_slug(membro.patente_slug)
        alvo = patente_para_xp(membro.xp)
        if alvo <= atual:
            return ResultadoPromocao(False, atual, atual)
        return await self.aplicar(
            session,
            membro,
            patente_nova=alvo,
            automatica=False,
            autor_descricao=autor_descricao,
            motivo="Patente retida pela importação confirmada por Administrador",
            origem=origem,
            guild_id=guild_id,
        )

    async def _sincronizar(
        self, membro: Membro, patente: Patente, guild_id: int | None
    ) -> tuple[bool, str | None]:
        """Aplica o papel no Discord; falha de integração não anula a promoção."""
        if self._sincronizador is None or membro.discord_id is None:
            return False, None if self._sincronizador is None else "membro sem discord_id"
        try:
            await self._sincronizador.sincronizar(
                discord_id=membro.discord_id, patente=patente, guild_id=guild_id
            )
        except Exception as exc:  # noqa: BLE001 — registrado para reprocessamento
            log.exception("Falha ao sincronizar patente no Discord (membro=%s)", membro.id)
            return False, f"{type(exc).__name__}: {exc}"[:500]
        return True, None
