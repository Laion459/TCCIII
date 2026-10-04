from decimal import Decimal

from extrato_pdf.modulos.metricas import comparar_com_referencia


def test_metricas_iguais():
    resultado = {
        "documento": {"arquivo": "a.pdf"},
        "extrato": {
            "instituicao": "SICOOB",
            "periodo": {"inicio": "2025-01-01", "fim": "2025-01-31"},
        },
        "valores": {
            "saldo_inicial": 2334.43,
            "total_entradas": 145991.44,
            "total_saidas": 145783.37,
            "saldo_final_informado": 2542.50,
        },
        "validacao": {
            "consistente": True,
            "status_processamento": "consistente",
            "revisao_humana": False,
        },
    }
    ref = {
        "documento": "a.pdf",
        "instituicao": "SICOOB",
        "periodo_inicio": "2025-01-01",
        "periodo_fim": "2025-01-31",
        "saldo_inicial": 2334.43,
        "total_entradas": 145991.44,
        "total_saidas": 145783.37,
        "saldo_final_informado": 2542.50,
    }
    m = comparar_com_referencia(resultado, ref, Decimal("0.01"))
    assert m["acerto_instituicao"] is True
    assert m["acerto_periodo"] is True
    assert m["erro_entradas"] == 0.0


def test_paginas_do_gabarito_zero_based_casam_com_pipeline():
    resultado = {
        "documento": {"arquivo": "contas 012023.pdf"},
        "extrato": {"instituicao": "CAIXA", "periodo": {}},
        "valores": {},
        "validacao": {},
        "experimento": {"paginas_extrato": [8, 9]},
    }
    ref = {
        "documento": "contas 012023.pdf",
        "instituicao": "CAIXA",
        "paginas_extrato": [7, 8],
    }
    m = comparar_com_referencia(resultado, ref, Decimal("0.01"))
    assert m["paginas_vp"] == 2
    assert m["paginas_fp"] == 0
    assert m["paginas_fn"] == 0
