"""Instrumentação em memória para o Grafana (docs/DECISOES.md, D15).

Contadores, histogramas e medidores do processo, expostos junto com as métricas agregadas do
banco em `GET /metrics` (formato Prometheus). Nada é enviado daqui: o Grafana Cloud busca o
endpoint, então a coleta não custa CPU nem memória entre uma busca e outra.

Regra que não se negocia: **nenhuma métrica carrega pessoa**. Só existem os rótulos de
`ROTULOS_PERMITIDOS`, e um valor que pareça identificador de pessoa (ID do Discord, e-mail) vira
`"descartado"`. O rótulo mais específico permitido é o identificador do projeto.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from oraculo.logging_config import get_logger

log = get_logger(__name__)

ROTULOS_PERMITIDOS = frozenset(
    {"job", "resultado", "tipo", "modelo", "motivo", "projeto", "destino", "evento"}
)
_PARECE_PESSOA = re.compile(r"@|\d{15,}")
_LIMITE_VALOR = 64
BALDES_SEGUNDOS: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300)


def rotulo_seguro(chave: str, valor: object) -> str:
    """Valor de rótulo que pode sair; o que parece pessoa (ou é longo demais) é descartado."""
    if chave not in ROTULOS_PERMITIDOS:
        raise ValueError(f"Rótulo não permitido em métrica: {chave!r}")
    texto = str(valor)
    if _PARECE_PESSOA.search(texto) or len(texto) > _LIMITE_VALOR:
        log.warning("Métrica: valor de rótulo %r descartado (parece identificador).", chave)
        return "descartado"
    return texto


Chave = tuple[tuple[str, str], ...]


def _chave(rotulos: dict[str, object]) -> Chave:
    return tuple(sorted((k, rotulo_seguro(k, v)) for k, v in rotulos.items()))


@dataclass(slots=True)
class _Serie:
    nome: str
    ajuda: str
    tipo: str
    valores: dict[Chave, float] = field(default_factory=dict)
    #: Só para histogramas: contagem por balde, soma e total por série.
    baldes: dict[Chave, list[int]] = field(default_factory=dict)
    somas: dict[Chave, float] = field(default_factory=dict)


class Registro:
    """Métricas do processo. Um por processo (`REGISTRO`); testes criam o seu."""

    def __init__(self) -> None:
        self._series: dict[str, _Serie] = {}

    def _serie(self, nome: str, ajuda: str, tipo: str) -> _Serie:
        serie = self._series.get(nome)
        if serie is None:
            serie = self._series[nome] = _Serie(nome, ajuda, tipo)
        elif serie.tipo != tipo:
            raise ValueError(f"Métrica {nome} já existe como {serie.tipo}")
        return serie

    def contar(self, nome: str, ajuda: str, valor: float = 1.0, **rotulos: object) -> None:
        serie = self._serie(nome, ajuda, "counter")
        chave = _chave(rotulos)
        serie.valores[chave] = serie.valores.get(chave, 0.0) + max(valor, 0.0)

    def definir(self, nome: str, ajuda: str, valor: float, **rotulos: object) -> None:
        self._serie(nome, ajuda, "gauge").valores[_chave(rotulos)] = float(valor)

    def observar(self, nome: str, ajuda: str, segundos: float, **rotulos: object) -> None:
        serie = self._serie(nome, ajuda, "histogram")
        chave = _chave(rotulos)
        baldes = serie.baldes.setdefault(chave, [0] * len(BALDES_SEGUNDOS))
        for i, limite in enumerate(BALDES_SEGUNDOS):
            if segundos <= limite:
                baldes[i] += 1
        serie.somas[chave] = serie.somas.get(chave, 0.0) + segundos
        serie.valores[chave] = serie.valores.get(chave, 0.0) + 1

    def valor(self, nome: str, **rotulos: object) -> float:
        serie = self._series.get(nome)
        return serie.valores.get(_chave(rotulos), 0.0) if serie else 0.0

    def texto_prometheus(self) -> str:
        linhas: list[str] = []
        for serie in self._series.values():
            linhas.append(f"# HELP {serie.nome} {serie.ajuda}")
            linhas.append(f"# TYPE {serie.nome} {serie.tipo}")
            for chave, valor in serie.valores.items():
                if serie.tipo != "histogram":
                    linhas.append(f"{serie.nome}{_formatar(chave)} {valor:g}")
                    continue
                for limite, contagem in zip(BALDES_SEGUNDOS, serie.baldes[chave], strict=True):
                    le = (*chave, ("le", f"{limite:g}"))
                    linhas.append(f"{serie.nome}_bucket{_formatar(le)} {contagem}")
                linhas.append(f"{serie.nome}_bucket{_formatar((*chave, ('le', '+Inf')))} {valor:g}")
                linhas.append(f"{serie.nome}_sum{_formatar(chave)} {serie.somas[chave]:g}")
                linhas.append(f"{serie.nome}_count{_formatar(chave)} {valor:g}")
        return "\n".join(linhas) + ("\n" if linhas else "")


def _formatar(chave: Chave) -> str:
    if not chave:
        return ""
    corpo = ",".join(
        f'{k}="{v.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
        for k, v in chave
    )
    return "{" + corpo + "}"


REGISTRO = Registro()


# --- Atalhos usados pelo código --------------------------------------------------------------


@asynccontextmanager
async def medir_job(nome: str, registro: Registro | None = None) -> AsyncIterator[None]:
    """Mede uma execução de job agendado: resultado, duração e hora da última execução.

    A exceção continua subindo (quem chama decide se o laço sobrevive); a métrica só registra.
    """
    reg = registro or REGISTRO
    inicio = time.monotonic()
    resultado = "erro"
    try:
        yield
        resultado = "ok"
    finally:
        reg.contar(
            "oraculo_job_execucoes_total",
            "Execuções de jobs agendados.",
            job=nome,
            resultado=resultado,
        )
        reg.observar(
            "oraculo_job_duracao_segundos",
            "Duração das execuções de jobs.",
            time.monotonic() - inicio,
            job=nome,
        )
        agora = time.time()
        reg.definir(
            "oraculo_job_ultima_execucao_timestamp_seconds",
            "Hora (Unix) da última execução do job, com ou sem erro.",
            agora,
            job=nome,
        )
        if resultado == "ok":
            reg.definir(
                "oraculo_job_ultimo_sucesso_timestamp_seconds",
                "Hora (Unix) da última execução do job que terminou sem erro.",
                agora,
                job=nome,
            )


#: Tipo da ação do gerente (API) → grupo do painel. O resto vira "outro".
GRUPO_MENSAGEM = {
    "lembrete": "lembrete",
    "alerta_pessoa": "alerta",
    "alerta_projeto": "alerta",
    "onboarding": "onboarding",
    "resumo_semanal": "resumo",
    "destaque_missoes": "missoes",
    "relatorio_sombra": "sombra",
}


def contar_mensagem(tipo: object, resultado: str, registro: Registro | None = None) -> None:
    grupo = GRUPO_MENSAGEM.get(str(tipo), "outro")
    (registro or REGISTRO).contar(
        "oraculo_gerente_mensagens_total",
        "Mensagens do gerente entregues pela Atena, por tipo e resultado.",
        tipo=grupo,
        resultado=resultado,
    )


def contar_rota(comando: str, registro: Registro | None = None) -> None:
    """Pergunta do `/perguntar` respondida por comando fixo, sem chamar a IA."""
    (registro or REGISTRO).contar(
        "oraculo_perguntas_sem_ia_total",
        "Perguntas do /perguntar respondidas sem IA (roteador ou cache).",
        destino=comando,
    )


def processo_prometheus() -> str:
    """CPU e memória deste processo — o que o Railway cobra. Sem dependência nova."""
    tempos = os.times()
    linhas = [
        "# HELP process_cpu_seconds_total CPU (usuário + sistema) gasta pelo processo.",
        "# TYPE process_cpu_seconds_total counter",
        f"process_cpu_seconds_total {tempos.user + tempos.system:g}",
    ]
    rss = _memoria_residente()
    if rss is not None:
        linhas += [
            "# HELP process_resident_memory_bytes Memória residente do processo.",
            "# TYPE process_resident_memory_bytes gauge",
            f"process_resident_memory_bytes {rss}",
        ]
    return "\n".join(linhas) + "\n"


def _memoria_residente() -> int | None:
    try:
        with open("/proc/self/statm", encoding="ascii") as arquivo:
            paginas = int(arquivo.read().split()[1])
        return paginas * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return None
