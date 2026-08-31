from decimal import Decimal
from pathlib import Path

from extrato_pdf.modelos import CondicaoExperimental, OrigemTexto, PaginaTexto, StatusProcessamento
from extrato_pdf.pipeline import processar_pdf
from extrato_pdf.util.config import carregar_config


PDF = Path(__file__).resolve().parents[2] / "dados" / "entrada" / "contas 012025.pdf"


def test_pipeline_condicao_a_jan(tmp_path: Path):
    if not PDF.exists():
        return
    config = carregar_config()
    # OCR mock nunca chamado na condição A
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
