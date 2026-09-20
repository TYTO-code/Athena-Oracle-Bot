"""Corpus do regulamento TYTO (`.md`) — RN-017.

Carrega os documentos institucionais de um diretório e os entrega como um bloco
único de texto, que vira o prefixo **estável** do prompt (ver `llm.py`: é ele
que fica em cache e é compartilhado por todas as perguntas de todos os membros).

Por que o regulamento inteiro em vez de busca por trechos: ele é pequeno perto
da janela de contexto, e pergunta sobre regra quase sempre cruza documentos
("quanto custa entrar na Comunidade e como isso afeta minha patente?"). Recortar
em pedaços e recuperar só os "mais parecidos" é justamente o modo de errar essas.
Se o corpus crescer a ponto de não caber, aí sim vale busca — não antes.

O conteúdo é lido uma vez e mantido em memória: são poucos arquivos, e reler a
cada pergunta só adicionaria I/O e variação no prefixo cacheado.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from oraculo.config import Settings, get_settings
from oraculo.logging_config import get_logger

log = get_logger(__name__)

LIMITE_BYTES_ARQUIVO = 512 * 1024
"""Teto por arquivo. Um `.md` maior que isso quase certamente não é regulamento
(dump, binário renomeado) e só encareceria o prompt."""


@dataclass(frozen=True, slots=True)
class Corpus:
    """Regulamento carregado, pronto para virar prefixo de prompt."""

    texto: str
    documentos: tuple[str, ...]

    @property
    def disponivel(self) -> bool:
        return bool(self.texto.strip())


CORPUS_VAZIO = Corpus(texto="", documentos=())


def carregar_corpus(settings: Settings | None = None) -> Corpus:
    """Lê os `.md` de `ORACULO_REGRAS_DIR`, em ordem estável por nome.

    Ordem alfabética não é estética: o prefixo do prompt só é reaproveitado em
    cache enquanto for byte a byte o mesmo, e a ordem de `iterdir()` não é
    garantida entre sistemas.
    """
    cfg = settings or get_settings()
    diretorio: Path | None = cfg.regras_dir
    if diretorio is None:
        return CORPUS_VAZIO

    caminho = Path(diretorio).expanduser()
    if not caminho.is_dir():
        log.warning("ORACULO_REGRAS_DIR não é um diretório acessível: %s", caminho)
        return CORPUS_VAZIO

    partes: list[str] = []
    nomes: list[str] = []
    for arquivo in sorted(caminho.rglob("*.md"), key=lambda p: str(p).casefold()):
        try:
            if arquivo.stat().st_size > LIMITE_BYTES_ARQUIVO:
                log.warning("Documento de regras ignorado (grande demais): %s", arquivo.name)
                continue
            conteudo = arquivo.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            log.warning("Não foi possível ler o documento de regras %s", arquivo.name)
            continue
        if not conteudo:
            continue
        nome = arquivo.relative_to(caminho).as_posix()
        nomes.append(nome)
        partes.append(f"<documento nome=\"{nome}\">\n{conteudo}\n</documento>")

    if not partes:
        log.warning("Nenhum documento de regras encontrado em %s", caminho)
        return CORPUS_VAZIO

    log.info("Regulamento TYTO carregado: %d documentos de %s", len(nomes), caminho)
    return Corpus(texto="\n\n".join(partes), documentos=tuple(nomes))
