"""Configuração da aplicação a partir de variáveis de ambiente.

TD-001 / RNF-003 — nenhum segredo é lido do código-fonte: tudo vem de `.env`
(carregado por `pydantic-settings`) ou do ambiente do container.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    """Todas as configurações do Bot Oráculo, prefixadas com `ORACULO_`."""

    model_config = SettingsConfigDict(
        env_prefix="ORACULO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Aplicação -----------------------------------------------------------
    env: Environment = "development"
    log_level: str = "INFO"
    run_bot: bool = True
    run_api: bool = True

    # --- Discord (RF-001) ----------------------------------------------------
    discord_token: str | None = None
    # `NoDecode`: o valor cru chega ao validador abaixo em vez de ser lido como JSON.
    discord_guild_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    discord_log_channel_id: int | None = None

    # --- Banco de dados (TD-002 / ADR-001) -----------------------------------
    database_url: str = "sqlite+aiosqlite:///./data/oraculo.sqlite3"
    db_echo: bool = False

    # --- Cache (US-404 / RNF-001) --------------------------------------------
    redis_url: str | None = None
    ranking_cache_ttl: int = 60

    # --- API / Webhooks (TD-003 / RNF-003) -----------------------------------
    api_host: str = "0.0.0.0"  # noqa: S104 — exposto pelo container, não pelo host
    api_port: int = 8000
    clickup_webhook_secret: str | None = None
    webhook_max_skew_seconds: int = 300

    # --- Google Agenda (RN-009 / RF-011) -------------------------------------
    google_enabled: bool = False
    google_calendar_id: str = "primary"
    google_credentials_file: Path | None = None
    google_timezone: str = "America/Sao_Paulo"

    # --- E-mail (RF-010) -----------------------------------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "oraculo@clubetyto.example"

    # --- Backup (RNF-005 / US-402) -------------------------------------------
    backup_enabled: bool = False
    backup_dir: Path = Path("./backups")
    backup_hour_utc: int = 6
    backup_retention_days: int = 14

    @field_validator("discord_guild_ids", mode="before")
    @classmethod
    def _split_guild_ids(cls, value: object) -> object:
        """Aceita `123,456` (formato natural em `.env`) além de lista JSON."""
        if isinstance(value, str):
            return [int(part) for part in value.replace(";", ",").split(",") if part.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host)

    def require_discord_token(self) -> str:
        """Falha cedo e com mensagem clara quando o token não foi provisionado."""
        if not self.discord_token:
            raise RuntimeError(
                "ORACULO_DISCORD_TOKEN ausente. Defina-o no `.env` ou nos secrets "
                "do ambiente (TD-001 / RNF-003)."
            )
        return self.discord_token

    def validate_for_production(self) -> list[str]:
        """Lista pendências de segurança que impedem subir em produção (RNF-003)."""
        problems: list[str] = []
        if not self.discord_token:
            problems.append("ORACULO_DISCORD_TOKEN não definido")
        if not self.clickup_webhook_secret:
            problems.append("ORACULO_CLICKUP_WEBHOOK_SECRET não definido (TD-003)")
        if self.database_url.startswith("sqlite"):
            problems.append("SQLite em produção não é suportado pelo ADR-001; use PostgreSQL")
        if self.google_enabled and not self.google_credentials_file:
            problems.append("Google Agenda habilitado sem ORACULO_GOOGLE_CREDENTIALS_FILE")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instância única de configuração (cacheada por processo)."""
    return Settings()
