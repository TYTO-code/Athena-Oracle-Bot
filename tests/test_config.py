"""Configuração e segredos — TD-001 / RNF-003."""

from __future__ import annotations

import pytest

from oraculo.config import Settings


def test_segredos_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv("ORACULO_DISCORD_TOKEN", "token-do-ambiente")
    monkeypatch.setenv("ORACULO_CLICKUP_WEBHOOK_SECRET", "segredo-do-ambiente")

    cfg = Settings(_env_file=None)

    assert cfg.discord_token == "token-do-ambiente"
    assert cfg.clickup_webhook_secret == "segredo-do-ambiente"


def test_token_ausente_falha_com_mensagem_acionavel():
    cfg = Settings(_env_file=None, discord_token=None)

    with pytest.raises(RuntimeError, match="ORACULO_DISCORD_TOKEN"):
        cfg.require_discord_token()


def test_guild_ids_aceitam_lista_separada_por_virgula(monkeypatch):
    monkeypatch.setenv("ORACULO_DISCORD_GUILD_IDS", "123, 456;789")

    cfg = Settings(_env_file=None)

    assert cfg.discord_guild_ids == [123, 456, 789]


def test_variaveis_vazias_equivalem_a_nao_informadas(monkeypatch):
    """Um `.env` copiado do modelo deixa chaves sem valor — isso não pode quebrar."""
    for chave in (
        "ORACULO_DISCORD_LOG_CHANNEL_ID",
        "ORACULO_DISCORD_TOKEN",
        "ORACULO_DISCORD_GUILD_IDS",
        "ORACULO_REDIS_URL",
        "ORACULO_GOOGLE_CREDENTIALS_FILE",
        "ORACULO_SMTP_HOST",
        "ORACULO_SMTP_FROM",
    ):
        monkeypatch.setenv(chave, "")

    cfg = Settings(_env_file=None)

    assert cfg.discord_log_channel_id is None
    assert cfg.discord_token is None
    assert cfg.discord_guild_ids == []
    assert cfg.redis_url is None
    assert cfg.google_credentials_file is None
    assert cfg.email_enabled is False
    # Campo com default não vira None: volta ao valor padrão.
    assert cfg.smtp_from == "oraculo@clubetyto.example"


def test_producao_exige_segredos_e_postgres():
    """RNF-003 — o deploy falha cedo se faltar segredo ou o banco for SQLite."""
    cfg = Settings(
        _env_file=None,
        env="production",
        discord_token=None,
        clickup_webhook_secret=None,
        database_url="sqlite+aiosqlite:///./data/oraculo.sqlite3",
    )

    pendencias = cfg.validate_for_production()

    assert any("DISCORD_TOKEN" in p for p in pendencias)
    assert any("PostgreSQL" in p for p in pendencias)
    # O webhook do ClickUp é da TYTO.club-API (DECISOES.md D8): o segredo local não é exigido.
    assert not any("WEBHOOK_SECRET" in p for p in pendencias)


def test_gerente_exige_url_e_chave_juntas_e_https():
    base = {
        "_env_file": None,
        "env": "production",
        "discord_token": "token",
        "database_url": "postgresql+asyncpg://u:s@db:5432/oraculo",
    }
    so_url = Settings(**base, tyto_api_url="https://api.example.com")
    assert any("TYTO_API_SERVICE_KEY" in p for p in so_url.validate_for_production())
    assert so_url.gerente_habilitado is False

    http = Settings(**base, tyto_api_url="http://api.example.com", tyto_api_service_key="k")
    assert any("https" in p for p in http.validate_for_production())

    ok = Settings(**base, tyto_api_url="https://api.example.com", tyto_api_service_key="k")
    assert ok.validate_for_production() == []
    assert ok.gerente_habilitado is True


def test_configuracao_de_producao_valida_nao_tem_pendencias():
    cfg = Settings(
        _env_file=None,
        env="production",
        discord_token="token",
        clickup_webhook_secret="segredo",
        database_url="postgresql+asyncpg://u:s@db:5432/oraculo",
    )

    assert cfg.validate_for_production() == []


def test_google_habilitado_sem_credenciais_e_pendencia():
    cfg = Settings(
        _env_file=None,
        env="production",
        discord_token="token",
        clickup_webhook_secret="segredo",
        database_url="postgresql+asyncpg://u:s@db:5432/oraculo",
        google_enabled=True,
        google_credentials_file=None,
    )

    assert any("GOOGLE_CREDENTIALS_FILE" in p for p in cfg.validate_for_production())
