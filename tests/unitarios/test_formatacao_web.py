from extrato_pdf.web.formatacao import formatar_brl, montar_equacao, preparar_relatorio


def test_formatar_brl_positivo():
    assert formatar_brl(2542.5) == "R$ 2.542,50"


def test_formatar_brl_negativo():
    assert formatar_brl(-10.5) == "-R$ 10,50"


def test_formatar_brl_none():
    assert formatar_brl(None) == "—"


def test_preparar_relatorio_equacao():
    dados = {
        "documento": {"arquivo": "x.pdf"},
        "extrato": {"instituicao": "SICOOB", "periodo": {"inicio": "2025-01-01", "fim": "2025-01-31"}},
        "valores": {
            "saldo_inicial": 100.0,
            "total_entradas": 50.0,
            "total_saidas": 30.0,
            "saldo_final_informado": 120.0,
            "saldo_final_calculado": 120.0,
            "diferenca": 0.0,
        },
        "validacao": {"status_processamento": "consistente", "tolerancia": 0.01},
        "alertas": [],
        "experimento": {"condicao": "A", "paginas_extrato": [1, 2]},
    }
    rel = preparar_relatorio(dados)
    assert rel["equacao"] is not None
    assert rel["equacao"]["dentro_tolerancia"] is True
    assert len(rel["regras"]) >= 4


def test_montar_equacao_incompleta():
    assert montar_equacao({"valores": {"saldo_inicial": 1.0}}) is None
