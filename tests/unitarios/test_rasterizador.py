from pathlib import Path

import pymupdf
import pytest

from extrato_pdf.corpora import CORPUS_NATIVO_ID, obter_corpus
from extrato_pdf.modulos.rasterizador import (
    RasterInvalidoError,
    gerar_corpus_rasterizado,
    rasterizar_pdf,
    validar_raster,
)


def _pdf_com_texto(destino: Path, texto: str = "SALDO 1.234,56") -> None:
    documento = pymupdf.open()
    pagina = documento.new_page(width=300, height=420)
    pagina.insert_text((72, 72), texto)
    destino.parent.mkdir(parents=True, exist_ok=True)
    documento.save(destino)
    documento.close()


def test_rasterizar_preserva_pagina_e_remove_texto(tmp_path: Path):
    origem = tmp_path / "pdf nativo" / "contas 012023.pdf"
    _pdf_com_texto(origem)
    destino = tmp_path / "pdf-100-dpi" / "contas 012023.pdf"

    rasterizar_pdf(origem, destino, 100)

    assert destino.stat().st_size > 0
    validar_raster(origem, destino)
    with pymupdf.open(origem) as original:
        assert "SALDO" in original[0].get_text()
    assert not list(destino.parent.glob("*.png"))
    assert not list(destino.parent.glob("*.jpg"))


def test_rasterizar_recusa_sobrescrever_original(tmp_path: Path):
    origem = tmp_path / "pdf nativo" / "contas 012023.pdf"
    _pdf_com_texto(origem)
    with pytest.raises(ValueError, match="original"):
        rasterizar_pdf(origem, origem, 100)


def test_lote_continua_depois_de_falha(tmp_path: Path):
    nativo = tmp_path / "pdf nativo"
    nativo.mkdir()
    _pdf_com_texto(nativo / "contas 012023.pdf")
    (nativo / "quebrado.pdf").write_bytes(b"nao e pdf")

    resumo = gerar_corpus_rasterizado(nativo, tmp_path, dpis=(100,))

    assert resumo.nativos == 2
    assert resumo.esperados == 2
    assert resumo.gerados == 1
    assert len(resumo.falhas) == 1
    assert "quebrado.pdf" in resumo.falhas[0]
    assert (tmp_path / "pdf-100-dpi" / "contas 012023.pdf").is_file()
    assert (nativo / "contas 012023.pdf").is_file()


def test_reaproveita_saida_valida(tmp_path: Path):
    nativo = tmp_path / "pdf nativo"
    _pdf_com_texto(nativo / "contas 012023.pdf")
    primeiro = gerar_corpus_rasterizado(nativo, tmp_path, dpis=(100,))
    segundo = gerar_corpus_rasterizado(nativo, tmp_path, dpis=(100,))

    assert primeiro.gerados == 1
    assert segundo.reaproveitados == 1
    assert segundo.gerados == 0


def test_corpus_nativo_aponta_para_pasta_com_espaco():
    corpus = obter_corpus(None)
    assert corpus.id == CORPUS_NATIVO_ID
    assert corpus.pasta == "pdf nativo"
    assert obter_corpus("pdf-200-dpi").dpi == 200
    with pytest.raises(ValueError):
        obter_corpus("pdf-600-dpi")


def test_saida_invalida_sem_imagem(tmp_path: Path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "saida.pdf"
    _pdf_com_texto(origem)
    _pdf_com_texto(destino, texto="")
    with pytest.raises(RasterInvalidoError):
        validar_raster(origem, destino)
