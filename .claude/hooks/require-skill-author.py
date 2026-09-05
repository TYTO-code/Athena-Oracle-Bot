#!/usr/bin/env python3
"""Gating mechanism do harness .claude/: exige `author:` no frontmatter de todo SKILL.md novo.

Qualquer pessoa que trabalhe neste projeto pode criar uma Skill em .claude/skills/ — sem um
registro de quem criou, não há como saber a quem perguntar quando a Skill ficar desatualizada ou
gerar dúvida. Este hook roda em PreToolUse, com matcher "Write" e `if` filtrando só chamadas que
escrevem um arquivo terminado em SKILL.md (ver .claude/settings.json) — nunca em Edit, porque uma
edição parcial não carrega o frontmatter inteiro no payload, o que geraria falso negativo.

Contrato: lê o payload da ferramenta em stdin, decide "allow"/"deny" via
hookSpecificOutput.permissionDecision, sempre sai com exit 0 (quem bloqueia é o JSON, não o
código de saída).
"""

import json
import sys


def extrair_frontmatter(conteudo: str) -> list[str]:
    linhas = conteudo.splitlines()
    dentro = False
    bloco: list[str] = []
    for linha in linhas:
        if linha.strip() == "---":
            if not dentro:
                dentro = True
                continue
            break
        if dentro:
            bloco.append(linha)
    return bloco


def tem_autor(frontmatter: list[str]) -> bool:
    for linha in frontmatter:
        chave, _, valor = linha.partition(":")
        if chave.strip() == "author" and valor.strip():
            return True
    return False


def responder(permission_decision: str, motivo: str | None = None) -> None:
    saida = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": permission_decision,
        }
    }
    if motivo:
        saida["hookSpecificOutput"]["permissionDecisionReason"] = motivo
    print(json.dumps(saida))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Payload malformado não é motivo pra bloquear uma escrita legítima — falha aberta.
        responder("allow")
        return

    conteudo = (payload.get("tool_input") or {}).get("content") or ""
    frontmatter = extrair_frontmatter(conteudo)

    if tem_autor(frontmatter):
        responder("allow")
        return

    responder(
        "deny",
        "Gate: SKILL.md sem campo 'author:' no frontmatter. Toda Skill precisa registrar quem a "
        "criou (nome ou handle) — adicione 'author: <nome>' e, se possível, 'created: AAAA-MM-DD' "
        "antes do '---' de fechamento.",
    )


if __name__ == "__main__":
    main()
