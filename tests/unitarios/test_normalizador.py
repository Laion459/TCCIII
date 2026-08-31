import pytest

from extrato_pdf.modulos.normalizador import (
    ErroNormalizacaoMonetaria,
    normalizar_monetario_br,
)
from decimal import Decimal


def test_normaliza_com_milhar():
    assert normalizar_monetario_br("2.334,43") == Decimal("2334.43")


def test_normaliza_zero():
    assert normalizar_monetario_br("0,00") == Decimal("0.00")


def test_normaliza_com_rs():
    assert normalizar_monetario_br("R$ 145.991,44") == Decimal("145991.44")


def test_normaliza_invalido():
    with pytest.raises(ErroNormalizacaoMonetaria):
        normalizar_monetario_br("abc")


def test_normaliza_vazio():
    with pytest.raises(ErroNormalizacaoMonetaria):
        normalizar_monetario_br("   ")
