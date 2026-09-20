"""Corpus do regulamento TYTO — RN-017."""

from __future__ import annotations

from oraculo.config import Settings
from oraculo.integrations.regras_corpus import LIMITE_BYTES_ARQUIVO, carregar_corpus


def _cfg(diretorio) -> Settings:
    return Settings(_env_file=None, regras_dir=diretorio)


def test_carrega_os_md_do_diretorio(tmp_path):
    (tmp_path / "XP.md").write_text("Art. 2º — patentes", encoding="utf-8")
    (tmp_path / "DRACMAS.md").write_text("§2 — movimentações", encoding="utf-8")

    corpus = carregar_corpus(_cfg(tmp_path))

    assert corpus.disponivel
    assert corpus.documentos == ("DRACMAS.md", "XP.md"), "ordem estável para o cache"
    assert "Art. 2º — patentes" in corpus.texto
    assert '<documento nome="XP.md">' in corpus.texto


def test_ordem_e_estavel_entre_carregamentos(tmp_path):
    for nome in ("b.md", "a.md", "c.md"):
        (tmp_path / nome).write_text(nome, encoding="utf-8")

    assert carregar_corpus(_cfg(tmp_path)).texto == carregar_corpus(_cfg(tmp_path)).texto


def test_subdiretorios_entram(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "MERCADOR.md").write_text("Art. 4º", encoding="utf-8")

    corpus = carregar_corpus(_cfg(tmp_path))

    assert corpus.documentos == ("sub/MERCADOR.md",)


def test_sem_diretorio_configurado_fica_vazio():
    corpus = carregar_corpus(Settings(_env_file=None, regras_dir=None))

    assert not corpus.disponivel
    assert corpus.documentos == ()


def test_diretorio_inexistente_nao_derruba(tmp_path):
    corpus = carregar_corpus(_cfg(tmp_path / "nao-existe"))

    assert not corpus.disponivel


def test_ignora_arquivo_grande_demais(tmp_path):
    (tmp_path / "ok.md").write_text("regra", encoding="utf-8")
    (tmp_path / "dump.md").write_text("x" * (LIMITE_BYTES_ARQUIVO + 10), encoding="utf-8")

    corpus = carregar_corpus(_cfg(tmp_path))

    assert corpus.documentos == ("ok.md",)


def test_ignora_arquivo_vazio_e_nao_md(tmp_path):
    (tmp_path / "ok.md").write_text("regra", encoding="utf-8")
    (tmp_path / "vazio.md").write_text("   ", encoding="utf-8")
    (tmp_path / "leiame.txt").write_text("não é markdown", encoding="utf-8")

    corpus = carregar_corpus(_cfg(tmp_path))

    assert corpus.documentos == ("ok.md",)
