"""Bootstrap do primeiro Administrador — RN-008.

`/cargo-institucional` exige cargo Administrador para ser usado; sem nenhum
Administrador cadastrado ainda, ninguém consegue nomear o primeiro (ciclo
fechado). Esta função quebra esse ciclo uma vez, para quem já tem acesso
direto ao servidor/banco — uma barra de confiança pelo menos tão alta quanto
ser Administrador no Discord. Uso via CLI: `python -m oraculo promover-admin`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.models import Membro, OrigemAcao
from oraculo.domain.hierarchy import CargoInstitucional
from oraculo.repositories import membros as repo_membros
from oraculo.services.cargo_institucional_service import CargoInstitucionalService


class AdministradorJaExisteError(Exception):
    """Já existe um Administrador ativo — use `/cargo-institucional` para nomear outro."""

    def __init__(self, membro: Membro) -> None:
        self.membro = membro
        super().__init__(
            f"Já existe um Administrador ativo ({membro.nome_exibicao}, "
            f"discord_id={membro.discord_id}). Use /cargo-institucional no Discord para "
            "nomear outro — este bootstrap é só para o primeiro."
        )


async def promover_primeiro_administrador(
    session: AsyncSession,
    *,
    discord_id: int,
    nome: str | None = None,
    guild_id: int | None = None,
) -> Membro:
    """Nomeia `discord_id` Administrador; recusa se já existir um ativo.

    A recusa evita que este bootstrap vire um segundo caminho de promoção
    paralelo a `/cargo-institucional` — dali em diante, o comando do Discord é a
    única via, auditada e sujeita à checagem de permissão normal.
    """
    existente = await session.scalar(
        select(Membro).where(Membro.administrador.is_(True), Membro.ativo.is_(True))
    )
    if existente is not None:
        raise AdministradorJaExisteError(existente)

    membro = await repo_membros.buscar_por_discord_id(session, discord_id)
    if membro is None:
        membro = await repo_membros.obter_ou_criar_por_discord(
            session, discord_id=discord_id, nome_exibicao=nome or str(discord_id)
        )

    await CargoInstitucionalService().definir(
        session,
        membro=membro,
        cargo=CargoInstitucional.ADMINISTRADOR,
        ativo=True,
        motivo="Nomeação do primeiro Administrador via acesso direto ao servidor (bootstrap)",
        autor=None,
        autor_descricao="bootstrap (promover-admin)",
        origem=OrigemAcao.SISTEMA,
        guild_id=guild_id,
    )
    return membro
