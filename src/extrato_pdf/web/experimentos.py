from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


CONDICOES = ("A", "B", "C")

_STATUS_ORDEM = (
    "consistente",
    "inconsistente",
    "incompleto",
    "revisao_necessaria",
    "nao_processavel",
)


def _taxa_consistente(por_status: dict[str, int]) -> float:
    total = sum(por_status.values())
    if total == 0:
        return 0.0
    return round(por_status.get("consistente", 0) / total * 100, 1)


def _score_referencia(itens: list[dict[str, Any]]) -> float:
    if not itens:
        return 0.0
    pontos = 0.0
    for item in itens:
        campos = (
            item.get("acerto_instituicao"),
            item.get("acerto_periodo"),
            item.get("acerto_saldo_inicial"),
            item.get("consistente"),
        )
        pontos += sum(1 for c in campos if c) / len(campos)
    return round(pontos / len(itens) * 100, 1)


def agregar_corpus_experimentos(pasta_experimentos: Path) -> dict[str, dict[str, Any]]:
    """Agrega status por condição a partir dos JSON em resultados/experimentos."""
    corpus: dict[str, dict[str, Any]] = {}
    for cond in CONDICOES:
        base = pasta_experimentos / f"condicao_{cond.lower()}"
        por_status: dict[str, int] = defaultdict(int)
        documentos: dict[str, str] = {}
        if base.exists():
            for json_path in base.rglob("resultado.json"):
                try:
                    dados = json.loads(json_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                status = dados.get("validacao", {}).get("status_processamento", "?")
                por_status[status] += 1
                arquivo = dados.get("documento", {}).get("arquivo", json_path.parent.name)
                documentos[arquivo] = status
        corpus[cond] = {
            "total": sum(por_status.values()),
            "por_status": dict(por_status),
            "taxa_consistente": _taxa_consistente(por_status),
            "documentos": documentos,
        }
    return corpus


def montar_heatmap(corpus: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    todos_docs: set[str] = set()
    for info in corpus.values():
        todos_docs.update(info.get("documentos", {}).keys())
    linhas: list[dict[str, Any]] = []
    for doc in sorted(todos_docs):
        linha: dict[str, Any] = {"documento": doc}
        for cond in CONDICOES:
            linha[cond] = corpus.get(cond, {}).get("documentos", {}).get(doc)
        linhas.append(linha)
    return linhas


def agregar_referencia_por_condicao(itens: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    por_cond: dict[str, list[dict[str, Any]]] = {c: [] for c in CONDICOES}
    for item in itens:
        cond = (item.get("condicao") or "?").upper()
        if cond in por_cond:
            por_cond[cond].append(item)

    resultado: dict[str, dict[str, Any]] = {}
    for cond, lista in por_cond.items():
        if not lista:
            resultado[cond] = {
                "total": 0,
                "acertos_pct": {},
                "score": 0.0,
                "media_erro_entradas": None,
                "media_erro_saidas": None,
            }
            continue

        def pct(campo: str) -> float:
            return round(sum(1 for i in lista if i.get(campo)) / len(lista) * 100, 1)

        erros_ent = [i["erro_entradas"] for i in lista if i.get("erro_entradas") is not None]
        erros_sai = [i["erro_saidas"] for i in lista if i.get("erro_saidas") is not None]

        resultado[cond] = {
            "total": len(lista),
            "acertos_pct": {
                "instituicao": pct("acerto_instituicao"),
                "periodo": pct("acerto_periodo"),
                "saldo_inicial": pct("acerto_saldo_inicial"),
                "consistente": pct("consistente"),
            },
            "score": _score_referencia(lista),
            "media_erro_entradas": round(sum(erros_ent) / len(erros_ent), 2) if erros_ent else None,
            "media_erro_saidas": round(sum(erros_sai) / len(erros_sai), 2) if erros_sai else None,
        }
    return resultado


def avaliar_hipotese(corpus: dict[str, dict[str, Any]], referencia: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Hipótese TCC: condição C ≥ A e C ≥ B."""
    def score_cond(cond: str) -> float:
        ref = referencia.get(cond, {})
        corp = corpus.get(cond, {})
        if ref.get("total", 0) > 0:
            return float(ref.get("score", 0))
        return float(corp.get("taxa_consistente", 0))

    score_a = score_cond("A")
    score_b = score_cond("B")
    score_c = score_cond("C")

    c_ge_a = score_c >= score_a if corpus.get("C", {}).get("total", 0) else False
    c_ge_b = score_c >= score_b if corpus.get("C", {}).get("total", 0) else False

    if score_c == 0 and score_a == 0 and score_b == 0:
        veredito = "indeterminado"
    elif c_ge_a and c_ge_b:
        veredito = "confirmada"
    elif c_ge_a or c_ge_b:
        veredito = "parcial"
    else:
        veredito = "refutada"

    return {
        "texto": "Condição C ≥ A e C ≥ B nas métricas agregadas",
        "scores": {"A": score_a, "B": score_b, "C": score_c},
        "c_maior_igual_a": c_ge_a,
        "c_maior_igual_b": c_ge_b,
        "veredito": veredito,
    }


def montar_laboratorio(
    itens_referencia: list[dict[str, Any]],
    pasta_experimentos: Path,
) -> dict[str, Any]:
    corpus = agregar_corpus_experimentos(pasta_experimentos)
    referencia = agregar_referencia_por_condicao(itens_referencia)
    heatmap = montar_heatmap(corpus)
    hipotese = avaliar_hipotese(corpus, referencia)

    chart_status = []
    for status in _STATUS_ORDEM:
        linha = {"status": status, "valores": {}}
        for cond in CONDICOES:
            linha["valores"][cond] = corpus.get(cond, {}).get("por_status", {}).get(status, 0)
        if any(linha["valores"].values()):
            chart_status.append(linha)

    chart_acertos = []
    for metrica, rotulo in (
        ("instituicao", "Instituição"),
        ("periodo", "Período"),
        ("saldo_inicial", "Saldo inicial"),
        ("consistente", "Consistente"),
    ):
        chart_acertos.append(
            {
                "metrica": rotulo,
                "valores": {
                    cond: referencia.get(cond, {}).get("acertos_pct", {}).get(metrica, 0)
                    for cond in CONDICOES
                },
            }
        )

    return {
        "corpus": corpus,
        "referencia": referencia,
        "heatmap": heatmap,
        "hipotese": hipotese,
        "chart_status": chart_status,
        "chart_acertos": chart_acertos,
        "condicoes": list(CONDICOES),
    }
