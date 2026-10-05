"""Trava de publicação: o repositório é público (ver LICENSE e SECURITY.md).

Falha se um arquivo versionado contiver algo que parece segredo, se um arquivo de segredo
for versionado, ou se o regulamento do Clube (privado) entrar em `docs/regras-tyto/`.
"""

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

PADROES_DE_SEGREDO = {
    "chave AWS": re.compile(r"AKIA[0-9A-Z]{16}"),
    "chave Google/Firebase": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "chave Anthropic/OpenAI": re.compile(r"sk-(?:ant-)?[A-Za-z0-9_\-]{32,}"),
    "token GitHub": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"),
    "token Slack": re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    "chave privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "token de bot Discord": re.compile(
        r"\b[MN][A-Za-z0-9_\-]{23,25}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}\b"
    ),
    "URL com senha": re.compile(r"://[^/\s:@]+:[^/\s:@$\{]{6,}@(?!db\b|localhost|cache\b)"),
}
NOMES_PROIBIDOS = re.compile(
    r"(^|/)(\.env(\..+)?|credentials\.json|token\.json|.*service-?account.*\.json"
    r"|firebase-adminsdk.*\.json|.*\.(pem|key|p12|pfx|sqlite3|db))$",
    re.IGNORECASE,
)


def _versionados() -> list[Path]:
    saida = subprocess.run(  # noqa: S603 — comando fixo, sem entrada externa
        ["git", "ls-files", "-z"],  # noqa: S607 — `git` do PATH, como no CI
        cwd=RAIZ,
        capture_output=True,
        check=True,
    ).stdout.decode()
    return [Path(p) for p in saida.split("\0") if p]


def test_nenhum_arquivo_de_segredo_versionado():
    ruins = [
        str(p)
        for p in _versionados()
        if NOMES_PROIBIDOS.search(str(p)) and p.name != ".env.example"
    ]
    assert ruins == []


def test_nenhum_conteudo_parece_segredo():
    achados = []
    for p in _versionados():
        if p.suffix in {".pdf", ".png", ".jpg", ".ico", ".lock"} or not (RAIZ / p).is_file():
            continue
        texto = (RAIZ / p).read_text(encoding="utf-8", errors="ignore")
        for nome, padrao in PADROES_DE_SEGREDO.items():
            if padrao.search(texto):
                achados.append(f"{p}: {nome}")
    assert achados == []


def test_regulamento_privado_nao_e_versionado():
    dentro = [str(p) for p in _versionados() if str(p).startswith("docs/regras-tyto/")]
    assert dentro == ["docs/regras-tyto/README.md"]


def test_licenca_e_politica_de_seguranca_existem_em_ingles():
    licenca = (RAIZ / "LICENSE").read_text(encoding="utf-8")
    assert "All rights reserved" in licenca and "NO IMPLIED LICENSE" in licenca
    assert "train" in licenca, "a licença deve vedar o uso para treino de modelos"
    seguranca = (RAIZ / "SECURITY.md").read_text(encoding="utf-8")
    assert "private vulnerability reporting" in seguranca.lower()


def test_compose_nao_tem_senha_padrao():
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD:-" not in compose
    assert "POSTGRES_PASSWORD:?" in compose
