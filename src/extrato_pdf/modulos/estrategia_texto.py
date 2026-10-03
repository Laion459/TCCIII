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


def _alertas_falha_ocr(paginas: list[PaginaTexto]) -> list[str]:
    return [
        f"OCR falhou na página {pagina.numero}: {pagina.erro_ocr}"
        for pagina in paginas
        if pagina.falha_ocr
    ]


def _origem_da_pagina_ocr(pagina: PaginaTexto) -> OrigemTexto:
    if pagina.falha_ocr or pagina.texto.strip():
        return OrigemTexto.OCR
    return OrigemTexto.COMBINADO


def _ocr_nas_paginas_fracas(
    caminho: str | Path,
    paginas_nativas: list[PaginaTexto],
    config: dict[str, Any],
    ocr_fn: Optional[Callable[..., list[PaginaTexto]]],
    on_progress: Optional[ProgressoFn],
    deve_cancelar: Optional[CancelarFn],
    min_chars: int,
) -> ResultadoEstrategiaTexto:
    alertas: list[str] = []
    faltantes = [
        pagina.numero
        for pagina in paginas_nativas
        if len(pagina.texto.strip()) < min_chars
    ]
    mapa: dict[int, PaginaTexto] = {
        pagina.numero: PaginaTexto(pagina.numero, pagina.texto, OrigemTexto.NATIVO)
        for pagina in paginas_nativas
    }
    if faltantes:
        alertas.append(
            f"OCR aplicado em {len(faltantes)} páginas sem texto nativo suficiente"
        )
        reconhecidas = _executar_ocr(
            caminho,
            config,
            ocr_fn,
            on_progress,
            paginas=faltantes,
            deve_cancelar=deve_cancelar,
        )
        alertas.extend(_alertas_falha_ocr(reconhecidas))
        for pagina_ocr in reconhecidas:
            mapa[pagina_ocr.numero] = PaginaTexto(
                pagina_ocr.numero,
                pagina_ocr.texto,
                _origem_da_pagina_ocr(pagina_ocr),
                falha_ocr=pagina_ocr.falha_ocr,
                erro_ocr=pagina_ocr.erro_ocr,
            )
    ordenadas = [mapa[numero] for numero in sorted(mapa)]
    return ResultadoEstrategiaTexto(paginas=ordenadas, alertas=alertas)


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
    min_chars = int(config["classificacao_pdf"]["min_caracteres_pagina_com_texto"])

    if condicao == CondicaoExperimental.A:
        return ResultadoEstrategiaTexto(paginas=list(paginas_nativas), alertas=[])

    if condicao == CondicaoExperimental.B or (
        condicao == CondicaoExperimental.C
        and classificacao.tipo == TipoPdf.ESCANEADO
    ):
        ocr_paginas = _executar_ocr(
            caminho, config, ocr_fn, on_progress, deve_cancelar=deve_cancelar
        )
        return ResultadoEstrategiaTexto(
            paginas=ocr_paginas,
            alertas=_alertas_falha_ocr(ocr_paginas),
        )

    return _ocr_nas_paginas_fracas(
        caminho,
        paginas_nativas,
        config,
        ocr_fn,
        on_progress,
        deve_cancelar,
        min_chars,
    )
