"""Respostas dos comandos fixos do gerente (`/meus-prazos`, `/minhas-tasks`, `/status`, `/missoes`).

Puro: recebe o JSON já filtrado pela TYTO.club-API e devolve texto. Nenhuma IA, nenhuma decisão
de permissão (a API só manda o que a pessoa pode ver; aqui não se acrescenta nada). Datas vão no
formato `<t:…:d>` do Discord, que cada pessoa vê no próprio fuso.
"""

from __future__ import annotations

from typing import Any

LIMITE_ITENS = 15

ESTADO_PROJETO = {
    "ok": "🟢 em dia",
    "atencao": "🟡 com tasks atrasadas",
    "parado": "🔴 parado",
    "sem_tasks": "⚪ sem tasks no ClickUp",
    "inativo": "⏸️ pausado ou concluído",
}

NIVEL_PESSOA = {"atencao": "atenção", "alerta": "alerta", "risco": "risco"}


def _data(ms: object) -> str:
    try:
        return f"<t:{int(float(str(ms)) // 1000)}:d>"
    except (TypeError, ValueError):
        return "sem prazo"


def _sem_vinculo() -> str:
    return (
        "Não encontrei seu cadastro no site da TYTO com este Discord. Confira o campo "
        "**ID do Discord** no seu perfil (o número, não o nome de usuário)."
    )


def _rodape(dados: dict[str, Any]) -> str:
    sync = dados.get("lastSyncAt")
    return f"\n\n_Última sincronização com o ClickUp: {_data(sync)}_" if sync else ""


def _tasks(dados: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in dados.get("tasks") or [] if isinstance(t, dict)]


def _linha_task(task: dict[str, Any]) -> str:
    nome = str(task.get("name") or "(sem título)")
    url = task.get("url")
    titulo = f"[{nome}]({url})" if url else nome
    projeto = task.get("projeto") or "projeto"
    prazo = _data(task.get("dueAt")) if task.get("dueAt") else "sem prazo"
    atraso = " ⚠️ atrasada" if task.get("atrasada") else ""
    return f"• {titulo} ({projeto}): {prazo}{atraso}"


def formatar_meus_prazos(dados: dict[str, Any]) -> str:
    if dados.get("vinculado") is False:
        return _sem_vinculo()
    com_prazo = sorted(
        (t for t in _tasks(dados) if t.get("dueAt")), key=lambda t: float(t.get("dueAt") or 0)
    )
    if not com_prazo:
        return "Você não tem tasks com prazo nos projetos. 🦉" + _rodape(dados)
    linhas = [_linha_task(t) for t in com_prazo[:LIMITE_ITENS]]
    if len(com_prazo) > LIMITE_ITENS:
        linhas.append(f"… e mais {len(com_prazo) - LIMITE_ITENS}.")
    return "\n".join(linhas) + _rodape(dados)


def formatar_minhas_tasks(dados: dict[str, Any]) -> str:
    if dados.get("vinculado") is False:
        return _sem_vinculo()
    tasks = _tasks(dados)
    if not tasks:
        return (
            "Você não tem tasks abertas atribuídas a você no ClickUp dos projetos."
            + _rodape(dados)
        )
    por_projeto: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        por_projeto.setdefault(str(task.get("projeto") or "Projeto"), []).append(task)
    blocos: list[str] = []
    mostradas = 0
    for projeto in sorted(por_projeto):
        itens = por_projeto[projeto]
        blocos.append(f"**{projeto}** ({len(itens)})")
        for task in itens:
            if mostradas >= LIMITE_ITENS:
                break
            blocos.append(_linha_task(task))
            mostradas += 1
    if len(tasks) > mostradas:
        blocos.append(f"… e mais {len(tasks) - mostradas}. Veja tudo no painel do site.")
    return "\n".join(blocos) + _rodape(dados)


def formatar_status(dados: dict[str, Any]) -> str:
    if dados.get("vinculado") is False:
        return _sem_vinculo()
    if not dados.get("encontrado"):
        # Mesma resposta para "não existe" e "sem acesso": não confirma projeto alheio.
        return "Não encontrei um projeto com esse nome entre os que você pode ver."
    projeto = dados.get("projeto") or {}
    saude = projeto.get("health") or {}
    titulo = projeto.get("title") or "Projeto"
    linhas = [f"**{titulo}**: {ESTADO_PROJETO.get(str(saude.get('state')), 'sem dados')}"]
    if dados.get("acesso") == "completo":
        linhas.append(
            f"Abertas: {saude.get('open', 0)} · Atrasadas: {saude.get('overdue', 0)} · "
            f"Concluídas na semana: {saude.get('doneThisWeek', 0)}"
        )
    if saude.get("nextDueAt"):
        linhas.append(f"Próximo prazo: {_data(saude.get('nextDueAt'))}")
    if saude.get("daysSinceMovement") is not None and dados.get("acesso") == "completo":
        linhas.append(f"Último movimento no ClickUp há {saude.get('daysSinceMovement')} dia(s).")

    carga = [c for c in projeto.get("carga") or [] if isinstance(c, dict)]
    if carga:
        linhas.append("\n**Carga por membro**")
        for c in carga[:LIMITE_ITENS]:
            linhas.append(
                f"• {c.get('nome')}: {c.get('open', 0)} abertas, {c.get('overdue', 0)} atrasadas"
            )

    pessoas = [p for p in projeto.get("pessoasEmAtencao") or [] if isinstance(p, dict)]
    if pessoas:
        linhas.append("\n**Pessoas em atenção** (visível só para administração e Conselho)")
        for p in pessoas[:LIMITE_ITENS]:
            nivel = NIVEL_PESSOA.get(str(p.get("level")), str(p.get("level")))
            linhas.append(f"• {p.get('nome')}: {p.get('days')} dias sem atividade ({nivel})")
    return "\n".join(linhas) + _rodape(dados)


def formatar_missoes(dados: dict[str, Any]) -> str:
    missoes = [m for m in dados.get("missoes") or [] if isinstance(m, dict)]
    if not missoes:
        return "Nenhuma missão aberta esperando alguém agora. 🦉"
    linhas = ["Estas missões estão esperando alguém. Quem quiser, é só pegar no site:"]
    for m in missoes[:LIMITE_ITENS]:
        titulo = m.get("title") or "Missão"
        url = m.get("url")
        nome = f"[{titulo}]({url})" if url else titulo
        linhas.append(f"• {nome}: {m.get('rewardDracmas', 0)} Dracmas, {m.get('rewardXp', 0)} XP")
    return "\n".join(linhas)
