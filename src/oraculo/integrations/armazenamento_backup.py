"""Cópia remota dos backups — RNF-005 / US-402 (retenção fora do disco local).

O disco de um container (Render/Railway) some junto com ele; um backup que só
existe ali não sobrevive ao incidente que mais precisa dele. Esta porta envia
cada arquivo para um object storage compatível com S3 e aplica uma retenção
própria, independente da local.

`boto3` é síncrono: as chamadas rodam em thread (`asyncio.to_thread`), como no
Google Agenda.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from oraculo.config import Settings
from oraculo.logging_config import get_logger

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class ObjetoRemoto:
    chave: str
    modificado_em: datetime


class ArmazenamentoRemoto(Protocol):
    """Destino remoto dos backups — qualquer coisa que envie, liste e apague arquivos."""

    async def enviar(self, arquivo: Path, chave: str) -> None: ...

    async def listar(self, prefixo: str) -> list[ObjetoRemoto]: ...

    async def apagar(self, chave: str) -> None: ...


class ArmazenamentoS3:
    """Object storage compatível com S3 (AWS, R2, B2, MinIO, buckets do Railway)."""

    def __init__(self, cfg: Settings) -> None:
        if not cfg.backup_s3_bucket:
            raise ValueError("ArmazenamentoS3 exige ORACULO_BACKUP_S3_BUCKET.")
        self._bucket = cfg.backup_s3_bucket
        self._endpoint = cfg.backup_s3_endpoint_url
        self._regiao = cfg.backup_s3_regiao
        self._cliente: Any | None = None

    def _conectar(self) -> Any:
        if self._cliente is None:
            import boto3

            self._cliente = boto3.client(
                "s3", endpoint_url=self._endpoint, region_name=self._regiao
            )
        return self._cliente

    async def enviar(self, arquivo: Path, chave: str) -> None:
        await asyncio.to_thread(self._conectar().upload_file, str(arquivo), self._bucket, chave)

    async def listar(self, prefixo: str) -> list[ObjetoRemoto]:
        return await asyncio.to_thread(self._listar_sync, prefixo)

    async def apagar(self, chave: str) -> None:
        await asyncio.to_thread(self._conectar().delete_object, Bucket=self._bucket, Key=chave)

    def _listar_sync(self, prefixo: str) -> list[ObjetoRemoto]:
        paginador = self._conectar().get_paginator("list_objects_v2")
        return [
            ObjetoRemoto(chave=item["Key"], modificado_em=item["LastModified"])
            for pagina in paginador.paginate(Bucket=self._bucket, Prefix=prefixo)
            for item in pagina.get("Contents", [])
        ]


def criar_armazenamento_remoto(cfg: Settings) -> ArmazenamentoRemoto | None:
    """`None` quando não há bucket configurado — o backup fica só no disco."""
    if not cfg.backup_s3_bucket:
        return None
    return ArmazenamentoS3(cfg)
