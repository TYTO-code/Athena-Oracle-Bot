"""Instrumentação para o Grafana e custo da API do Claude (D15).

O que importa: toda chamada ao Claude é contada com tokens e custo; o teto diário e o orçamento
do mês recusam antes de chamar o modelo; e nenhuma métrica carrega pessoa.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from oraculo.db.base import sessao
from oraculo.domain.custo_llm import (
    PRECO_DESCONHECIDO,
    UsoLLM,
    custo_usd,
    orcamento_esgotado,
    preco_do_modelo,
)
from oraculo.domain.errors import OrcamentoDeIaEsgotadoError
from oraculo.integrations.llm import ClienteAnthropic
from oraculo.observabilidade import (
    Registro,
    contar_mensagem,
    medir_job,
    processo_prometheus,
    rotulo_seguro,
)
from oraculo.services.metricas_service import coletar
from oraculo.services.uso_llm_service import UsoLlmService

# --- Custo ------------------------------------------------------------------------------------


def test_custo_do_haiku_com_cache():
    uso = UsoLLM(
        "claude-haiku-4-5", entrada=1_000, saida=500, cache_escrita=2_000, cache_leitura=10_000
    )
    # 1000×1 + 2000×1,25 + 10000×0,1 + 500×5 = 7000 → US$ 0,007
    assert custo_usd(uso) == pytest.approx(0.007)


def test_modelo_com_data_usa_o_preco_da_familia():
    assert preco_do_modelo("claude-haiku-4-5-20251001") == (1.0, 5.0)


def test_modelo_desconhecido_custa_o_mais_caro():
    assert preco_do_modelo("modelo-novo") == PRECO_DESCONHECIDO
    assert custo_usd(UsoLLM("modelo-novo", saida=1_000_000)) >= 20


def test_orcamento():
    assert orcamento_esgotado(0.05, 1.0, 0.10, 5.0) is None
    assert orcamento_esgotado(0.10, 1.0, 0.10, 5.0) == "diario"
    assert orcamento_esgotado(0.01, 5.0, 0.10, 5.0) == "mensal"
    assert orcamento_esgotado(9.0, 1.0, 0, 5.0) is None, "teto 0 desliga o freio do dia"


# --- Nenhuma pessoa nas métricas ---------------------------------------------------------------


@pytest.mark.parametrize("valor", ["123456789012345678", "fulano@example.com", "x" * 65])
def test_valor_que_parece_pessoa_e_descartado(valor):
    assert rotulo_seguro("projeto", valor) == "descartado"


def test_rotulo_fora_da_lista_nao_existe():
    with pytest.raises(ValueError):
        rotulo_seguro("uid", "abc")
    with pytest.raises(ValueError):
        Registro().contar("x_total", "x", membro="ana")


def test_projeto_pode_ser_rotulo():
    assert rotulo_seguro("projeto", "alpha-01") == "alpha-01"


# --- Registro e formato ------------------------------------------------------------------------


async def test_medir_job_conta_ok_e_erro_e_marca_horario():
    reg = Registro()
    async with medir_job("backup", reg):
        pass
    with pytest.raises(RuntimeError):
        async with medir_job("backup", reg):
            raise RuntimeError("falhou")

    assert reg.valor("oraculo_job_execucoes_total", rotina="backup", resultado="ok") == 1
    assert reg.valor("oraculo_job_execucoes_total", rotina="backup", resultado="erro") == 1
    assert reg.valor("oraculo_job_ultima_execucao_timestamp_seconds", rotina="backup") > 0
    texto = reg.texto_prometheus()
    assert "# TYPE oraculo_job_duracao_segundos histogram" in texto
    assert 'oraculo_job_duracao_segundos_bucket{rotina="backup",le="+Inf"} 2' in texto
    assert 'oraculo_job_duracao_segundos_count{rotina="backup"} 2' in texto


def test_mensagens_por_grupo():
    reg = Registro()
    contar_mensagem("alerta_pessoa", "sent", reg)
    contar_mensagem("alerta_projeto", "sent", reg)
    contar_mensagem("coisa_nova", "failed", reg)
    assert reg.valor("oraculo_gerente_mensagens_total", tipo="alerta", resultado="sent") == 2
    assert reg.valor("oraculo_gerente_mensagens_total", tipo="outro", resultado="failed") == 1


def test_cpu_e_memoria_do_processo():
    texto = processo_prometheus()
    assert "process_cpu_seconds_total" in texto


# --- Serviço de uso e teto ---------------------------------------------------------------------


def _servico(
    teto: float = 0.10, mensal: float = 5.0, dia: str = "2026-11-14"
) -> tuple[UsoLlmService, Registro]:
    reg = Registro()
    momento = datetime.fromisoformat(dia + "T12:00:00").replace(tzinfo=UTC)
    return (
        UsoLlmService(
            abrir_sessao=lambda: sessao(),
            teto_diario_usd=teto,
            orcamento_mensal_usd=mensal,
            registro=reg,
            relogio=lambda: momento,
        ),
        reg,
    )


async def test_registra_tokens_e_custo_e_soma_no_banco(engine):
    servico, reg = _servico()
    uso = UsoLLM("claude-haiku-4-5", entrada=10_000, saida=2_000)  # US$ 0,02
    await servico.registrar(uso)
    await servico.registrar(uso)

    assert reg.valor("oraculo_llm_chamadas_total", modelo="claude-haiku-4-5", resultado="ok") == 2
    assert reg.valor("oraculo_llm_tokens_total", modelo="claude-haiku-4-5", tipo="saida") == 4_000
    assert reg.valor("oraculo_llm_custo_usd_total", modelo="claude-haiku-4-5") == pytest.approx(
        0.04
    )
    async with sessao() as session:
        hoje, mes = await servico.custos(session)
    assert hoje == pytest.approx(0.04)
    assert mes == pytest.approx(0.04)


async def test_teto_diario_recusa_antes_de_chamar(engine):
    servico, reg = _servico(teto=0.03)
    await servico.verificar()  # ainda não gastou nada
    await servico.registrar(UsoLLM("claude-haiku-4-5", entrada=10_000, saida=5_000))  # 0,035
    with pytest.raises(OrcamentoDeIaEsgotadoError) as erro:
        await servico.verificar()
    assert erro.value.motivo == "diario"
    assert reg.valor("oraculo_llm_recusas_orcamento_total", motivo="diario") == 1


async def test_orcamento_do_mes_soma_dias_anteriores(engine):
    ontem, _ = _servico(dia="2026-11-13")
    await ontem.registrar(UsoLLM("claude-haiku-4-5", saida=1_000_000))  # US$ 5
    hoje, _ = _servico(dia="2026-11-14")
    with pytest.raises(OrcamentoDeIaEsgotadoError) as erro:
        await hoje.verificar()
    assert erro.value.motivo == "mensal"
    outro_mes, _ = _servico(dia="2026-12-01")
    await outro_mes.verificar()


async def test_sem_conseguir_ler_o_uso_recusa():
    @asynccontextmanager
    async def quebrada():
        raise RuntimeError("banco fora")
        yield  # pragma: no cover

    servico = UsoLlmService(abrir_sessao=quebrada)
    with pytest.raises(OrcamentoDeIaEsgotadoError):
        await servico.verificar()


async def test_falha_ao_gravar_nao_quebra_a_resposta():
    @asynccontextmanager
    async def quebrada():
        raise RuntimeError("banco fora")
        yield  # pragma: no cover

    reg = Registro()
    servico = UsoLlmService(abrir_sessao=quebrada, registro=reg)
    await servico.registrar(UsoLLM("claude-haiku-4-5", entrada=10))
    assert reg.valor("oraculo_llm_chamadas_total", modelo="claude-haiku-4-5", resultado="ok") == 1


async def test_metrics_mostra_custo_e_tetos(session, engine):
    servico, _ = _servico(dia=datetime.now(UTC).strftime("%Y-%m-%d"))
    await servico.registrar(UsoLLM("claude-haiku-4-5", saida=10_000))  # 0,05
    metricas = {m.nome: m for m in await coletar(session)}
    assert metricas["oraculo_llm_custo_hoje_usd"].valor() == pytest.approx(0.05)
    assert metricas["oraculo_llm_teto_diario_usd"].valor() == pytest.approx(0.10)
    assert metricas["oraculo_llm_alerta_mensal_usd"].valor() == pytest.approx(4.0)


# --- Cliente da Anthropic: todo uso é contado ---------------------------------------------------


async def test_cliente_conta_o_uso_de_cada_resposta(settings):
    vistos: list[UsoLLM] = []

    async def ao_usar(uso: UsoLLM) -> None:
        vistos.append(uso)

    cliente = ClienteAnthropic(
        settings.model_copy(update={"anthropic_api_key": "x"}), ao_usar=ao_usar
    )
    resposta = SimpleNamespace(
        model="claude-haiku-4-5",
        stop_reason="refusal",
        content=[],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=3,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=7,
        ),
    )
    await cliente._contar_uso(resposta)
    assert vistos == [UsoLLM("claude-haiku-4-5", entrada=10, saida=3, cache_leitura=7)]
