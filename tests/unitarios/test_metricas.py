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
