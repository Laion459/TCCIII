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


def test_resumo_dashboard_separa_condicoes(tmp_path: Path, monkeypatch):
    from extrato_pdf.web import servicos

    entrada = tmp_path / "entrada"
    refs = tmp_path / "refs"
    resultados = tmp_path / "resultados"
    entrada.mkdir()
    refs.mkdir()
    for cond, status in (("a", "consistente"), ("b", "incompleto"), ("c", "consistente")):
        pasta = resultados / "experimentos" / f"condicao_{cond}" / "doc"
        pasta.mkdir(parents=True)
        (pasta / "resultado.json").write_text(
            f"""{{
              "documento": {{"arquivo": "x.pdf"}},
              "extrato": {{"instituicao": "SICOOB"}},
              "validacao": {{"status_processamento": "{status}", "consistente": {str(status == "consistente").lower()}}},
              "experimento": {{"condicao": "{cond.upper()}"}}
            }}""",
            encoding="utf-8",
        )

    monkeypatch.setattr(servicos, "pasta_entrada", lambda: entrada)
    monkeypatch.setattr(servicos, "pasta_referencias", lambda: refs)
    monkeypatch.setattr(servicos, "pasta_resultados", lambda: resultados)
    monkeypatch.setattr(servicos, "pasta_experimentos", lambda: resultados / "experimentos")
    monkeypatch.setattr(servicos, "raiz_projeto", lambda: tmp_path)

    resumo = servicos.resumo_dashboard()
    por = {c["condicao"]: c for c in resumo["por_condicao"]}
    assert por["A"]["taxa_consistente"] == 100.0
    assert por["B"]["taxa_consistente"] == 0.0
    assert por["C"]["taxa_consistente"] == 100.0
    # Não misturar A+B+C numa única taxa no resumo.
    assert "taxa_consistencia" not in resumo


def test_listar_resultados_filtra_condicao(tmp_path: Path, monkeypatch):
    from extrato_pdf.web import servicos

    resultados = tmp_path / "resultados"
    for cond in ("a", "b"):
        pasta = resultados / "experimentos" / f"condicao_{cond}" / "doc"
        pasta.mkdir(parents=True)
        (pasta / "resultado.json").write_text(
            f'{{"documento":{{"arquivo":"x.pdf"}},"validacao":{{"status_processamento":"consistente"}},"experimento":{{"condicao":"{cond.upper()}"}}}}',
            encoding="utf-8",
        )
    monkeypatch.setattr(servicos, "pasta_resultados", lambda: resultados)
    monkeypatch.setattr(servicos, "pasta_experimentos", lambda: resultados / "experimentos")
    monkeypatch.setattr(servicos, "raiz_projeto", lambda: tmp_path)

    so_a = servicos.listar_resultados(condicao="A")
    assert len(so_a) == 1
    assert so_a[0].condicao == "A"


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
