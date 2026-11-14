"""Roteador antes da IA no `/perguntar` (fase 6 de docs/GERENTE_PLANO.md, D14).

Perguntas que um comando fixo responde melhor (prazos, tasks, situação de um projeto, missões
abertas) não chegam ao modelo: a Atena responde com os mesmos dados de `/meus-prazos`,
`/minhas-tasks`, `/status` e `/missoes`, sem custo de API e sem chance de inventar número.

Puro e conservador: só desvia quando a intenção é clara. Na dúvida, a pergunta segue para a IA.
Também normaliza perguntas para o cache de respostas repetidas (`normalizar`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rota:
    comando: str  # "meus-prazos" | "minhas-tasks" | "status" | "missoes"
    projeto: str = ""


def normalizar(texto: str) -> str:
    """Sem acento, sem caixa, sem pontuação, espaços únicos."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    limpo = re.sub(r"[^\w\s-]", " ", sem_acento.casefold())
    return re.sub(r"\s+", " ", limpo).strip()


_PRAZOS = re.compile(
    r"\b(meus? prazos?|minhas? (entregas?|deadlines?)|quando (vence|vencem|e a entrega)|"
    r"o que (vence|esta vencendo)|tenho (algo|alguma coisa|tasks?|tarefas?) (atrasad|vencend))"
)
_TASKS = re.compile(
    r"\b(minhas? (tasks?|tarefas?|pendencias)|quais (sao )?(as )?minhas (tasks?|tarefas?)|"
    r"o que (eu )?(tenho|preciso) (pra|para|que) fazer)"
)
_MISSOES = re.compile(
    r"\b(missoes? (abertas?|disponiveis?|livres?|sem ninguem|paradas?|abandonadas?)|"
    r"(tem|ha|existe|existem) (alguma )?miss(ao|oes) (aberta|disponivel|livre)s?)"
)
_STATUS = re.compile(
    r"\b(?:status|situacao|andamento) (?:do|da|de) (?:projeto )?(?P<a>[\w -]{2,60})$|"
    r"\bcomo (?:esta|anda|vai) (?:o|a) (?:projeto )?(?P<b>[\w -]{2,60})$"
)
#: Pedidos que ninguém deveria desviar: explicação, opinião, regra.
_ABERTA = re.compile(r"\b(por que|porque|explique|explica|regra|regulamento|como funciona)\b")


def rotear(pergunta: str) -> Rota | None:
    texto = normalizar(pergunta)
    if not texto or _ABERTA.search(texto):
        return None
    if _PRAZOS.search(texto):
        return Rota("meus-prazos")
    if _TASKS.search(texto):
        return Rota("minhas-tasks")
    if _MISSOES.search(texto):
        return Rota("missoes")
    achado = _STATUS.search(texto)
    if achado:
        projeto = (achado.group("a") or achado.group("b") or "").strip(" -")
        if projeto and projeto not in {"meu projeto", "projeto", "meus projetos"}:
            return Rota("status", projeto)
    return None
