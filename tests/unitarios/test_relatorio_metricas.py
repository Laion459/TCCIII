from decimal import Decimal
from pathlib import Path

from extrato_pdf.web.relatorio_metricas import (
    enriquecer_comparacao,
    formatar_relatorio_markdown,
    gerar_arquivos_relatorio,
    montar_consolidado,
)


def _resultado(status: str = "consistente", **valores):
    base_vals = {
        "saldo_inicial": 100.0,
        "total_entradas": 50.0,
        "total_saidas": 20.0,
        "saldo_final_informado": 130.0,
        "saldo_final_calculado": 130.0,
        "diferenca": 0.0,
    }
    base_vals.update(valores)
    return {
        "documento": {"arquivo": "doc.pdf", "tipo_pdf": "nativo", "quantidade_paginas": 10},
        "extrato": {
            "instituicao": "SICOOB",
            "periodo": {"inicio": "2025-01-01", "fim": "2025-01-31"},
        },
        "valores": base_vals,
        "validacao": {
            "consistente": status == "consistente",
            "status_processamento": status,
            "revisao_humana": False,
        },
        "experimento": {"condicao": "A"},
    }


def _ref():
    return {
        "documento": "doc.pdf",
        "instituicao": "SICOOB",
        "periodo_inicio": "2025-01-01",
        "periodo_fim": "2025-01-31",
        "saldo_inicial": 100.0,
        "total_entradas": 50.0,
        "total_saidas": 20.0,
        "saldo_final_informado": 130.0,
    }


def test_enriquecer_comparacao_completa():
    m = enriquecer_comparacao(_resultado(), _ref(), Decimal("0.01"))
    assert m["acerto_campos_essenciais"] is True
    assert m["acerto_entradas"] is True
    assert m["tipo_pdf"] == "nativo"


def test_gerar_arquivos_relatorio(tmp_path: Path):
    exp = tmp_path / "experimentos"
    refs = tmp_path / "refs"
    saida = tmp_path / "metricas"
    refs.mkdir()
    (refs / "D01.json").write_text(
        __import__("json").dumps(_ref(), ensure_ascii=False),
        encoding="utf-8",
    )
    for cond, status in (("a", "consistente"), ("b", "incompleto"), ("c", "consistente")):
        pasta = exp / f"condicao_{cond}" / "doc"
        pasta.mkdir(parents=True)
        res = _resultado(status=status)
        res["experimento"]["condicao"] = cond.upper()
        if cond == "b":
            res["valores"]["saldo_inicial"] = None
            res["valores"]["total_entradas"] = None
        (pasta / "resultado.json").write_text(
            __import__("json").dumps(res, ensure_ascii=False),
            encoding="utf-8",
        )

    meta = gerar_arquivos_relatorio(exp, refs, saida, Decimal("0.01"))
    assert meta["markdown_path"].exists()
    assert meta["json_path"].exists()
    texto = meta["markdown_path"].read_text(encoding="utf-8")
    assert "Relatório completo de métricas experimentais" in texto
    assert "Score 6" in texto
    assert "Divergências A × C" in texto
    assert meta["qtd_metricas"] >= 2

    consolidado = montar_consolidado(exp, refs, Decimal("0.01"))
    md = formatar_relatorio_markdown(consolidado)
    assert "Hipótese do TCC" in md
    assert consolidado["por_condicao"]["A"]["taxa_consistente"] == 100.0
