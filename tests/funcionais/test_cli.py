from pathlib import Path

import pytest

from extrato_pdf.cli.main import main

PDF = (
    Path(__file__).resolve().parents[2]
    / "dados"
    / "entrada"
    / "pdf nativo"
    / "contas 012025.pdf"
)


def test_cli_condicao_a(tmp_path: Path):
    if not PDF.exists():
        pytest.skip(f"PDF de fixture ausente: {PDF}")
    code = main(
        [
            str(PDF),
            "--condicao",
            "A",
            "--saida",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert (tmp_path / "contas 012025" / "resultado.json").exists()
