from decimal import Decimal

from extrato_pdf.modelos import OrigemTexto, PaginaTexto
from extrato_pdf.modulos.parser import extrair_campos
from extrato_pdf.util.config import carregar_config


SNIPPET = """
SICOOB
EXTRATO CONTA CORRENTE
PERÍODO: 01/01/2025 - 31/01/2025
HISTÓRICO DE MOVIMENTAÇÃO
31/12
SALDO ANTERIOR
2.334,43
C
02/01
PIX EMIT.OUTRA IF
150,00D
07/01
CRÉD.TED-STR
96.169,38
C
07/01
PIX EMIT.OUTRA IF
200,00D
31/01
SALDO DO DIA
2.542,50
C
RESUMO
SALDO EM C.CORRENTE(+):
2.542,50C
OUVIDORIA SICOOB: 0800
"""


def test_parser_sicoob_snippet_basico():
    # Totais parciais do snippet (não o mês completo); valida extração estrutural
    config = carregar_config()
    paginas = [PaginaTexto(1, SNIPPET, OrigemTexto.NATIVO)]
    campos = extrair_campos(paginas, [], config)
    assert campos.instituicao == "SICOOB"
    assert campos.periodo_inicio == "2025-01-01"
    assert campos.periodo_fim == "2025-01-31"
    assert campos.saldo_inicial == Decimal("2334.43")
    assert campos.saldo_final_informado == Decimal("2542.50")
    assert campos.total_entradas == Decimal("96169.38")
    assert campos.total_saidas == Decimal("350.00")
