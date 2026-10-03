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
    agregado = agregar_movimentos_caixa(SNIPPET_CAIXA_BR)
    assert agregado.saldo_inicial == Decimal("4856.97")
    assert agregado.saldo_final == Decimal("6921.05")
    assert agregado.total_saidas == Decimal("100.00")
    assert agregado.total_entradas == Decimal("5000.00")
    assert agregado.total_entradas_inferido == Decimal("2164.08")
    assert agregado.entradas_divergem_identidade is True
    assert agregado.periodo_inicio == "2023-02-01"
    assert agregado.periodo_fim == "2023-02-28"


def test_parser_caixa_us_movimentos():
    agregado = agregar_movimentos_caixa(SNIPPET_CAIXA_US)
    assert agregado.saldo_inicial == Decimal("0.00")
    assert agregado.total_entradas == Decimal("1000.00")
    assert agregado.total_saidas == Decimal("200.00")
    assert agregado.saldo_final == Decimal("800.00")
    assert agregado.entradas_divergem_identidade is False


def test_periodo_de_mes_usa_ultimo_dia_civil():
    assert agregar_movimentos_caixa("Mês: janeiro/2023").periodo_fim == "2023-01-31"
    assert agregar_movimentos_caixa("Mês: abril/2023").periodo_fim == "2023-04-30"
    assert agregar_movimentos_caixa("Mês: fevereiro/2024").periodo_fim == "2024-02-29"
    assert agregar_movimentos_caixa("Mês: fevereiro/2023").periodo_fim == "2023-02-28"


def test_intervalo_explicito_precede_o_mes():
    texto = "PERÍODO: 05/01/2023 - 20/01/2023\nMês: janeiro/2023"
    agregado = agregar_movimentos_caixa(texto)
    assert agregado.periodo_inicio == "2023-01-05"
    assert agregado.periodo_fim == "2023-01-20"


def test_sem_credito_preserva_valor_lido():
    texto = """
Extrato por período
CAIXA
Mês: janeiro/2023
SALDO ANTERIOR
100,00 C
SALDO DIA
130,00 C
"""
    agregado = agregar_movimentos_caixa(texto)
    assert agregado.total_entradas == Decimal("0.00")
    assert agregado.total_entradas_inferido == Decimal("30.00")
    assert agregado.entradas_divergem_identidade is True
    assert agregado.periodo_fim == "2023-01-31"


def test_extrair_campos_caixa_br_snippet():
    config = carregar_config()
    paginas = [PaginaTexto(1, SNIPPET_CAIXA_BR, OrigemTexto.NATIVO)]
    campos = extrair_campos(paginas, [], config)
    assert campos.instituicao == "CAIXA"
    assert campos.saldo_inicial == Decimal("4856.97")
    assert campos.saldo_final_informado == Decimal("6921.05")
    assert campos.total_saidas == Decimal("100.00")
    assert campos.total_entradas == Decimal("5000.00")
    assert campos.total_entradas_inferido == Decimal("2164.08")
    assert campos.divergencia_entradas_identidade is True


def test_identificar_caixa():
    from extrato_pdf.modulos.instituicao import identificar_instituicao

    config = carregar_config()
    r = identificar_instituicao("Extrato por período CAIXA ECONOMICA FEDERAL", config)
    assert r.nome == "CAIXA"
    assert r.ambigua is False
