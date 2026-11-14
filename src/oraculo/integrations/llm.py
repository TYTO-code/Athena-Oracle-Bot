"""Cliente do modelo de linguagem — RN-017.

Porta (`ClienteLLM`) + implementação sobre o SDK oficial da Anthropic. A porta
existe para que o serviço de perguntas seja testável sem gastar um centavo de
API — e, mais importante, para que os testes de segurança possam inspecionar
**exatamente** o que teria sido enviado ao modelo.

Montagem do prompt (a ordem importa para o cache):

1. `instrucoes` — persona e regras de resposta. Estável.
2. `corpus_regras` — o regulamento TYTO inteiro, com `cache_control`. Estável e
   **compartilhado entre todos os membros**: a pergunta de cada pessoa reaproveita
   o mesmo prefixo cacheado, o que derruba o custo da parte cara do prompt.
3. `contexto_usuario` — dados do projeto e a pergunta. Volátil, vai depois do
   ponto de corte do cache, porque muda a cada chamada.

O que **não** está aqui, de propósito: qualquer noção de permissão. Quando um
prompt chega neste módulo, a decisão de acesso já foi tomada e aplicada em
`pergunta_service.py` — este arquivo só sabe falar com o modelo.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from oraculo.config import Settings, get_settings
from oraculo.domain.custo_llm import UsoLLM
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Prompt:
    """O que será enviado ao modelo, já separado por estabilidade de cache."""

    instrucoes: str
    corpus_regras: str
    contexto_usuario: str


class ClienteLLM(Protocol):
    async def responder(self, prompt: Prompt) -> str: ...


#: Recebe o uso de cada resposta (tokens) para contar custo; `None` = não conta.
AoUsar = Callable[[UsoLLM], Awaitable[None]]
#: Recebe falhas (modelo, resultado) para o contador de chamadas.
AoFalhar = Callable[[str, str], None]


class ClienteAnthropic:
    """Implementação real. Uma chamada, sem streaming: o Discord só mostra a
    resposta pronta mesmo, e a interação adiada aguenta a espera."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        ao_usar: AoUsar | None = None,
        ao_falhar: AoFalhar | None = None,
    ) -> None:
        self._cfg = settings or get_settings()
        self._cliente: Any | None = None
        self._ao_usar = ao_usar
        self._ao_falhar = ao_falhar

    def _falhou(self, resultado: str) -> None:
        if self._ao_falhar is not None:
            self._ao_falhar(self._cfg.llm_model, resultado)

    def _conectar(self) -> Any:
        if self._cliente is not None:
            return self._cliente
        if not self._cfg.anthropic_api_key:
            raise IntegracaoIndisponivelError("LLM", "ORACULO_ANTHROPIC_API_KEY não definida.")
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - dependência declarada
            raise IntegracaoIndisponivelError("LLM", f"SDK anthropic ausente: {exc}") from exc

        self._cliente = AsyncAnthropic(
            api_key=self._cfg.anthropic_api_key, timeout=self._cfg.llm_timeout_segundos
        )
        return self._cliente

    def _blocos_de_sistema(self, prompt: Prompt) -> list[dict[str, Any]]:
        blocos: list[dict[str, Any]] = [{"type": "text", "text": prompt.instrucoes}]
        if prompt.corpus_regras.strip():
            blocos.append(
                {
                    "type": "text",
                    "text": prompt.corpus_regras,
                    # Ponto de corte do cache: tudo daqui para trás é reaproveitado
                    # entre perguntas de qualquer membro.
                    "cache_control": {"type": "ephemeral"},
                }
            )
        return blocos

    async def responder(self, prompt: Prompt) -> str:
        from anthropic import APITimeoutError

        cliente = self._conectar()
        try:
            resposta = await cliente.messages.create(
                model=self._cfg.llm_model,
                max_tokens=self._cfg.llm_max_tokens,
                system=self._blocos_de_sistema(prompt),
                messages=[{"role": "user", "content": prompt.contexto_usuario}],
            )
        except APITimeoutError as exc:
            self._falhou("timeout")
            log.warning("Modelo não respondeu em %ss", self._cfg.llm_timeout_segundos)
            raise IntegracaoIndisponivelError(
                "LLM",
                f"o modelo demorou mais de {self._cfg.llm_timeout_segundos:.0f}s para "
                "responder. Tente de novo em instantes.",
            ) from exc
        except Exception as exc:  # noqa: BLE001 — falha externa vira erro de integração
            self._falhou("erro")
            log.exception("Falha na chamada ao modelo")
            raise IntegracaoIndisponivelError("LLM", str(exc)) from exc

        # Toda resposta é cobrada, inclusive recusa e resposta vazia: o uso é contado antes.
        await self._contar_uso(resposta)

        if getattr(resposta, "stop_reason", None) == "refusal":
            raise IntegracaoIndisponivelError(
                "LLM", "o modelo recusou responder a esta solicitação."
            )

        texto = "\n".join(
            bloco.text for bloco in resposta.content if getattr(bloco, "type", None) == "text"
        ).strip()

        if not texto:
            raise IntegracaoIndisponivelError("LLM", "resposta vazia do modelo.")
        return texto

    async def _contar_uso(self, resposta: Any) -> None:
        uso = getattr(resposta, "usage", None)
        if uso is None:
            return
        registro = UsoLLM(
            modelo=str(getattr(resposta, "model", None) or self._cfg.llm_model),
            entrada=int(getattr(uso, "input_tokens", 0) or 0),
            saida=int(getattr(uso, "output_tokens", 0) or 0),
            cache_escrita=int(getattr(uso, "cache_creation_input_tokens", 0) or 0),
            cache_leitura=int(getattr(uso, "cache_read_input_tokens", 0) or 0),
        )
        log.info(
            "Pergunta respondida: entrada=%s cache_escrita=%s cache_leitura=%s saída=%s",
            registro.entrada,
            registro.cache_escrita,
            registro.cache_leitura,
            registro.saida,
        )
        if self._ao_usar is not None:
            await self._ao_usar(registro)


def criar_cliente_llm(
    settings: Settings | None = None,
    *,
    ao_usar: AoUsar | None = None,
    ao_falhar: AoFalhar | None = None,
) -> ClienteLLM | None:
    """Cliente configurado, ou `None` quando `/perguntar` está desligado."""
    cfg = settings or get_settings()
    if not cfg.llm_habilitado:
        return None
    return ClienteAnthropic(cfg, ao_usar=ao_usar, ao_falhar=ao_falhar)
