"""Erros de domínio do Bot Oráculo.

Separar erros de negócio de erros técnicos permite que o bot e a API traduzam
cada caso para a resposta correta (mensagem ao usuário vs. 500 + log).
"""

from __future__ import annotations


class OraculoError(Exception):
    """Raiz de todos os erros previstos do sistema."""


class BusinessRuleError(OraculoError):
    """Violação de uma regra de negócio catalogada (`RN-xxx`)."""

    regra: str = "RN-000"


class PermissaoNegadaError(BusinessRuleError):
    """RN-008 — o cargo do autor não autoriza a ação solicitada."""

    regra = "RN-008"

    def __init__(self, acao: str, cargo_atual: str, cargo_minimo: str) -> None:
        self.acao = acao
        self.cargo_atual = cargo_atual
        self.cargo_minimo = cargo_minimo
        super().__init__(
            f"Ação '{acao}' exige cargo mínimo '{cargo_minimo}'; autor possui '{cargo_atual}'."
        )


class MotivoObrigatorioError(BusinessRuleError):
    """RN-005 — toda movimentação de XP exige motivo registrável."""

    regra = "RN-005"

    def __init__(self) -> None:
        super().__init__("O motivo é obrigatório em qualquer movimentação de XP (RN-005).")


class QuantidadeInvalidaError(BusinessRuleError):
    """RF-003 — quantidade de XP precisa ser um inteiro positivo."""

    regra = "RF-003"

    def __init__(self, quantidade: int) -> None:
        self.quantidade = quantidade
        super().__init__(f"Quantidade de XP inválida: {quantidade}. Informe um inteiro positivo.")


class SaldoInalteradoError(BusinessRuleError):
    """A operação não alteraria o saldo (ex.: remover XP de quem tem zero)."""

    regra = "RF-003"

    def __init__(self, nome: str, saldo: int) -> None:
        super().__init__(f"Nenhuma alteração de XP para {nome} (saldo atual: {saldo}).")


class AutorNaoIdentificadoError(BusinessRuleError):
    """RN-004 — movimentação sem autor fora do contexto de automação."""

    regra = "RN-004"

    def __init__(self, acao: str) -> None:
        super().__init__(
            f"Ação '{acao}' exige autor identificado; use origem=SISTEMA para automações."
        )


class XpSomenteLeituraError(BusinessRuleError):
    """O XP é espelhado de uma origem externa e não pode ser alterado aqui."""

    regra = "RF-003"

    def __init__(self) -> None:
        super().__init__(
            "O XP é sincronizado a partir da plataforma do clube e não pode ser "
            "alterado pelo bot. Ajuste o valor na plataforma — a mudança aparece "
            "aqui na próxima sincronização."
        )


class SaldoDracmasInsuficienteError(BusinessRuleError):
    """`Institucional/COMUNIDADE_E_CLUBE.md` Art. 3º §1º / Art. 4º §1º —
    sem saldo para o ingresso/débito."""

    regra = "DRACMAS.md"

    def __init__(self, saldo_atual: int, valor_necessario: int) -> None:
        self.saldo_atual = saldo_atual
        self.valor_necessario = valor_necessario
        super().__init__(
            f"Saldo insuficiente: {saldo_atual} Dracmas disponíveis, "
            f"{valor_necessario} necessários."
        )


class ContaDracmasSuspensaError(BusinessRuleError):
    """`Institucional/DRACMAS.md` §4 — conta suspensa por saldo negativo não
    movimenta até reversão manual."""

    regra = "DRACMAS.md §4"

    def __init__(self, discord_id: int) -> None:
        self.discord_id = discord_id
        super().__init__(
            f"Conta de Dracmas de {discord_id} está suspensa (saldo negativo) — reversão "
            "é sempre manual, mediante decisão administrativa (DRACMAS.md §4)."
        )


class QuantidadeDracmasInvalidaError(BusinessRuleError):
    """Valor de movimentação de Dracmas precisa ser um inteiro positivo diferente de zero."""

    regra = "DRACMAS.md"

    def __init__(self, valor: int) -> None:
        self.valor = valor
        super().__init__(f"Valor de Dracmas inválido: {valor}. Informe um inteiro positivo.")


class MotivoDracmasObrigatorioError(BusinessRuleError):
    """`Institucional/DRACMAS.md` §3 — toda movimentação exige origem/motivo identificável."""

    regra = "DRACMAS.md §3"

    def __init__(self) -> None:
        super().__init__(
            "O motivo é obrigatório em qualquer movimentação de Dracmas (DRACMAS.md §3)."
        )


class VinculoJaSolicitadoError(BusinessRuleError):
    """RN-016 — já existe verificação em andamento, ou já está vinculado."""

    regra = "RN-016"


class CodigoInvalidoOuExpiradoError(BusinessRuleError):
    """RN-016 — código incorreto, expirado, ou sem solicitação pendente."""

    regra = "RN-016"


class ConflitoDeVinculoError(BusinessRuleError):
    """RN-016 — a conta Discord já tem registro no bot; precisa de Administrador."""

    regra = "RN-016"


class LimiteDePerguntasError(BusinessRuleError):
    """RN-017 — teto de perguntas por hora atingido (freio de custo)."""

    regra = "RN-017"

    def __init__(self, limite: int) -> None:
        self.limite = limite
        super().__init__(
            f"Você já fez {limite} perguntas nesta hora. Espere um pouco antes da próxima."
        )


class PerguntaVaziaError(BusinessRuleError):
    """RN-017 — pergunta sem conteúdo utilizável."""

    regra = "RN-017"

    def __init__(self) -> None:
        super().__init__("Faça uma pergunta — não consigo responder a um texto vazio.")


class RecursoNaoEncontradoError(OraculoError):
    """Entidade referenciada (membro, reunião, evento) não existe."""

    def __init__(self, recurso: str, identificador: object) -> None:
        self.recurso = recurso
        self.identificador = identificador
        super().__init__(f"{recurso} não encontrado: {identificador!r}")


class IntegracaoIndisponivelError(OraculoError):
    """RN-009 — dependência externa (ex.: Google Agenda) indisponível."""

    def __init__(self, servico: str, detalhe: str = "") -> None:
        self.servico = servico
        super().__init__(f"Integração indisponível: {servico}. {detalhe}".strip())


class AssinaturaInvalidaError(OraculoError):
    """TD-003 — webhook recebido sem assinatura HMAC válida."""

    def __init__(self, detalhe: str = "assinatura ausente ou incorreta") -> None:
        super().__init__(f"Webhook rejeitado: {detalhe}.")
