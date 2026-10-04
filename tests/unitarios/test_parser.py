from decimal import Decimal

from extrato_pdf.modelos import OrigemTexto, PaginaTexto
from extrato_pdf.modulos.parser import _agregar_movimentos_sicoob, extrair_campos
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


def test_sicoob_sem_lancamento_nao_grava_zero():
    texto = """
SICOOB
EXTRATO CONTA CORRENTE
PERÍODO: 01/01/2024 - 31/01/2024
HISTÓRICO DE MOVIMENTAÇÃO
"""
    saldo_inicial, entradas, saidas, saldo_final = _agregar_movimentos_sicoob(texto)
    assert saldo_inicial is None
    assert entradas is None
    assert saidas is None
    assert saldo_final is None


def test_sicoob_ocr_mesma_linha():
    texto = """
SICOOB
EXTRATO CONTA CORRENTE
PERÍODO: 01/01/2024 - 31/01/2024
2212 —SALDO ANTERIOR 0,00C
2901 — PIXREC.OUTRA F MT 120
2901 — CADASTRO 38,05D
30/01 — DEB.EMI.TED DIF.TIT 502,04D
30/01 — DEB.EMI.TED DIF.TIT 100,00D
31/01 — TED INTERNET 20,66D
RESUMO
SALDO EM C.CORRENTE(+): 8.576,23C
"""
    saldo_inicial, entradas, saidas, saldo_final = _agregar_movimentos_sicoob(texto)
    assert saldo_inicial == Decimal("0.00")
    assert entradas is None
    assert saidas == Decimal("660.75")
    assert saldo_final == Decimal("8576.23")


def test_sicoob_ocr_coluna_valor():
    texto = """
EXTRATO CONTA CORRENTE
PERÍODO: 01/01/2024 - 31/01/2024
HISTÓRICO
SALDO ANTERIOR
PIX REC.OUTRA IF MT
CADASTRO
SALDO DO DIA
RESUMO
SALDO EM C.CORRENTE(+):
VALOR
0,00C
9.236,98
c
38,05D
9.198,93
c
502,04D
100,00D
8.596,89
c
20,66D
8.576,23
c
8.576,23C
"""
    saldo_inicial, entradas, saidas, saldo_final = _agregar_movimentos_sicoob(texto)
    assert saldo_inicial == Decimal("0.00")
    assert entradas == Decimal("9236.98")
    assert saidas == Decimal("660.75")
    assert saldo_final == Decimal("8576.23")


def test_sicoob_cd_depois_do_cabecalho_de_pagina():
    texto = """
EXTRATO CONTA CORRENTE
31/12
SALDO ANTERIOR
0,00
C
10/04
DÉB.PGTO.BOLETO INT
5.054,07
ANEXO DE CONTAS FINANCEIRAS
Período base: ABR 2024
RESID. PORTAL DO SANTINHO
1
EMBRACON CONDOMINIOS
D
06/06
DÉB.PGTO.BOLETO INT
1.000,00
D
RESUMO
SALDO EM C.CORRENTE(+): 0,00C
"""
    _saldo_inicial, _entradas, saidas, _saldo_final = _agregar_movimentos_sicoob(texto)
    assert saidas == Decimal("6054.07")


def test_sicoob_saldo_do_dia_nao_entra_como_credito():
    texto = """
EXTRATO CONTA CORRENTE
SALDO ANTERIOR
0,00
C
100,00
C
10,00
D
56.677,02
SALDO DO DIA
C
RESUMO
SALDO EM C.CORRENTE(+): 90,00C
"""
    _saldo_inicial, entradas, saidas, saldo_final = _agregar_movimentos_sicoob(texto)
    assert entradas == Decimal("100.00")
    assert saidas == Decimal("10.00")
    assert saldo_final == Decimal("90.00")


def test_sicoob_lookahead_quando_a_equacao_fecha():
    texto = """
EXTRATO CONTA CORRENTE
SALDO ANTERIOR
0,00
C
10.000,00
C
5.054,07
06/06
DÉB.PGTO.BOLETO INT
D
RESUMO
SALDO EM C.CORRENTE(+): 4.945,93C
"""
    _saldo_inicial, entradas, saidas, saldo_final = _agregar_movimentos_sicoob(texto)
    assert entradas == Decimal("10000.00")
    assert saidas == Decimal("5054.07")
    assert saldo_final == Decimal("4945.93")


def test_sicoob_nao_pega_sigla_do_proximo_valor():
    texto = """
EXTRATO CONTA CORRENTE
31/12
SALDO ANTERIOR
0,00
C
100,00
50,00
D
RESUMO
SALDO EM C.CORRENTE(+): 0,00C
"""
    _saldo_inicial, entradas, saidas, _saldo_final = _agregar_movimentos_sicoob(texto)
    assert entradas is None
    assert saidas == Decimal("50.00")


def test_extrato_do_condominio_nao_abre_a_regiao_sicoob():
    condominio = """
Extrato
Compensado entre 01/01/2025 e 31/01/2025
Todas as contas financeiras
001 - Conta corrente Sicoob
R$ 200,15
"""
    config = carregar_config()
    paginas = [
        PaginaTexto(10, condominio, OrigemTexto.NATIVO),
        PaginaTexto(26, SNIPPET, OrigemTexto.NATIVO),
        PaginaTexto(27, "SICOOB\nOUTRA CONTA\n10,00D\n", OrigemTexto.NATIVO),
    ]
    campos = extrair_campos(paginas, [], config)
    assert campos.paginas_utilizadas == [26]
    assert campos.total_saidas == Decimal("350.00")
