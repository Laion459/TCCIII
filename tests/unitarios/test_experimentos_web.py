from pathlib import Path

from extrato_pdf.web.experimentos import (
    agregar_corpus_experimentos,
    avaliar_hipotese,
    montar_heatmap,
    montar_laboratorio,
)


def test_agregar_corpus_vazio(tmp_path: Path):
    corpus = agregar_corpus_experimentos(tmp_path)
    assert corpus["A"]["total"] == 0
    assert corpus["C"]["taxa_consistente"] == 0.0


def test_montar_laboratorio_com_corpus(tmp_path: Path):
    base = tmp_path / "condicao_a" / "doc1"
    base.mkdir(parents=True)
    (base / "resultado.json").write_text(
        """{
      "documento": {"arquivo": "a.pdf"},
      "validacao": {"status_processamento": "consistente", "consistente": true}
    }""",
        encoding="utf-8",
    )
    lab = montar_laboratorio([], tmp_path)
    assert lab["corpus"]["A"]["total"] == 1
    assert lab["corpus"]["A"]["taxa_consistente"] == 100.0
    assert len(lab["heatmap"]) == 1


def test_avaliar_hipotese_confirmada():
    corpus = {
        "A": {"total": 1, "taxa_consistente": 50.0},
        "B": {"total": 1, "taxa_consistente": 40.0},
        "C": {"total": 1, "taxa_consistente": 80.0},
    }
    referencia = {"A": {"total": 0, "score": 0}, "B": {"total": 0, "score": 0}, "C": {"total": 0, "score": 0}}
    hip = avaliar_hipotese(corpus, referencia)
    assert hip["veredito"] == "confirmada"
    assert hip["c_maior_igual_a"] is True


def test_heatmap_multiplas_condicoes(tmp_path: Path):
    for cond, status in (("a", "consistente"), ("c", "incompleto")):
        pasta = tmp_path / f"condicao_{cond}" / "mesmo"
        pasta.mkdir(parents=True)
        (pasta / "resultado.json").write_text(
            f'{{"documento":{{"arquivo":"x.pdf"}},"validacao":{{"status_processamento":"{status}"}}}}',
            encoding="utf-8",
        )
    corpus = agregar_corpus_experimentos(tmp_path)
    heat = montar_heatmap(corpus)
    assert heat[0]["documento"] == "x.pdf"
    assert heat[0]["A"] == "consistente"
    assert heat[0]["C"] == "incompleto"
