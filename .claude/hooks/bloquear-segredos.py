#!/usr/bin/env python3
"""Gating mechanism do harness .claude/: barra `git commit` que inclui segredos ou dados pessoais.

Repositórios do Clube TYTO vão se tornar públicos e o histórico do git é permanente: o que entra
num commit não sai mais sem reescrever o histórico. Este hook roda em PreToolUse (matcher "Bash",
`if: Bash(git commit *)`, ver .claude/settings.json), olha só o que está **staged** e nega o commit
quando acha:

* arquivos que não devem ser versionados (`.env`, chaves `.pem`/`.key`, contas de serviço);
* chaves privadas, tokens (AWS, GitHub, Slack, Discord) e atribuições `senha = "valor longo"`;
* e-mails pessoais (gmail, outlook, hotmail, yahoo, icloud, proton) — use o `noreply` do GitHub.

Para uma linha legítima (ex.: e-mail de exemplo em documentação), acrescente `allow-secret` ou
`allow-pessoal` num comentário da própria linha. O hook nunca imprime o valor encontrado, só o
arquivo e o tipo — a saída vai para o log da sessão.

Contrato de hook PreToolUse: lê o payload em stdin (ignorado), imprime em stdout um JSON com
hookSpecificOutput.permissionDecision "allow" ou "deny" e sempre sai com exit 0.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import PurePosixPath

NOMES_PROIBIDOS = [
    (re.compile(r"(^|/)\.env($|\.(?!example$|sample$|template$)[^/]+$)"), "arquivo .env (use .env.example)"),
    (re.compile(r"\.(pem|key|p12|pfx|jks|keystore)$", re.I), "chave/certificado privado"),
    (re.compile(r"(^|/)(id_rsa|id_ed25519)$"), "chave SSH privada"),
    (re.compile(r"service[-_]?account.*\.json$|firebase-adminsdk.*\.json$|credentials?\.json$", re.I), "credencial de serviço"),
]

IGNORAR_ARQUIVOS = re.compile(
    r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|\.lock|\.min\.(js|css)|\.(png|jpe?g|gif|webp|ico|pdf|woff2?|ttf|mp3|wav|zip))$",
    re.I,
)

PADROES = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "chave privada"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "chave de acesso AWS"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b"), "token do GitHub"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "token do Slack"),
    (re.compile(r"\b[MNO][A-Za-z0-9_-]{23}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b"), "token de bot do Discord"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"), "chave de API (sk-...)"),
    (
        re.compile(
            r"""(?ix)\b(?:senha|password|passwd|secret|api[_-]?key|token|private[_-]?key)\w*\s*[:=]\s*["'][^"'\s]{16,}["']"""
        ),
        "credencial atribuída a um valor literal",
    ),
]

# Valores que parecem segredo mas são exemplo/placeholder.
PLACEHOLDER = re.compile(
    r"(?i)(example|exemplo|placeholder|changeme|troque|your[-_]|seu[-_]|xxxx|\*{3,}|<[^>]+>|\$\{|%\(|process\.env|os\.environ|getenv)"
)

EMAIL_PESSOAL = re.compile(
    r"\b[\w.+-]+@(?:gmail|googlemail|outlook|hotmail|live|yahoo|icloud|proton(?:mail)?|pm)\.(?:com|me|com\.br|net)\b",
    re.I,
)
EMAIL_OK = re.compile(r"(?i)(noreply|no-reply|example|exemplo|teste@|test@|seu-email|novo-email|fulano|email@email)")

MARCAS = ("allow-secret", "allow-pessoal")


def analisar(diff: str, arquivos: list[str]) -> list[str]:
    """Achados (arquivo + tipo, nunca o valor) para o diff staged e a lista de arquivos staged."""
    achados: list[str] = []

    for arquivo in arquivos:
        for padrao, tipo in NOMES_PROIBIDOS:
            if padrao.search(arquivo):
                achados.append(f"{arquivo}: {tipo}")

    atual = ""
    ignorar = False
    for linha in diff.splitlines():
        if linha.startswith("+++ "):
            atual = linha[4:].removeprefix("b/")
            ignorar = bool(IGNORAR_ARQUIVOS.search(atual)) or PurePosixPath(atual).name == "package-lock.json"
            continue
        if ignorar or not linha.startswith("+") or linha.startswith("+++"):
            continue
        conteudo = linha[1:]
        if any(marca in conteudo for marca in MARCAS):
            continue

        for padrao, tipo in PADROES:
            achado = padrao.search(conteudo)
            if achado and not PLACEHOLDER.search(achado.group(0)):
                achados.append(f"{atual}: {tipo}")
        for email in EMAIL_PESSOAL.finditer(conteudo):
            if not EMAIL_OK.search(email.group(0)):
                achados.append(f"{atual}: e-mail pessoal (use o noreply do GitHub)")

    return sorted(set(achados))


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False).stdout


def main() -> int:
    raiz = os.environ.get("CLAUDE_PROJECT_DIR")
    if raiz:
        os.chdir(raiz)
    try:
        arquivos = [a for a in _git("diff", "--cached", "--name-only").splitlines() if a]
        achados = analisar(_git("diff", "--cached", "-U0", "--no-color"), arquivos)
    except Exception as erro:  # nunca travar o commit por falha do próprio hook
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
              "permissionDecisionReason": f"Gate de segredos não pôde rodar ({erro}); confira o diff à mão."}}))
        return 0

    if not achados:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}))
        return 0

    motivo = (
        "Gate: o commit tem segredo ou dado pessoal e foi bloqueado — " + "; ".join(achados[:12])
        + ". Remova do staged (git restore --staged) ou, se for legítimo, marque a linha com "
        "`allow-secret`/`allow-pessoal`. O que já foi commitado antes não sai sem reescrever o histórico."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
          "permissionDecisionReason": motivo}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
