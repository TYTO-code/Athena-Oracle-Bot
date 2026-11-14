"""Gerente dos projetos na Atena: entrega da fila e respostas dos comandos fixos.

Nada aqui chama o modelo de linguagem: o teste `test_nenhum_modulo_do_gerente_importa_llm`
garante isso olhando os imports, como pede o critério de aceite do plano.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.domain.gerente_respostas import (
    formatar_meus_prazos,
    formatar_minhas_tasks,
    formatar_missoes,
    formatar_status,
)
from oraculo.services.gerente_entrega_service import GerenteEntregaService, ResultadoEnvio


class FonteFalsa:
    def __init__(self, itens: list[dict[str, Any]], falhar_fila: bool = False) -> None:
        self.itens = itens
        self.confirmados: list[tuple[str, str]] = []
        self.falhar_fila = falhar_fila

    async def fila(self, limite: int = 20) -> list[dict[str, Any]]:
        if self.falhar_fila:
            raise IntegracaoIndisponivelError("TYTO.club-API", "fora")
        return self.itens[:limite]

    async def confirmar(self, item_id: str, status: str) -> None:
        self.confirmados.append((item_id, status))

    async def consultar(self, recurso: str, discord_id: int, **params: str) -> dict[str, Any]:
        return {}


class RemetenteFalso:
    def __init__(self, dm: str = ResultadoEnvio.ENTREGUE) -> None:
        self.dms: list[tuple[int, str]] = []
        self.canal: list[str] = []
        self.dm_resultado = dm

    async def enviar_dm(self, discord_id: int, texto: str) -> str:
        self.dms.append((discord_id, texto))
        return self.dm_resultado

    async def publicar_no_canal(self, texto: str) -> str:
        self.canal.append(texto)
        return ResultadoEnvio.ENTREGUE


async def test_entrega_dm_e_canal_e_confirma_cada_item():
    fonte = FonteFalsa(
        [
            {"id": "a", "target": {"kind": "dm", "discordId": "123456789012345678"}, "text": "Olá"},
            {"id": "b", "target": {"kind": "canal"}, "text": "Missões esperando alguém"},
        ]
    )
    remetente = RemetenteFalso()
    relatorio = await GerenteEntregaService(fonte, remetente).entregar_pendentes()

    assert remetente.dms == [(123456789012345678, "Olá")]
    assert remetente.canal == ["Missões esperando alguém"]
    assert fonte.confirmados == [("a", "sent"), ("b", "sent")]
    assert relatorio.entregues == 2


async def test_dm_fechada_e_alvo_invalido_nao_insistem():
    fonte = FonteFalsa(
        [
            {"id": "a", "target": {"kind": "dm", "discordId": "123456789012345678"}, "text": "Olá"},
            {"id": "b", "target": {"kind": "dm", "discordId": "fulano"}, "text": "Olá"},
            {"id": "c", "target": {"kind": "dm", "discordId": "1"}, "text": ""},
        ]
    )
    relatorio = await GerenteEntregaService(
        fonte, RemetenteFalso(dm=ResultadoEnvio.RECUSADO)
    ).entregar_pendentes()
    assert [s for _, s in fonte.confirmados] == ["failed", "failed", "failed"]
    assert relatorio.recusadas == 3


async def test_api_fora_do_ar_nao_derruba_o_ciclo():
    relatorio = await GerenteEntregaService(
        FonteFalsa([], falhar_fila=True), RemetenteFalso()
    ).entregar_pendentes()
    assert relatorio.entregues == 0


def test_meus_prazos_ordena_por_prazo_e_marca_atraso():
    texto = formatar_meus_prazos(
        {
            "vinculado": True,
            "tasks": [
                {"name": "B", "projeto": "Alpha", "dueAt": 2_000_000_000_000},
                {"name": "A", "projeto": "Alpha", "dueAt": 1_000_000_000_000, "atrasada": True},
                {"name": "Sem prazo", "projeto": "Alpha", "dueAt": None},
            ],
            "lastSyncAt": 1_000_000_000_000,
        }
    )
    assert texto.index("A (Alpha)") < texto.index("B (Alpha)")
    assert "⚠️ atrasada" in texto
    assert "Sem prazo" not in texto
    assert "<t:1000000000:d>" in texto


def test_sem_vinculo_orienta_a_completar_o_cadastro():
    assert "ID do Discord" in formatar_minhas_tasks({"vinculado": False})


def test_status_nao_confirma_projeto_alheio():
    assert "Não encontrei" in formatar_status({"vinculado": True, "encontrado": False})


def test_status_resumo_publico_nao_mostra_numeros_internos():
    texto = formatar_status(
        {
            "vinculado": True,
            "encontrado": True,
            "acesso": "resumo",
            "projeto": {"title": "Alpha", "health": {"state": "ok", "open": 9, "overdue": 3}},
        }
    )
    assert "Alpha" in texto
    assert "Atrasadas" not in texto


def test_status_completo_com_carga_e_pessoas_quando_a_api_manda():
    texto = formatar_status(
        {
            "vinculado": True,
            "encontrado": True,
            "acesso": "completo",
            "projeto": {
                "title": "Alpha",
                "health": {"state": "atencao", "open": 4, "overdue": 1, "doneThisWeek": 2},
                "carga": [{"nome": "Ana", "open": 3, "overdue": 1}],
                "pessoasEmAtencao": [{"nome": "Bia", "days": 9, "level": "alerta"}],
            },
        }
    )
    assert "Atrasadas: 1" in texto
    assert "Ana: 3 abertas" in texto
    assert "Bia: 9 dias" in texto


def test_missoes_em_tom_de_convite():
    texto = formatar_missoes(
        {"missoes": [{"title": "Logo", "rewardDracmas": 100, "rewardXp": 50, "url": "https://x"}]}
    )
    assert "esperando alguém" in texto
    assert "[Logo](https://x): 100 Dracmas, 50 XP" in texto


def test_nenhum_modulo_do_gerente_importa_llm():
    raiz = Path(__file__).resolve().parents[1] / "src" / "oraculo"
    arquivos = [
        raiz / "domain" / "gerente_respostas.py",
        raiz / "services" / "gerente_entrega_service.py",
        raiz / "integrations" / "gerente_api.py",
        raiz / "bot" / "cogs" / "gerente.py",
    ]
    for arquivo in arquivos:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        nomes = {
            alias.name
            for no in ast.walk(arvore)
            if isinstance(no, ast.Import | ast.ImportFrom)
            for alias in no.names
        } | {
            no.module or ""
            for no in ast.walk(arvore)
            if isinstance(no, ast.ImportFrom)
        }
        assert not any("anthropic" in n or "llm" in n for n in nomes), arquivo.name
