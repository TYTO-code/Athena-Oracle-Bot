"""Hierarquia do Clube TYTO — TD-007, resolvida pela unificação com `Institucional/XP.md`.

A Carta Institucional (Art. VIII) separa a posição de um membro em eixos
**independentes**, e este módulo modela exatamente isso:

1. **Patente** (`Institucional/XP.md` Art. 2º) — 17 patamares, de Neófito a
   Omni, determinados **exclusivamente** pelo XP acumulado (RN-002). É
   irrevogável: nada rebaixa uma patente (XP.md Art. 1º §3º).
2. **Cargo institucional** — `Conselheiro` (eleito, Carta Art. III/IV), e a
   função técnica de `Administrador` deste bot. Nunca vêm do XP: são
   concedidos e revogados por ato auditado de um Administrador.

"Membro" deixou de ser um degrau da escala: é a filiação ao Clube — quem tem
um registro `Membro` é membro; quem é só da Comunidade é `Aldeao` (RN-011).

RN-001 — cargo único vale para a **patente**: um membro tem exatamente uma
patente ativa, e no Discord só o papel dela. Cargos institucionais são papéis
à parte, acumuláveis com qualquer patente.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Patente:
    """Um patamar da escala oficial de patentes (XP.md Art. 2º)."""

    slug: str
    """Identificador estável usado no banco e nas permissões."""

    nome: str
    """Nome exibido ao usuário e esperado como nome do papel no Discord."""

    ordem: int
    """Posição na escala, de 1 (Neófito) a 17 (Omni)."""

    xp_minimo: int
    """Limiar de XP do patamar (XP.md Art. 2º)."""

    def __ge__(self, outra: Patente) -> bool:
        return self.ordem >= outra.ordem

    def __gt__(self, outra: Patente) -> bool:
        return self.ordem > outra.ordem

    def __le__(self, outra: Patente) -> bool:
        return self.ordem <= outra.ordem

    def __lt__(self, outra: Patente) -> bool:
        return self.ordem < outra.ordem

    def __str__(self) -> str:  # pragma: no cover - representação trivial
        return self.nome


# REGRA ÚNICA DA ESCALA (XP.md Art. 2º §3º): Neófito começa em 0 XP; Escudeiro exige
# `XP_BASE`; e cada patamar seguinte exige exatamente `XP_MULTIPLICADOR` vezes o XP do anterior
# (`xp_minimo(n) = XP_BASE × XP_MULTIPLICADOR^(n − 2)`, n ≥ 2). É a mesma regra de
# `TYTO.club/src/constants/tiers.ts` e do backend, para que bot e plataforma nunca discordem da
# patente de um mesmo XP. Mudar a escala vale só dali em diante — nunca rebaixa quem já alcançou o
# patamar (Art. 1º §3º): o bot só promove (`PromocaoService`) e guarda a patente no banco.
XP_BASE = 400
XP_MULTIPLICADOR = 4


def xp_minimo(ordem: int) -> int:
    """Limiar de XP do patamar `ordem` (1 = Neófito), pela regra única da escala."""
    return 0 if ordem <= 1 else XP_BASE * XP_MULTIPLICADOR ** (ordem - 2)


NEOFITO = Patente("neofito", "Neófito", 1, xp_minimo(1))
ESCUDEIRO = Patente("escudeiro", "Escudeiro", 2, xp_minimo(2))
ARMEIRO = Patente("armeiro", "Armeiro", 3, xp_minimo(3))
VETERANO = Patente("veterano", "Veterano", 4, xp_minimo(4))
MESTRE_DE_ARMAS = Patente("mestre-de-armas", "Mestre de Armas", 5, xp_minimo(5))
DESAFIANTE_LEGIONARIO = Patente("desafiante-legionario", "Desafiante Legionário", 6, xp_minimo(6))
OFICIAL = Patente("oficial", "Oficial", 7, xp_minimo(7))
CENTURIAO = Patente("centuriao", "Centurião", 8, xp_minimo(8))
COMANDANTE = Patente("comandante", "Comandante", 9, xp_minimo(9))
DOM = Patente("dom", "Dom", 10, xp_minimo(10))
LORDE = Patente("lorde", "Lorde", 11, xp_minimo(11))
SENHOR_DA_GUERRA = Patente("senhor-da-guerra", "Senhor da Guerra", 12, xp_minimo(12))
SUSERANO = Patente("suserano", "Suserano", 13, xp_minimo(13))
MONARCA = Patente("monarca", "Monarca", 14, xp_minimo(14))
DOMINADOR = Patente("dominador", "Dominador", 15, xp_minimo(15))
RENOVEK = Patente("renovek", "Renovek", 16, xp_minimo(16))
OMNI = Patente("omni", "Omni", 17, xp_minimo(17))

PATENTES: tuple[Patente, ...] = (
    NEOFITO,
    ESCUDEIRO,
    ARMEIRO,
    VETERANO,
    MESTRE_DE_ARMAS,
    DESAFIANTE_LEGIONARIO,
    OFICIAL,
    CENTURIAO,
    COMANDANTE,
    DOM,
    LORDE,
    SENHOR_DA_GUERRA,
    SUSERANO,
    MONARCA,
    DOMINADOR,
    RENOVEK,
    OMNI,
)
"""Escala completa, sempre ordenada do menor para o maior patamar."""

PATENTE_INICIAL: Patente = NEOFITO

_POR_SLUG: dict[str, Patente] = {p.slug: p for p in PATENTES}
_POR_NOME: dict[str, Patente] = {p.nome.casefold(): p for p in PATENTES}


def patente_por_slug(slug: str) -> Patente:
    """Resolve uma patente pelo slug (ou pelo nome exibido, por conveniência)."""
    chave = slug.strip().casefold()
    patente = _POR_SLUG.get(chave) or _POR_NOME.get(chave)
    if patente is None:
        validos = ", ".join(p.slug for p in PATENTES)
        raise KeyError(f"Patente desconhecida: {slug!r}. Válidas: {validos}.")
    return patente


def patente_para_xp(xp: int) -> Patente:
    """RN-002 — maior patente alcançada com `xp` acumulado (XP.md Art. 1º §3º)."""
    alcancada = PATENTE_INICIAL
    for patente in PATENTES:
        if xp >= patente.xp_minimo:
            alcancada = patente
    return alcancada


def proxima_patente(patente: Patente) -> Patente | None:
    """Próximo patamar acima de `patente`, ou `None` em Omni (RF-002)."""
    return PATENTES[patente.ordem] if patente.ordem < len(PATENTES) else None


def xp_faltante(xp_atual: int, patente_atual: Patente | None = None) -> int | None:
    """XP restante até o próximo patamar, ou `None` se já está no topo (RF-002)."""
    seguinte = proxima_patente(patente_atual or patente_para_xp(xp_atual))
    if seguinte is None:
        return None
    return max(0, seguinte.xp_minimo - xp_atual)


def normalizar_nome_papel(nome: str) -> str:
    """Forma canônica de um nome de papel do Discord, para comparar patentes e cargos.

    Os papéis do servidor costumam ter enfeites no nome (``🛡️ Escudeiro``,
    ``⚔️│Mestre de Armas``, ``【Neófito】``, ``Omni ⭐``). Esta função descarta
    tudo o que não é letra ou número (emojis, símbolos, separadores, seletores de
    variação, juntadores de largura zero), remove acentos, uniformiza letras
    estilizadas (``𝐎𝐦𝐧𝐢`` → ``omni``), colapsa espaços e ignora maiúsculas.

    Só a comparação usa essa forma: o nome que o bot **cria ou exibe** continua
    sendo o canônico (`Patente.nome`).
    """
    decomposto = unicodedata.normalize("NFKD", nome)
    sem_acentos = "".join(c for c in decomposto if not unicodedata.combining(c))
    so_texto = "".join(c if c.isalnum() else " " for c in sem_acentos)
    return " ".join(so_texto.split()).casefold()


def nomes_de_patentes_discord() -> frozenset[str]:
    """Papéis de patente gerenciados pelo bot no Discord.

    RN-001 / RN-003 / TD-005 — a sincronização remove **todos** estes nomes do
    membro antes de atribuir a patente nova, evitando acúmulo.
    """
    return frozenset(p.nome for p in PATENTES)


_POR_NOME_NORMALIZADO: dict[str, Patente] = {normalizar_nome_papel(p.nome): p for p in PATENTES}


def patente_do_papel(nome_do_papel: str) -> Patente | None:
    """Patente que um papel do Discord representa, ignorando emojis e enfeites do nome."""
    return _POR_NOME_NORMALIZADO.get(normalizar_nome_papel(nome_do_papel))


class CargoInstitucional(StrEnum):
    """Cargos fora da escala de XP — acumuláveis com qualquer patente.

    Não há rebaixamento por XP nem promoção automática: concessão e revogação
    acontecem na plataforma TYTO.club e são apenas espelhadas pelo bot (RN-021).
    """

    CONSELHEIRO = "conselheiro"
    """Conselheiro do Conselho Régio (Carta Art. III/IV) — eleito."""

    ADMINISTRADOR = "administrador"
    """Função técnica do bot: segurança, logs, backup e conformidade."""

    @property
    def nome(self) -> str:
        """Nome exibido e esperado como nome do papel no Discord."""
        return self.value.capitalize()


def nomes_de_cargos_institucionais_discord() -> frozenset[str]:
    """Papéis institucionais gerenciados pelo bot no Discord (um por cargo)."""
    return frozenset(c.nome for c in CargoInstitucional)


@dataclass(frozen=True, slots=True)
class Perfil:
    """Posição completa de um membro nos eixos da Carta Art. VIII."""

    patente: Patente
    conselheiro: bool = False
    administrador: bool = False

    def possui(self, cargo: CargoInstitucional) -> bool:
        if cargo is CargoInstitucional.CONSELHEIRO:
            return self.conselheiro
        return self.administrador

    @property
    def cargos_institucionais(self) -> tuple[CargoInstitucional, ...]:
        return tuple(c for c in CargoInstitucional if self.possui(c))

    def descricao(self) -> str:
        """Ex.: "Oficial" ou "Comandante · Conselheiro"."""
        return " · ".join([self.patente.nome, *(c.nome for c in self.cargos_institucionais)])


def pelo_menos(patente: Patente, minima: Patente) -> bool:
    """Comparação canônica do tipo "Oficial+" (RN-008)."""
    return patente.ordem >= minima.ordem
