from unittest.mock import patch

import pytest

from extrato_pdf.modulos.extrator_ocr import (
    _resolver_workers,
    extrair_texto_ocr,
)
from extrato_pdf.modelos import OrigemTexto, PaginaTexto
from extrato_pdf.util.progresso import ProcessamentoCanceladoError
from extrato_pdf.util.config import ConfigInvalidaError, carregar_config


def test_resolver_workers_limita_por_cpu():
    import os

    config = {"ocr": {"workers": 99}}
    limite = os.cpu_count() or 4
    assert _resolver_workers(config) == min(99, max(1, limite))


def test_resolver_workers_invalido_retorna_1():
    assert _resolver_workers({"ocr": {"workers": 0}}) == 1
    assert _resolver_workers({"ocr": {"workers": "x"}}) == 1


def test_config_workers_invalido():
    config = carregar_config()
    config["ocr"]["workers"] = 0
    with pytest.raises(ConfigInvalidaError, match="ocr.workers"):
        from extrato_pdf.util.config import _validar_config

        _validar_config(config)


@patch("extrato_pdf.modulos.extrator_ocr.pymupdf.open")
@patch("extrato_pdf.modulos.extrator_ocr._ocr_pagina")
def test_extrair_texto_ocr_ordena_paginas(mock_ocr_pagina, mock_open, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    doc = mock_open.return_value
    doc.page_count = 3
    doc.close = lambda: None

    def fake_ocr(path, numero, *args):
        return PaginaTexto(numero=numero, texto=f"p{numero}", origem=OrigemTexto.OCR)

    mock_ocr_pagina.side_effect = fake_ocr

    config = {"ocr": {"idioma": "por", "dpi": 200, "workers": 3}}
    resultado = extrair_texto_ocr(pdf, config)

    assert [p.numero for p in resultado] == [1, 2, 3]
    assert mock_ocr_pagina.call_count == 3


@patch("extrato_pdf.modulos.extrator_ocr.pymupdf.open")
@patch("extrato_pdf.modulos.extrator_ocr._ocr_pagina")
def test_extrair_texto_ocr_workers_1_sequencial(mock_ocr_pagina, mock_open, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    doc = mock_open.return_value
    doc.page_count = 2
    doc.close = lambda: None

    mock_ocr_pagina.side_effect = lambda path, n, *a: PaginaTexto(
        n, f"p{n}", OrigemTexto.OCR
    )

    config = {"ocr": {"idioma": "por", "dpi": 200, "workers": 1}}
    resultado = extrair_texto_ocr(pdf, config, paginas=[2, 1])

    assert [p.numero for p in resultado] == [2, 1]
    assert mock_ocr_pagina.call_count == 2


@patch("extrato_pdf.modulos.extrator_ocr.pymupdf.open")
@patch("extrato_pdf.modulos.extrator_ocr._ocr_pagina")
def test_extrair_texto_ocr_respeita_cancelamento(mock_ocr_pagina, mock_open, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    doc = mock_open.return_value
    doc.page_count = 5
    doc.close = lambda: None

    mock_ocr_pagina.side_effect = lambda path, n, *a: PaginaTexto(
        n, f"p{n}", OrigemTexto.OCR
    )

    cancelar_apos = {"n": 0}

    def deve_cancelar() -> bool:
        return cancelar_apos["n"] >= 2

    config = {"ocr": {"idioma": "por", "dpi": 200, "workers": 1}}

    def on_progress(evento):
        if evento.get("concluidas", 0) >= 2:
            cancelar_apos["n"] = 2

    with pytest.raises(ProcessamentoCanceladoError):
        extrair_texto_ocr(
            pdf,
            config,
            on_progress=on_progress,
            deve_cancelar=deve_cancelar,
        )

    assert mock_ocr_pagina.call_count == 2
