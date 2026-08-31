import json
from pathlib import Path

import pytest

from extrato_pdf.util.config import ConfigInvalidaError, carregar_config
from extrato_pdf.web.servicos import montar_config_ui, salvar_config_ui


def test_montar_config_ui_tem_campos():
    ui = montar_config_ui()
    for chave in (
        "tolerancia_monetaria",
        "limiar_localizacao",
        "ocr_dpi",
        "tesseract_cmd",
        "instituicoes",
    ):
        assert chave in ui


def test_salvar_config_ui_persiste(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    origem = Path(__file__).resolve().parents[2] / "config" / "default.json"
    copia = tmp_path / "default.json"
    copia.write_text(origem.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(
        "extrato_pdf.web.servicos.caminho_config_padrao",
        lambda: copia,
    )

    salvar_config_ui(
        {
            "tolerancia_monetaria": "0.02",
            "limiar_localizacao": "10",
            "min_caracteres_pagina": "50",
            "percentual_minimo_nativo": "85",
            "ocr_dpi": "180",
            "ocr_workers": "2",
            "ocr_idioma": "por",
            "tesseract_cmd": "C:\\Tesseract\\tesseract.exe",
        }
    )

    dados = json.loads(copia.read_text(encoding="utf-8"))
    assert dados["tolerancia_monetaria"] == 0.02
    assert dados["limiar_localizacao"] == 10
    assert dados["classificacao_pdf"]["min_caracteres_pagina_com_texto"] == 50
    assert dados["ocr"]["workers"] == 2
    carregar_config(caminho_default=copia)


def test_salvar_config_ui_rejeita_workers_invalido(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    origem = Path(__file__).resolve().parents[2] / "config" / "default.json"
    copia = tmp_path / "default.json"
    copia.write_text(origem.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(
        "extrato_pdf.web.servicos.caminho_config_padrao",
        lambda: copia,
    )

    with pytest.raises(ConfigInvalidaError):
        salvar_config_ui(
            {
                "tolerancia_monetaria": "0.01",
                "limiar_localizacao": "8",
                "min_caracteres_pagina": "40",
                "percentual_minimo_nativo": "90",
                "ocr_dpi": "200",
                "ocr_workers": "0",
                "ocr_idioma": "por",
                "tesseract_cmd": "tesseract",
            }
        )
