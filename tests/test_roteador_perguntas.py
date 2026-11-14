"""Roteador antes da IA e cache de respostas repetidas no /perguntar (fase 6)."""

from __future__ import annotations

import pytest

from oraculo.domain.roteador_perguntas import Rota, normalizar, rotear


@pytest.mark.parametrize(
    ("pergunta", "rota"),
    [
        ("Quais são os meus prazos?", Rota("meus-prazos")),
        ("quando vence minha entrega", Rota("meus-prazos")),
        ("Tenho tasks atrasadas?", Rota("meus-prazos")),
        ("Quais são minhas tarefas?", Rota("minhas-tasks")),
        ("o que eu tenho pra fazer", Rota("minhas-tasks")),
        ("Tem missão aberta?", Rota("missoes")),
        ("missões disponíveis", Rota("missoes")),
        ("Qual o status do projeto Alpha Ação?", Rota("status", "alpha acao")),
        ("como está o Atlas", Rota("status", "atlas")),
    ],
)
def test_intencao_clara_vai_para_o_comando_fixo(pergunta, rota):
    assert rotear(pergunta) == rota


@pytest.mark.parametrize(
    "pergunta",
    [
        "Como funciona a regra de XP?",
        "Por que meus prazos são tão curtos?",
        "Explique o regulamento das missões abertas",
        "O que decidiram no projeto?",
        "como está o meu projeto",
        "",
    ],
)
def test_na_duvida_segue_para_a_ia(pergunta):
    assert rotear(pergunta) is None


def test_normalizar():
    assert normalizar("  Qual é a REGRA?! ") == "qual e a regra"
