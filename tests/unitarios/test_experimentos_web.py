from pathlib import Path

from extrato_pdf.web.experimentos import (
    agregar_corpus_experimentos,
    avaliar_hipotese,
    montar_heatmap,
    montar_laboratorio,
)


def test_listar_pdfs_separa_corpora(tmp_path: Path, monkeypatch):
    from extrato_pdf.web import servicos

    entrada = tmp_path / "entrada"
    (entrada / "pdf nativo").mkdir(parents=True)
    (entrada / "pdf-100-dpi").mkdir()
    (entrada / "pdf nativo" / "contas 012023.pdf").write_bytes(b"%PDF")
    (entrada / "pdf-100-dpi" / "contas 012023.pdf").write_bytes(b"%PDF-100")
    (entrada / "solto.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(servicos, "pasta_entrada", lambda: entrada)

    nativos = servicos.listar_pdfs_entrada("pdf-nativo")
    rasters = servicos.listar_pdfs_entrada("pdf-100-dpi")

    assert [item.nome for item in nativos] == ["contas 012023.pdf"]
    assert [item.nome for item in rasters] == ["contas 012023.pdf"]
    assert servicos.pasta_gravacao_corpus("pdf-100-dpi").name == "pdf-100-dpi"


def test_nome_pdf_rejeita_caminho():
    import pytest

    from extrato_pdf.web.servicos import nome_pdf_seguro

    with pytest.raises(ValueError):
        nome_pdf_seguro(r"..\contas 012023.pdf")


def test_esteira_combina_corpus_e_condicao(tmp_path: Path, monkeypatch):
    from extrato_pdf.web import servicos

    entrada = tmp_path / "entrada"
    (entrada / "pdf nativo").mkdir(parents=True)
    (entrada / "pdf-100-dpi").mkdir()
    (entrada / "pdf-200-dpi").mkdir()
    (entrada / "pdf nativo" / "contas 012023.pdf").write_bytes(b"%PDF")
    (entrada / "pdf nativo" / "contas 022023.pdf").write_bytes(b"%PDF")
    (entrada / "pdf-100-dpi" / "contas 012023.pdf").write_bytes(b"%PDF")
    (entrada / "pdf-200-dpi" / "contas 012023.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(servicos, "pasta_entrada", lambda: entrada)

    itens = servicos.montar_esteira(
        ["pdf-200-dpi", "pdf-nativo", "pdf-100-dpi"],
        ["C", "A"],
        ["contas 022023.pdf", "contas 012023.pdf"],
    )
    pares = [(item.corpus, item.condicao, item.arquivo) for item in itens]
    assert pares == [
        ("pdf-nativo", "A", "contas 022023.pdf"),
        ("pdf-nativo", "A", "contas 012023.pdf"),
        ("pdf-nativo", "C", "contas 022023.pdf"),
        ("pdf-nativo", "C", "contas 012023.pdf"),
        ("pdf-100-dpi", "A", "contas 012023.pdf"),
        ("pdf-100-dpi", "C", "contas 012023.pdf"),
        ("pdf-200-dpi", "A", "contas 012023.pdf"),
        ("pdf-200-dpi", "C", "contas 012023.pdf"),
    ]


def test_esteira_rejeita_selecao_vazia():
    from extrato_pdf.web import servicos
    import pytest

    with pytest.raises(ValueError, match="condição"):
        servicos.normalizar_condicoes([])
    with pytest.raises(ValueError, match="corpus"):
        servicos.normalizar_corpora([])


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
