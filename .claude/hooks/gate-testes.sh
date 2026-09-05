#!/usr/bin/env bash
# Gating mechanism do harness .claude/ deste repositório.
#
# Barra `git commit`/`git push` a menos que `make test` (146 testes, pytest) passe primeiro —
# mas só quando dá pra rodar de verdade. Este repositório exige um venv Python instalado
# (`make setup`) para testar localmente; em máquina sem espaço/capacidade pra isso, o gate não
# pode travar todo commit para sempre — ele libera com aviso, e quem verifica de fato é o CI
# (.github/workflows/ci.yml), que roda `make test` num ambiente próprio a cada push/PR.
#
# Contrato de hook PreToolUse: lê o payload em stdin (ignorado aqui — o filtro `if` em
# .claude/settings.json já resolveu que o comando é commit/push), roda os testes quando possível,
# e imprime em stdout um JSON com hookSpecificOutput.permissionDecision "allow" ou "deny". Sempre
# sai com exit 0 — quem decide bloquear é o campo do JSON, não o código de saída deste script.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

if [ ! -x .venv/bin/python ]; then
  cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"Gate: sem .venv nesta máquina (make setup não rodado) — verificação local pulada; o CI (.github/workflows/ci.yml) roda a suíte de verdade a cada push/PR. Confirme lá antes de considerar a mudança segura."}}
EOF
  exit 0
fi

LOG="$(mktemp)"
if make test > "$LOG" 2>&1; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  rm -f "$LOG"
  exit 0
fi

TAIL=$(tail -n 40 "$LOG" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')
rm -f "$LOG"
cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Gate: make test falhou em Athena-Oracle-Bot (venv presente, teste real rodou e falhou) — commit/push bloqueado até os testes passarem. Últimas linhas: ${TAIL}"}}
EOF
exit 0
