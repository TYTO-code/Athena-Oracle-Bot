"""Montagem do banner de boas-vindas: função pura, sem Discord envolvido."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from oraculo.bot.welcome_image import _LADO_SAIDA, FUNDO_PADRAO, montar_banner


def _png_bytes(cor: tuple[int, int, int], lado: int) -> bytes:
    imagem = Image.new("RGB", (lado, lado), cor)
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


@pytest.fixture
def fundo_sintetico(tmp_path):
    caminho = tmp_path / "fundo.png"
    # Retangular de propósito: confere que o recorte ao quadrado funciona.
    Image.new("RGB", (900, 500), (120, 10, 200)).save(caminho)
    return caminho


def test_fundo_padrao_do_repositorio_existe_e_abre():
    assert FUNDO_PADRAO.is_file()
    with Image.open(FUNDO_PADRAO) as imagem:
        imagem.verify()


def test_monta_banner_do_tamanho_esperado_e_e_png_valido(fundo_sintetico):
    avatar = _png_bytes((10, 200, 10), 256)

    banner = montar_banner(avatar, fundo=fundo_sintetico)

    with Image.open(io.BytesIO(banner)) as imagem:
        imagem.verify()
    with Image.open(io.BytesIO(banner)) as imagem:
        assert imagem.size == (_LADO_SAIDA, _LADO_SAIDA)
        assert imagem.format == "PNG"


def test_e_deterministico(fundo_sintetico):
    avatar = _png_bytes((200, 50, 50), 128)

    primeiro = montar_banner(avatar, fundo=fundo_sintetico)
    segundo = montar_banner(avatar, fundo=fundo_sintetico)

    assert primeiro == segundo


def test_avatar_menor_ou_maior_que_o_padrao_nao_quebra(fundo_sintetico):
    pequeno = _png_bytes((5, 5, 5), 32)
    grande = _png_bytes((250, 250, 250), 1024)

    assert montar_banner(pequeno, fundo=fundo_sintetico)
    assert montar_banner(grande, fundo=fundo_sintetico)
