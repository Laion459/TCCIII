from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from extrato_pdf.modelos import (
    ClassificacaoPdf,
    CondicaoExperimental,
    OrigemTexto,
    PaginaTexto,
    TipoPdf,
)
from extrato_pdf.modulos.extrator_ocr import extrair_texto_ocr
from extrato_pdf.util.progresso import CancelarFn, ProgressoFn


@dataclass
class ResultadoEstrategiaTexto:
    paginas: list[PaginaTexto]
    alertas: list[str]


def _executar_ocr(
    caminho: str | Path,
    config: dict[str, Any],
    ocr_fn: Optional[Callable[..., list[PaginaTexto]]],
    on_progress: Optional[ProgressoFn],
    paginas: Optional[list[int]] = None,
    deve_cancelar: Optional[CancelarFn] = None,
) -> list[PaginaTexto]:
    if ocr_fn is not None:
        if paginas is None:
            return ocr_fn(caminho, config)
        return ocr_fn(caminho, config, paginas)
    return extrair_texto_ocr(
        caminho,
        config,
        paginas=paginas,
        on_progress=on_progress,
        deve_cancelar=deve_cancelar,
    )


def obter_texto_trabalho(
    caminho: str | Path,
    paginas_nativas: list[PaginaTexto],
    classificacao: ClassificacaoPdf,
    condicao: CondicaoExperimental,
    config: dict[str, Any],
    ocr_fn: Optional[Callable[..., list[PaginaTexto]]] = None,
    on_progress: Optional[ProgressoFn] = None,
    deve_cancelar: Optional[CancelarFn] = None,
) -> ResultadoEstrategiaTexto:
    """Decide origem do texto conforme condição A/B/C e classe do PDF (DP04)."""
    alertas: list[str] = []
    min_chars = int(config["classificacao_pdf"]["min_caracteres_pagina_com_texto"])

    if condicao == CondicaoExperimental.A:
        return ResultadoEstrategiaTexto(paginas=list(paginas_nativas), alertas=alertas)

    if condicao == CondicaoExperimental.B:
        ocr_paginas = _executar_ocr(
            caminho, config, ocr_fn, on_progress, deve_cancelar=deve_cancelar
        )
        return ResultadoEstrategiaTexto(paginas=ocr_paginas, alertas=alertas)

    # Condição C
    if classificacao.tipo == TipoPdf.NATIVO:
        return ResultadoEstrategiaTexto(paginas=list(paginas_nativas), alertas=alertas)

    if classificacao.tipo == TipoPdf.ESCANEADO:
        ocr_paginas = _executar_ocr(
            caminho, config, ocr_fn, on_progress, deve_cancelar=deve_cancelar
        )
        return ResultadoEstrategiaTexto(paginas=ocr_paginas, alertas=alertas)

    # Híbrido: nativo quando suficiente; OCR nas demais (DP04)
    faltantes = [
        p.numero
        for p in paginas_nativas
        if len(p.texto.strip()) < min_chars
    ]
    mapa: dict[int, PaginaTexto] = {
        p.numero: PaginaTexto(p.numero, p.texto, OrigemTexto.NATIVO)
        for p in paginas_nativas
    }
    if faltantes:
        alertas.append(
            f"OCR aplicado em {len(faltantes)} páginas sem texto nativo suficiente"
        )
        for pagina_ocr in _executar_ocr(
            caminho,
            config,
            ocr_fn,
            on_progress,
            paginas=faltantes,
            deve_cancelar=deve_cancelar,
        ):
            mapa[pagina_ocr.numero] = PaginaTexto(
                pagina_ocr.numero,
                pagina_ocr.texto,
                OrigemTexto.OCR if pagina_ocr.texto.strip() else OrigemTexto.COMBINADO,
            )
    ordenadas = [mapa[n] for n in sorted(mapa)]
    return ResultadoEstrategiaTexto(paginas=ordenadas, alertas=alertas)
