"""O Dockerfile só pode copiar o que o .dockerignore deixa entrar no contexto.

Um `COPY` de caminho ignorado não falha em teste nenhum e não falha localmente:
falha no build do deploy, em segundos, com o bot fora do ar. Foi assim que a
cópia de `docs/regras-tyto` (RN-017) derrubou o build no Railway.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


# Subconjunto deliberado da sintaxe do .dockerignore: prefixo de diretório e
# igualdade de caminho. Basta para pegar o erro que nos custou um deploy, e é
# simples o bastante para ninguém precisar depurar o próprio teste.
def _padroes_de_exclusao() -> list[str]:
    linhas = (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
    padroes = []
    for linha in linhas:
        limpa = linha.strip()
        if not limpa or limpa.startswith("#") or limpa.startswith("!"):
            continue
        padroes.append(limpa.rstrip("/"))
    return padroes


def _origens_copiadas() -> list[str]:
    origens: list[str] = []
    for linha in (RAIZ / "Dockerfile").read_text(encoding="utf-8").splitlines():
        limpa = linha.strip()
        if not re.match(r"^COPY\s", limpa, flags=re.IGNORECASE):
            continue
        argumentos = [parte for parte in limpa.split()[1:] if not parte.startswith("--")]
        if "--from=" in limpa:
            continue  # vem de outro estágio, não do contexto
        origens.extend(argumentos[:-1])  # o último argumento é o destino
    return origens


def _esta_ignorado(origem: str, padroes: list[str]) -> str | None:
    for padrao in padroes:
        if "*" in padrao or "?" in padrao:
            continue  # curinga: fora do subconjunto checado aqui
        if origem == padrao or origem.startswith(f"{padrao}/"):
            return padrao
    return None


def test_dockerfile_nao_copia_caminho_ignorado():
    padroes = _padroes_de_exclusao()

    for origem in _origens_copiadas():
        padrao = _esta_ignorado(origem, padroes)
        assert padrao is None, (
            f"Dockerfile copia {origem!r}, mas o .dockerignore exclui {padrao!r}. "
            "O build quebra no deploy, não aqui."
        )


def test_dockerfile_so_copia_caminho_existente():
    for origem in _origens_copiadas():
        if "*" in origem or "?" in origem:
            continue
        assert (RAIZ / origem).exists(), (
            f"Dockerfile copia {origem!r}, que não existe no repositório."
        )


def test_regulamento_tyto_entra_na_imagem():
    """RN-017: sem esta pasta o /perguntar sobe sem base de regras nenhuma."""
    assert "docs/regras-tyto" in _origens_copiadas()
