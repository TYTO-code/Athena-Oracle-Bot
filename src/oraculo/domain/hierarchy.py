"""Catálogo da hierarquia real do Clube TYTO.

TD-004 — substitui os níveis arbitrários do legado ("Novice", etc.) pela
estrutura oficial `Membro → Cavalaria → Lorde → Conselheiro → Administrador`.

RN-001 — um membro possui **apenas um** cargo de hierarquia ativo. A ordem
(`ordem`) é a única fonte de verdade para comparações do tipo "Cavalaria+".

RN-002 — a progressão é derivada do XP acumulado por `cargo_para_xp`.

> **Premissa a validar com o Clube TYTO:** os limiares de XP abaixo não constam
> do Documento Único. São valores iniciais coerentes com a progressão descrita
> e podem ser ajustados sem tocar em nenhuma outra camada — apenas esta tabela.
> `Administrador` é intencionalmente inalcançável por XP (atribuição manual).
"""

from __future__ import annotations

from dataclasses import dataclass

XP_INALCANCAVEL = None
"""Marcador de cargo que não é obtido por progressão automática (RN-002)."""


@dataclass(frozen=True, slots=True)
class Cargo:
    """Um cargo da hierarquia TYTO."""

    slug: str
    """Identificador estável usado no banco e nas permissões."""

    nome: str
    """Nome exibido ao usuário e esperado como nome do cargo no Discord."""

    ordem: int
    """Posição na hierarquia; maior valor = mais autoridade (RN-008)."""

    xp_minimo: int | None
    """XP necessário para alcançar o cargo, ou `None` se não for automático."""

    descricao: str = ""

    @property
    def automatico(self) -> bool:
        """True quando o cargo pode ser concedido por progressão de XP."""
        return self.xp_minimo is not None

    def __ge__(self, outro: Cargo) -> bool:
        return self.ordem >= outro.ordem

    def __gt__(self, outro: Cargo) -> bool:
        return self.ordem > outro.ordem

    def __le__(self, outro: Cargo) -> bool:
        return self.ordem <= outro.ordem

    def __lt__(self, outro: Cargo) -> bool:
        return self.ordem < outro.ordem

    def __str__(self) -> str:  # pragma: no cover - representação trivial
        return self.nome


MEMBRO = Cargo(
    slug="membro",
    nome="Membro",
    ordem=0,
    xp_minimo=0,
    descricao="Cargo de entrada; consulta perfil, ranking e responde RSVP.",
)
CAVALARIA = Cargo(
    slug="cavalaria",
    nome="Cavalaria",
    ordem=1,
    xp_minimo=500,
    descricao="Pode criar e gerir reuniões (RN-006).",
)
LORDE = Cargo(
    slug="lorde",
    nome="Lorde",
    ordem=2,
    xp_minimo=1_500,
    descricao="Pode criar e gerir eventos oficiais (RN-007).",
)
CONSELHEIRO = Cargo(
    slug="conselheiro",
    nome="Conselheiro",
    ordem=3,
    xp_minimo=3_500,
    descricao="Pode conceder/remover XP e auditar histórico (RN-004).",
)
ADMINISTRADOR = Cargo(
    slug="administrador",
    nome="Administrador",
    ordem=4,
    xp_minimo=XP_INALCANCAVEL,
    descricao="Segurança, logs, backup e conformidade; atribuição manual.",
)

HIERARQUIA: tuple[Cargo, ...] = (MEMBRO, CAVALARIA, LORDE, CONSELHEIRO, ADMINISTRADOR)
"""Hierarquia completa, sempre ordenada do menor para o maior (RN-001)."""

CARGO_INICIAL: Cargo = MEMBRO

_POR_SLUG: dict[str, Cargo] = {c.slug: c for c in HIERARQUIA}
_POR_NOME: dict[str, Cargo] = {c.nome.casefold(): c for c in HIERARQUIA}


def cargo_por_slug(slug: str) -> Cargo:
    """Resolve um cargo pelo slug (ou pelo nome exibido, por conveniência)."""
    chave = slug.strip().casefold()
    cargo = _POR_SLUG.get(chave) or _POR_NOME.get(chave)
    if cargo is None:
        validos = ", ".join(c.slug for c in HIERARQUIA)
        raise KeyError(f"Cargo desconhecido: {slug!r}. Válidos: {validos}.")
    return cargo


def cargo_para_xp(xp: int) -> Cargo:
    """RN-002 — maior cargo automático alcançado com `xp` acumulado.

    Cargos não automáticos (Administrador) nunca são retornados aqui: eles não
    fazem parte da progressão e devem ser atribuídos manualmente.
    """
    if xp < 0:
        return CARGO_INICIAL
    alcancado = CARGO_INICIAL
    for cargo in HIERARQUIA:
        if cargo.xp_minimo is not None and xp >= cargo.xp_minimo:
            alcancado = cargo
    return alcancado


def proximo_cargo(cargo: Cargo) -> Cargo | None:
    """Próximo cargo automático acima de `cargo`, ou `None` no topo (RF-002)."""
    for candidato in HIERARQUIA:
        if candidato.ordem > cargo.ordem and candidato.automatico:
            return candidato
    return None


def xp_faltante(xp_atual: int, cargo_atual: Cargo | None = None) -> int | None:
    """XP restante até a próxima promoção, ou `None` se já está no topo (RF-002)."""
    atual = cargo_atual or cargo_para_xp(xp_atual)
    seguinte = proximo_cargo(atual)
    if seguinte is None or seguinte.xp_minimo is None:
        return None
    return max(0, seguinte.xp_minimo - xp_atual)


def nomes_de_cargos_discord() -> frozenset[str]:
    """Nomes de cargos TYTO gerenciados pelo bot no Discord.

    RN-001 / RN-003 / TD-005 — a sincronização remove **todos** estes nomes do
    membro antes de atribuir o novo cargo, evitando acúmulo.
    """
    return frozenset(c.nome for c in HIERARQUIA)


def pelo_menos(cargo: Cargo, minimo: Cargo) -> bool:
    """Comparação canônica do tipo "Cavalaria+" (RN-008)."""
    return cargo.ordem >= minimo.ordem
