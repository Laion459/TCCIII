from pathlib import Path

from extrato_pdf.cli.main import main

PDF = Path(__file__).resolve().parents[2] / "dados" / "entrada" / "contas 012025.pdf"


def test_cli_condicao_a(tmp_path: Path):
    if not PDF.exists():
        return
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
