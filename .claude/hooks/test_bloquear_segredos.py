"""Testes do hook bloquear-segredos.py (rodar com: python3 -m unittest .claude/hooks/test_bloquear_segredos.py)."""

import importlib.util
import pathlib
import unittest

CAMINHO = pathlib.Path(__file__).with_name("bloquear-segredos.py")
spec = importlib.util.spec_from_file_location("bloquear_segredos", CAMINHO)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def diff(arquivo: str, *linhas: str) -> str:
    return f"+++ b/{arquivo}\n" + "\n".join("+" + linha for linha in linhas)


class AnalisarTest(unittest.TestCase):
    def test_commit_limpo_passa(self):
        d = diff("src/a.py", "x = 1", "# senha vem do ambiente: os.environ['SENHA']")
        self.assertEqual(mod.analisar(d, ["src/a.py"]), [])

    def test_arquivos_proibidos(self):
        achados = mod.analisar("", [".env", "src/.env", "keys/server.pem", "firebase-adminsdk-x.json", ".env.example"])
        textos = " | ".join(achados)
        self.assertIn(".env: arquivo .env", textos)
        self.assertIn("src/.env", textos)
        self.assertIn("server.pem", textos)
        self.assertIn("firebase-adminsdk-x.json", textos)
        self.assertFalse([a for a in achados if a.startswith(".env.example")])

    def test_chave_privada_e_tokens(self):
        d = diff(
            "x.txt",
            "-----BEGIN " + "PRIVATE KEY-----",  # montado em partes: o repo não pode conter a chave por extenso
            "aws = AKIA" + "ABCDEFGHIJKLMNOP",
            "gh = ghp_" + "a" * 36,
            "slack = xoxb-" + "1234567890-abcdef",
        )
        achados = " | ".join(mod.analisar(d, []))
        for tipo in ("chave privada", "AWS", "GitHub", "Slack"):
            self.assertIn(tipo, achados)

    def test_atribuicao_literal_longa_e_placeholder(self):
        ruim = diff("c.py", 'api_key = "9f8e7d6c5b4a39281716"')
        self.assertTrue(mod.analisar(ruim, []))
        for ok in ('api_key = "your-api-key-here-1234"', 'password = "troque-esta-senha-agora"', "token = os.environ['TOKEN']", 'secret = "${SEGREDO_DO_AMBIENTE}"'):
            self.assertEqual(mod.analisar(diff("c.py", ok), []), [], ok)

    def test_email_pessoal(self):
        achados = mod.analisar(diff("README.md", "contato: fulana.silva@gmail.com"), [])
        self.assertTrue(any("e-mail pessoal" in a for a in achados))
        self.assertFalse(mod.analisar(diff("README.md", "123+user@users.noreply.github.com"), []))
        self.assertFalse(mod.analisar(diff("README.md", "exemplo@gmail.com"), []))

    def test_marca_de_excecao_na_linha(self):
        d = diff("doc.md", "autor: pessoa@outlook.com <!-- allow-pessoal -->")
        self.assertEqual(mod.analisar(d, []), [])

    def test_lockfile_e_binarios_sao_ignorados(self):
        d = diff("package-lock.json", 'api_key = "9f8e7d6c5b4a39281716aa"')
        self.assertEqual(mod.analisar(d, []), [])

    def test_saida_nunca_traz_o_valor(self):
        valor = "9f8e7d6c5b4a39281716"
        achados = " ".join(mod.analisar(diff("c.py", f'api_key = "{valor}"'), []))
        self.assertNotIn(valor, achados)


if __name__ == "__main__":
    unittest.main()
