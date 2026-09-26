"""Backup local e cópia remota com retenção própria — RNF-005 / US-402."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from oraculo.db.base import agora, sessao
from oraculo.db.models import RegistroAuditoria
from oraculo.integrations.armazenamento_backup import ObjetoRemoto, criar_armazenamento_remoto
from oraculo.tasks.backup import _limpar_remotos, executar_backup


@dataclass
class ArmazenamentoFalso:
    objetos: dict[str, ObjetoRemoto] = field(default_factory=dict)
    enviados: list[tuple[str, int]] = field(default_factory=list)
    falhar_envio: bool = False

    async def enviar(self, arquivo: Path, chave: str) -> None:
        if self.falhar_envio:
            raise ConnectionError("bucket fora do ar")
        self.enviados.append((chave, arquivo.stat().st_size))  # noqa: ASYNC240 — dublê
        self.objetos[chave] = ObjetoRemoto(chave, agora())

    async def listar(self, prefixo: str) -> list[ObjetoRemoto]:
        return [o for chave, o in self.objetos.items() if chave.startswith(prefixo)]

    async def apagar(self, chave: str) -> None:
        del self.objetos[chave]


def test_sem_bucket_nao_ha_armazenamento_remoto(settings):
    assert criar_armazenamento_remoto(settings) is None


async def test_backup_e_enviado_ao_armazenamento_remoto(engine, settings, tmp_path):
    settings.backup_dir = tmp_path
    settings.backup_s3_bucket = "tyto-backups"
    remoto = ArmazenamentoFalso()

    arquivo = await executar_backup(settings, remoto=remoto)

    assert arquivo.exists() and arquivo.stat().st_size > 0
    assert remoto.enviados == [(f"oraculo/backups/{arquivo.name}", arquivo.stat().st_size)]

    async with sessao(settings) as session:
        registro = await session.scalar(
            select(RegistroAuditoria).where(RegistroAuditoria.acao == "backup.executado")
        )
    assert registro.dados["remoto"]["chave"] == f"oraculo/backups/{arquivo.name}"


async def test_falha_no_remoto_nao_invalida_o_backup_local(engine, settings, tmp_path):
    settings.backup_dir = tmp_path
    remoto = ArmazenamentoFalso(falhar_envio=True)

    arquivo = await executar_backup(settings, remoto=remoto)

    assert arquivo.exists()
    async with sessao(settings) as session:
        registro = await session.scalar(
            select(RegistroAuditoria).where(RegistroAuditoria.acao == "backup.executado")
        )
    assert "bucket fora do ar" in registro.dados["remoto"]["erro"]


async def test_retencao_remota_apaga_expirados_mas_nunca_o_mais_recente():
    velho = agora() - timedelta(days=200)
    remoto = ArmazenamentoFalso(
        objetos={
            "p/a": ObjetoRemoto("p/a", velho),
            "p/b": ObjetoRemoto("p/b", velho - timedelta(days=1)),
            "p/c": ObjetoRemoto("p/c", agora() - timedelta(days=10)),
            "outro/x": ObjetoRemoto("outro/x", velho),
        }
    )

    removidos = await _limpar_remotos(remoto, "p/", dias=90)

    assert removidos == 2
    assert set(remoto.objetos) == {"p/c", "outro/x"}

    # Só expirados: o mais recente fica mesmo vencido.
    so_velhos = ArmazenamentoFalso(objetos={"p/a": ObjetoRemoto("p/a", velho)})
    assert await _limpar_remotos(so_velhos, "p/", dias=90) == 0
    assert set(so_velhos.objetos) == {"p/a"}
