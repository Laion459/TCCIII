from __future__ import annotations

from pathlib import Path

import pymupdf

from extrato_pdf.modelos import OrigemTexto, PaginaTexto


def extrair_texto_nativo(caminho: str | Path) -> list[PaginaTexto]:
    """Extrai texto embutido por página via PyMuPDF (DP01)."""
    path = Path(caminho)
    doc = pymupdf.open(path)
    paginas: list[PaginaTexto] = []
    try:
        for indice in range(doc.page_count):
            texto = doc.load_page(indice).get_text("text") or ""
            paginas.append(
                PaginaTexto(
                    numero=indice + 1,
                    texto=texto,
                    origem=OrigemTexto.NATIVO,
                )
            )
    finally:
        doc.close()
    return paginas
