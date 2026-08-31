from decimal import Decimal

from extrato_pdf.modelos import CamposExtraidos
from extrato_pdf.modulos.regras import aplicar_regras
from extrato_pdf.modelos import StatusProcessamento


def _campos_jan() -> CamposExtraidos:
    return CamposExtraidos(
        instituicao="SICOOB",
        tipo_conta="conta_corrente",
        periodo_inicio="2025-01-01",
        periodo_fim="2025-01-31",
        saldo_inicial=Decimal("2334.43"),
        total_entradas=Decimal("145991.44"),
        total_saidas=Decimal("145783.37"),
        saldo_final_informado=Decimal("2542.50"),
    )


def test_jan_consistente():
    r = aplicar_regras(_campos_jan(), Decimal("0.01"))
    assert r.status_processamento == StatusProcessamento.CONSISTENTE
    assert r.consistente is True
    assert r.saldo_final_calculado == Decimal("2542.50")
    assert r.diferenca == Decimal("0.00")


def test_tolerancia_limite():
    c = _campos_jan()
    c.saldo_final_informado = Decimal("2542.51")
    r = aplicar_regras(c, Decimal("0.01"))
    assert r.status_processamento == StatusProcessamento.CONSISTENTE


def test_fora_tolerancia():
    c = _campos_jan()
    c.saldo_final_informado = Decimal("2542.52")
    r = aplicar_regras(c, Decimal("0.01"))
    assert r.status_processamento == StatusProcessamento.INCONSISTENTE


def test_incompleto():
    c = CamposExtraidos(instituicao="SICOOB", saldo_inicial=Decimal("1.00"))
    r = aplicar_regras(c, Decimal("0.01"))
    assert r.status_processamento == StatusProcessamento.INCOMPLETO
    assert r.revisao_humana is True


def test_revisao_ambiguidade():
    c = _campos_jan()
    c.ambiguidade_instituicao = True
    r = aplicar_regras(c, Decimal("0.01"))
    assert r.status_processamento == StatusProcessamento.REVISAO_NECESSARIA
