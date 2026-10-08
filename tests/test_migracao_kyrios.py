"""Migração `d4e5f6a7b8c9`: o slug `dominador` vira `kyrios` sem tocar em mais nada."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

CAMINHO = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "20261008_d4e5f6a7b8c9_dominador_vira_kyrios.py"
)


def _carregar():
    spec = importlib.util.spec_from_file_location("migracao_kyrios", CAMINHO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _banco():
    motor = sa.create_engine("sqlite://")
    with motor.begin() as conexao:
        conexao.execute(sa.text("CREATE TABLE membros (id INTEGER PRIMARY KEY, patente_slug TEXT)"))
        conexao.execute(
            sa.text(
                "CREATE TABLE promocoes (id INTEGER PRIMARY KEY, "
                "cargo_anterior TEXT, cargo_novo TEXT)"
            )
        )
        conexao.execute(
            sa.text(
                "INSERT INTO membros (patente_slug) VALUES "
                "('dominador'), ('monarca'), ('renovek'), ('omni')"
            )
        )
        conexao.execute(
            sa.text(
                "INSERT INTO promocoes (cargo_anterior, cargo_novo) VALUES "
                "('monarca', 'dominador'), ('dominador', 'renovek'), ('oficial', 'centuriao')"
            )
        )
    return motor


def _rodar(motor, funcao: str) -> None:
    modulo = _carregar()
    with motor.begin() as conexao:
        with Operations.context(MigrationContext.configure(conexao)):
            getattr(modulo, funcao)()


def _estado(motor):
    with motor.connect() as conexao:
        membros = [
            r[0] for r in conexao.execute(sa.text("SELECT patente_slug FROM membros ORDER BY id"))
        ]
        promocoes = [
            tuple(r)
            for r in conexao.execute(
                sa.text("SELECT cargo_anterior, cargo_novo FROM promocoes ORDER BY id")
            )
        ]
    return membros, promocoes


def test_upgrade_renomeia_so_o_slug_dominador():
    motor = _banco()

    _rodar(motor, "upgrade")

    membros, promocoes = _estado(motor)
    assert membros == ["kyrios", "monarca", "renovek", "omni"]
    assert promocoes == [("monarca", "kyrios"), ("kyrios", "renovek"), ("oficial", "centuriao")]


def test_upgrade_e_idempotente_e_downgrade_desfaz():
    motor = _banco()

    _rodar(motor, "upgrade")
    _rodar(motor, "upgrade")
    assert _estado(motor)[0][0] == "kyrios"

    _rodar(motor, "downgrade")
    membros, promocoes = _estado(motor)
    assert membros == ["dominador", "monarca", "renovek", "omni"]
    assert promocoes[0] == ("monarca", "dominador")
