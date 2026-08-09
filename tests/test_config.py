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
    assert any("WEBHOOK_SECRET" in p for p in pendencias)
    assert any("PostgreSQL" in p for p in pendencias)


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
