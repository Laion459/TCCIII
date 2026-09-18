from decimal import Decimal

from extrato_pdf.modelos import OrigemTexto, PaginaTexto
from extrato_pdf.modulos.parser import extrair_campos
from extrato_pdf.modulos.parser_caixa import agregar_movimentos_caixa
from extrato_pdf.util.config import carregar_config


SNIPPET_CAIXA_BR = """
Extrato por período
CAIXA
Agência: 3392 / Produto: 001 / Conta: 00002098-8
Mês: fevereiro/2023
Data Histórico Valor
01/02/2023
SALDO ANTERIOR
4.856,97 C
04/02/2023
CRED TED
5.000,00 C
10.000,00 C
04/02/2023
ENVIO PIX
100,00 D
9.900,00 C
28/02/2023
SALDO DIA
6.921,05 C
Lançamentos do Dia
16/03/2023
ALGO
1,00 D
"""


SNIPPET_CAIXA_US = """
Extrato por período
caixa.gov.br
Agência: 3392 / Produto: 003 / Conta: 00002098-8
01/01/2023
SALDO ANTERIOR
0.00
0.00
05/01/2023
CRED TED
1000.00
1000.00
10/01/2023
ENVIO PIX
-200.00
800.00
31/01/2023
SALDO DIA
0.00
800.00
"""


def test_parser_caixa_br_rotulos_e_debitos():
    si, e, s, sf, pi, pf = agregar_movimentos_caixa(SNIPPET_CAIXA_BR)
    assert si == Decimal("4856.97")
    assert sf == Decimal("6921.05")
    assert s == Decimal("100.00")
    # identidade sf - si + saidas
    assert e == Decimal("2164.08")
    assert pi == "2023-02-01"
    assert pf == "2023-02-28"


def test_parser_caixa_us_movimentos():
    si, e, s, sf, _pi, _pf = agregar_movimentos_caixa(SNIPPET_CAIXA_US)
    assert si == Decimal("0.00")
    assert e == Decimal("1000.00")
    assert s == Decimal("200.00")
    assert sf == Decimal("800.00")


def test_extrair_campos_caixa_br_snippet():
    config = carregar_config()
    paginas = [PaginaTexto(1, SNIPPET_CAIXA_BR, OrigemTexto.NATIVO)]
    campos = extrair_campos(paginas, [], config)
    assert campos.instituicao == "CAIXA"
    assert campos.saldo_inicial == Decimal("4856.97")
    assert campos.saldo_final_informado == Decimal("6921.05")
    assert campos.total_saidas == Decimal("100.00")
    assert campos.total_entradas == Decimal("2164.08")


def test_identificar_caixa():
    from extrato_pdf.modulos.instituicao import identificar_instituicao

    config = carregar_config()
    r = identificar_instituicao("Extrato por período CAIXA ECONOMICA FEDERAL", config)
    assert r.nome == "CAIXA"
    assert r.ambigua is False
