from unittest.mock import patch

import pytest
import time

from extrato_pdf.modelos import OrigemTexto, PaginaTexto
from extrato_pdf.modulos.extrator_ocr import extrair_texto_ocr
from extrato_pdf.util.progresso import ProcessamentoCanceladoError
from extrato_pdf.web.jobs import ItemJob, Job, StatusItem, StatusJob
from extrato_pdf.web.servicos import _criar_callback_progresso, _finalizar_cancelamento


@patch("extrato_pdf.modulos.extrator_ocr.pymupdf.open")
@patch("extrato_pdf.modulos.extrator_ocr._ocr_pagina")
def test_extrair_texto_ocr_reporta_progresso(mock_ocr_pagina, mock_open, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    doc = mock_open.return_value
    doc.page_count = 3
    doc.close = lambda: None

    mock_ocr_pagina.side_effect = lambda path, n, *a: PaginaTexto(
        n, f"p{n}", OrigemTexto.OCR
    )

    eventos: list[dict] = []

    config = {"ocr": {"idioma": "por", "dpi": 200, "workers": 1}}
    extrair_texto_ocr(pdf, config, on_progress=eventos.append)

    assert len(eventos) == 4
    assert eventos[0] == {"etapa": "ocr", "concluidas": 0, "total": 3, "workers": 1}
    assert eventos[-1] == {"etapa": "ocr", "concluidas": 3, "total": 3, "workers": 1}


def test_job_percentual_com_sub_progresso():
    job = Job(
        id="x",
        tipo="lote",
        condicao="B",
        itens=[ItemJob(arquivo="a.pdf"), ItemJob(arquivo="b.pdf")],
        status=StatusJob.EXECUTANDO,
    )
    job.sub_progresso = {"concluidas": 50, "total": 100, "workers": 4}
    assert job.percentual == 25.0
    assert job.percentual_sub == 50.0


def test_callback_progresso_atualiza_job():
    job = Job(id="x", tipo="unitario", condicao="B", itens=[ItemJob(arquivo="doc.pdf")])
    item = job.itens[0]
    callback = _criar_callback_progresso(job, item)

    callback({"etapa": "ocr", "concluidas": 12, "total": 40, "workers": 4})

    assert job.etapa == "ocr"
    assert job.sub_progresso == {"concluidas": 12, "total": 40, "workers": 4}
    assert "OCR 12/40" in item.mensagem

    callback({"etapa": "parser"})
    assert job.etapa == "parser"
    assert job.sub_progresso is None


def test_callback_progresso_dispara_cancelamento():
    job = Job(id="x", tipo="unitario", condicao="B", itens=[ItemJob(arquivo="doc.pdf")])
    job.cancelar = True
    item = job.itens[0]
    callback = _criar_callback_progresso(job, item)

    with pytest.raises(ProcessamentoCanceladoError):
        callback({"etapa": "ocr", "concluidas": 1, "total": 10, "workers": 4})


def test_finalizar_cancelamento_marca_job():
    job = Job(
        id="x",
        tipo="lote",
        condicao="B",
        itens=[ItemJob(arquivo="a.pdf"), ItemJob(arquivo="b.pdf")],
        status=StatusJob.EXECUTANDO,
    )
    item = job.itens[0]
    item.status = StatusItem.PROCESSANDO
    _finalizar_cancelamento(job, item, time.perf_counter())
    assert job.status == StatusJob.CANCELADO
    assert item.status == StatusItem.CANCELADO
