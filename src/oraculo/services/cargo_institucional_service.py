"""Cargos institucionais — TD-007 / RN-008, RN-010.

Conselheiro (eleito, Carta Art. III/IV) e Administrador (função técnica do
bot) não vêm do XP e não fazem parte da escala de patentes: são flags
independentes em `Membro`, acumuláveis com qualquer patente (Carta Art. VIII).

Concessão e revogação são sempre ato de um Administrador, com motivo
obrigatório e registro no log de auditoria imutável (RN-010). A sincronização
do papel no Discord é best-effort, como na promoção de patente: falha de rede
não desfaz o que já foi gravado.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import Membro, OrigemAcao
from oraculo.domain.errors import (
    AutorNaoIdentificadoError,
    CargoInstitucionalInalteradoError,
    MotivoObrigatorioError,
    UltimoAdministradorError,
)
from oraculo.domain.hierarchy import CargoInstitucional
from oraculo.domain.permissions import Acao, exigir
from oraculo.logging_config import get_logger
from oraculo.repositories import auditoria
from oraculo.services.promocao_service import SincronizadorCargos

log = get_logger(__name__)

MOTIVO_MIN_CARACTERES = 3


@dataclass(slots=True)
class ResultadoCargoInstitucional:
    membro: Membro
    cargo: CargoInstitucional
    ativo: bool
    sincronizado: bool
    erro_sincronizacao: str | None = None


class CargoInstitucionalService:
    def __init__(self, sincronizador: SincronizadorCargos | None = None) -> None:
        self._sincronizador = sincronizador

    async def definir(
        self,
        session: AsyncSession,
        *,
        membro: Membro,
        cargo: CargoInstitucional,
        ativo: bool,
        motivo: str,
        autor: Membro | None,
        autor_descricao: str | None = None,
        origem: OrigemAcao = OrigemAcao.DISCORD,
        guild_id: int | None = None,
    ) -> ResultadoCargoInstitucional:
        """Concede (`ativo=True`) ou revoga `cargo` de `membro`.

        `autor=None` só é aceito com origem SISTEMA (bootstrap do primeiro
        Administrador pela CLI); qualquer chamada de usuário passa pela
        política central (RN-008).
        """
        motivo_limpo = (motivo or "").strip()
        if len(motivo_limpo) < MOTIVO_MIN_CARACTERES:
            raise MotivoObrigatorioError("concessão ou revogação de cargo institucional")
        if autor is not None:
            exigir(autor.perfil, Acao.DEFINIR_CARGO_INSTITUCIONAL)
        elif origem is not OrigemAcao.SISTEMA:
            raise AutorNaoIdentificadoError(Acao.DEFINIR_CARGO_INSTITUCIONAL.value)

        if membro.perfil.possui(cargo) == ativo:
            raise CargoInstitucionalInalteradoError(membro.nome_exibicao, cargo.nome, ativo)

        if cargo is CargoInstitucional.ADMINISTRADOR and not ativo:
            await self._garantir_outro_administrador(session, membro)

        if cargo is CargoInstitucional.CONSELHEIRO:
            membro.conselheiro = ativo
        else:
            membro.administrador = ativo
        await session.flush()

        sincronizado, erro = await self._sincronizar(membro, cargo, ativo, guild_id)

        await auditoria.registrar(
            session,
            acao="cargo_institucional.concedido" if ativo else "cargo_institucional.revogado",
            resumo=(
                f"{membro.nome_exibicao}: {cargo.nome} "
                f"{'concedido' if ativo else 'revogado'} — {motivo_limpo}"
            ),
            ator=autor,
            ator_descricao=autor_descricao,
            alvo_tipo="membro",
            alvo_id=membro.id,
            dados={
                "cargo": cargo.value,
                "ativo": ativo,
                "motivo": motivo_limpo,
                "sincronizado_discord": sincronizado,
            },
            origem=origem,
            guild_id=guild_id,
        )
        log.info(
            "Cargo institucional %s %s para membro=%s (sync=%s)",
            cargo.value,
            "concedido" if ativo else "revogado",
            membro.id,
            sincronizado,
        )
        return ResultadoCargoInstitucional(membro, cargo, ativo, sincronizado, erro)

    @staticmethod
    async def _garantir_outro_administrador(session: AsyncSession, membro: Membro) -> None:
        outros = await session.scalar(
            select(func.count())
            .select_from(Membro)
            .where(
                Membro.administrador.is_(True),
                Membro.ativo.is_(True),
                Membro.id != membro.id,
            )
        )
        if not outros:
            raise UltimoAdministradorError()

    async def _sincronizar(
        self, membro: Membro, cargo: CargoInstitucional, ativo: bool, guild_id: int | None
    ) -> tuple[bool, str | None]:
        if self._sincronizador is None or membro.discord_id is None:
            return False, None if self._sincronizador is None else "membro sem discord_id"
        try:
            await self._sincronizador.definir_cargo_institucional(
                discord_id=membro.discord_id, cargo=cargo, ativo=ativo, guild_id=guild_id
            )
        except Exception as exc:  # noqa: BLE001 — registrado na auditoria
            log.exception("Falha ao sincronizar cargo institucional (membro=%s)", membro.id)
            return False, f"{type(exc).__name__}: {exc}"[:500]
        return True, None
