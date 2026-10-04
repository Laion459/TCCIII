import json
from decimal import Decimal
from pathlib import Path

import pytest

from extrato_pdf.modelos import CondicaoExperimental, StatusProcessamento
from extrato_pdf.pipeline import processar_pdf
from extrato_pdf.util.config import carregar_config


RAIZ = Path(__file__).resolve().parents[2]
PDF = RAIZ / "dados" / "entrada" / "pdf nativo" / "contas 012025.pdf"
PDF_D04 = RAIZ / "dados" / "entrada" / "pdf nativo" / "contas 012023.pdf"


def _exigir_pdf(caminho: Path) -> None:
    if not caminho.exists():
        pytest.skip(f"PDF de fixture ausente: {caminho}")


def test_pipeline_condicao_a_jan(tmp_path: Path):
    _exigir_pdf(PDF)
    config = carregar_config()
    resultado = processar_pdf(
        PDF,
        config=config,
        condicao=CondicaoExperimental.A,
        diretorio_saida=tmp_path,
        ocr_fn=lambda *a, **k: [],
    )
    assert resultado.validacao.status_processamento == StatusProcessamento.CONSISTENTE
    assert resultado.campos.instituicao == "SICOOB"
    assert resultado.campos.saldo_inicial == Decimal("2334.43")
    assert resultado.campos.total_entradas == Decimal("145991.44")
    assert resultado.campos.total_saidas == Decimal("145783.37")
    assert resultado.campos.saldo_final_informado == Decimal("2542.50")
    assert (tmp_path / "contas 012025" / "resultado.json").exists()
    assert resultado.paginas_ocr == 0
    assert resultado.duracao_s >= 0


def test_pipeline_d04_nativo_grava_duracao_e_nao_estica_periodo(tmp_path: Path):
    _exigir_pdf(PDF_D04)
    config = carregar_config()
    resultado = processar_pdf(
        PDF_D04,
        config=config,
        condicao=CondicaoExperimental.A,
        diretorio_saida=tmp_path,
        ocr_fn=lambda *a, **k: [],
    )
    assert resultado.paginas_ocr == 0
    assert resultado.duracao_s >= 0
    assert resultado.campos.paginas_utilizadas == [8, 9]
    assert resultado.campos.periodo_inicio == "2023-01-01"
    assert resultado.campos.periodo_fim == "2023-02-20"
    assert resultado.campos.periodo_exige_revisao is False
    assert resultado.campos.saldo_inicial == Decimal("0.00")
    assert resultado.campos.total_entradas == Decimal("42775.68")
    assert resultado.campos.total_saidas == Decimal("37918.71")
    assert resultado.campos.saldo_final_informado == Decimal("4856.97")
    assert resultado.validacao.status_processamento == StatusProcessamento.CONSISTENTE
    dados = json.loads(
        (tmp_path / "contas 012023" / "resultado.json").read_text(encoding="utf-8")
    )
    assert dados["experimento"]["paginas_ocr"] == 0
    assert "duracao_s" in dados["experimento"]
