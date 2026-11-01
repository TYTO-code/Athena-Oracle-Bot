"""Monta o banner de boas-vindas: avatar de quem entrou sobre o fundo da TYTO.

Puramente estético — não lê nem escreve dado algum da plataforma TYTO.club (RN-021 não se aplica:
não há XP, patente, Dracmas nem vínculo envolvido, só uma imagem postada no próprio Discord). Função
pura o bastante para testar sem subir bot nem Discord: recebe bytes de avatar já baixados pelo cog e
devolve bytes de PNG prontos para enviar.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

FUNDO_PADRAO = Path(__file__).resolve().parent.parent / "assets" / "boas_vindas_fundo.png"

# Retângulo "de monitor" (16:9) em vez de um quadrado — mais parecido com um banner de verdade.
_LARGURA_SAIDA = 1280
_ALTURA_SAIDA = 720
_DIAMETRO_AVATAR = 360
_ESPESSURA_ANEL = 12


def _mascara_circular(diametro: int) -> Image.Image:
    mascara = Image.new("L", (diametro, diametro), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, diametro - 1, diametro - 1), fill=255)
    return mascara


def montar_banner(avatar_bytes: bytes, *, fundo: Path = FUNDO_PADRAO) -> bytes:
    """Fundo da TYTO recortado num retângulo 16:9 ("de monitor") + avatar circular centralizado,
    com um anel branco separando um do outro. Devolve os bytes de um PNG RGB, pronto para
    `discord.File`.
    """
    with Image.open(fundo) as imagem_fundo:
        fundo_rgba = imagem_fundo.convert("RGBA")

    largura_alvo, altura_alvo = _LARGURA_SAIDA, _ALTURA_SAIDA
    proporcao_alvo = largura_alvo / altura_alvo
    proporcao_fundo = fundo_rgba.width / fundo_rgba.height
    if proporcao_fundo > proporcao_alvo:
        # Fundo mais largo que o alvo: corta as laterais, mantém a altura inteira.
        nova_largura = round(fundo_rgba.height * proporcao_alvo)
        esquerda = (fundo_rgba.width - nova_largura) // 2
        caixa = (esquerda, 0, esquerda + nova_largura, fundo_rgba.height)
    else:
        # Fundo mais alto (ou quadrado, como o nosso): corta topo/base, mantém a largura inteira.
        nova_altura = round(fundo_rgba.width / proporcao_alvo)
        topo = (fundo_rgba.height - nova_altura) // 2
        caixa = (0, topo, fundo_rgba.width, topo + nova_altura)
    fundo_rgba = fundo_rgba.crop(caixa)
    fundo_rgba = fundo_rgba.resize((largura_alvo, altura_alvo), Image.Resampling.LANCZOS)

    tamanho_avatar = (_DIAMETRO_AVATAR, _DIAMETRO_AVATAR)
    with Image.open(io.BytesIO(avatar_bytes)) as imagem_avatar:
        avatar = imagem_avatar.convert("RGBA").resize(tamanho_avatar, Image.Resampling.LANCZOS)

    diametro_anel = _DIAMETRO_AVATAR + _ESPESSURA_ANEL * 2
    anel = Image.new("RGBA", (diametro_anel, diametro_anel), (0, 0, 0, 0))
    cor_anel = (255, 255, 255, 235)
    ImageDraw.Draw(anel).ellipse((0, 0, diametro_anel - 1, diametro_anel - 1), fill=cor_anel)
    posicao_anel = ((largura_alvo - diametro_anel) // 2, (altura_alvo - diametro_anel) // 2)
    fundo_rgba.alpha_composite(anel, posicao_anel)

    posicao_avatar = ((largura_alvo - _DIAMETRO_AVATAR) // 2, (altura_alvo - _DIAMETRO_AVATAR) // 2)
    fundo_rgba.paste(avatar, posicao_avatar, _mascara_circular(_DIAMETRO_AVATAR))

    saida = io.BytesIO()
    fundo_rgba.convert("RGB").save(saida, format="PNG")
    return saida.getvalue()
