"""RN-021 — o bot só consulta a plataforma. Trava estrutural, não de comportamento.

Os testes de comportamento provam que os comandos de escrita sumiram; estes
provam que ninguém reintroduziu um caminho de escrita no código que fala com o
Firebase ou com a API da plataforma.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "oraculo"

# Métodos de escrita do cliente Firestore / de qualquer cliente HTTP.
ESCRITA = re.compile(
    r"\.(set|update|delete|create|add|commit|batch|transaction|run_transaction|"
    r"post|put|patch)\s*\("
)


def _codigo(caminho: Path) -> str:
    """Código sem comentários nem docstrings de uma linha, para não dar falso positivo."""
    return "\n".join(
        linha for linha in caminho.read_text().splitlines() if not linha.lstrip().startswith("#")
    )


def test_adaptador_do_firestore_nao_chama_nenhum_metodo_de_escrita():
    achados = ESCRITA.findall(_codigo(RAIZ / "integrations" / "plataforma.py"))
    assert achados == []


def test_nao_ha_cliente_da_api_de_economia_da_plataforma():
    """Os Dracmas do Clube vivem só na plataforma; o bot não os movimenta."""
    assert not (RAIZ / "integrations" / "economia_plataforma.py").exists()


def test_so_o_adaptador_de_plataforma_importa_o_firestore():
    donos = {
        str(p.relative_to(RAIZ))
        for p in RAIZ.rglob("*.py")
        if "google.cloud.firestore" in _codigo(p) or "firebase_admin" in _codigo(p)
    }
    assert donos <= {"integrations/plataforma.py", "integrations/projetos_db.py"}


def test_nao_ha_bootstrap_de_administrador_pelo_bot():
    """Administrador vem da plataforma (espelho), nunca de uma variável do bot."""
    from oraculo.config import Settings

    assert "bootstrap_admin_discord_id" not in Settings.model_fields
    assert not (RAIZ / "services" / "bootstrap_service.py").exists()
