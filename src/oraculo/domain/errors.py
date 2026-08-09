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
