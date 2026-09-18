from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Optional

import pymupdf
import pytesseract
from PIL import Image

from extrato_pdf.modelos import OrigemTexto, PaginaTexto
from extrato_pdf.util.progresso import CancelarFn, ProgressoFn, emitir, verificar_cancelamento


class OcrIndisponivelError(RuntimeError):
    """Tesseract não encontrado ou não configurado."""


def configurar_tesseract(config: dict[str, Any]) -> None:
    cmd = config.get("ocr", {}).get("tesseract_cmd")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def _resolver_workers(config: dict[str, Any]) -> int:
    ocr_cfg = config.get("ocr", {})
    workers = ocr_cfg.get("workers", 1)
    if not isinstance(workers, int) or workers < 1:
        return 1
    workers = min(workers, 8)
    return min(workers, max(1, (os.cpu_count() or 4)))


def _ocr_pagina(
    caminho: Path,
    numero: int,
    idioma: str,
    dpi: int,
    tesseract_cmd: Optional[str],
) -> PaginaTexto:
    """Renderiza e OCR de uma página (abre PDF próprio - seguro para threads)."""
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    zoom = dpi / 72.0
    matriz = pymupdf.Matrix(zoom, zoom)

    doc = pymupdf.open(caminho)
    try:
        pagina = doc.load_page(numero - 1)
        pix = pagina.get_pixmap(matrix=matriz, alpha=False)
        imagem = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        try:
            texto = pytesseract.image_to_string(imagem, lang=idioma) or ""
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrIndisponivelError(
                "Tesseract não encontrado. Configure ocr.tesseract_cmd."
            ) from exc
        except Exception:  # noqa: BLE001
            texto = ""
        return PaginaTexto(numero=numero, texto=texto, origem=OrigemTexto.OCR)
    finally:
        doc.close()


def _reportar_ocr(
    on_progress: Optional[ProgressoFn],
    concluidas: int,
    total: int,
    workers: int,
    deve_cancelar: Optional[CancelarFn],
) -> None:
    emitir(
        on_progress,
        {
            "etapa": "ocr",
            "concluidas": concluidas,
            "total": total,
            "workers": workers,
        },
        deve_cancelar=deve_cancelar,
    )


def extrair_texto_ocr(
    caminho: str | Path,
    config: dict[str, Any],
    paginas: Optional[Iterable[int]] = None,
    on_progress: Optional[ProgressoFn] = None,
    deve_cancelar: Optional[CancelarFn] = None,
) -> list[PaginaTexto]:
    """OCR por página com Tesseract; renderização via PyMuPDF (DP02)."""
    verificar_cancelamento(deve_cancelar)
    configurar_tesseract(config)
    path = Path(caminho)
    ocr_cfg = config.get("ocr", {})
    idioma = ocr_cfg.get("idioma", "por")
    dpi = int(ocr_cfg.get("dpi", 200))
    tesseract_cmd = ocr_cfg.get("tesseract_cmd")
    workers = _resolver_workers(config)

    doc = pymupdf.open(path)
    try:
        if paginas is None:
            alvos = list(range(1, doc.page_count + 1))
        else:
            alvos = list(paginas)
    finally:
        doc.close()

    if not alvos:
        return []

    total = len(alvos)
    _reportar_ocr(on_progress, 0, total, workers if workers > 1 else 1, deve_cancelar)

    if workers == 1 or total == 1:
        resultados: list[PaginaTexto] = []
        for indice, numero in enumerate(alvos, start=1):
            verificar_cancelamento(deve_cancelar)
            resultados.append(_ocr_pagina(path, numero, idioma, dpi, tesseract_cmd))
            _reportar_ocr(on_progress, indice, total, 1, deve_cancelar)
        return resultados

    resultados: list[PaginaTexto] = []
    lock = threading.Lock()
    concluidas = 0
    cancelado = False
    executor = ThreadPoolExecutor(max_workers=min(workers, total))
    futuros = [
        executor.submit(_ocr_pagina, path, numero, idioma, dpi, tesseract_cmd)
        for numero in alvos
    ]
    try:
        for futuro in as_completed(futuros):
            verificar_cancelamento(deve_cancelar)
            pagina = futuro.result()
            with lock:
                concluidas += 1
                _reportar_ocr(on_progress, concluidas, total, workers, deve_cancelar)
            resultados.append(pagina)
    except Exception:
        cancelado = True
        for futuro in futuros:
            futuro.cancel()
        raise
    finally:
        executor.shutdown(wait=not cancelado, cancel_futures=cancelado)

    resultados.sort(key=lambda p: p.numero)
    return resultados
