from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class ResultadoValidacaoPdf:
    valido: bool
    caminho: Path
    quantidade_paginas: int = 0
    mensagem: str = ""


def validar_pdf(caminho: str | Path) -> ResultadoValidacaoPdf:
    path = Path(caminho)
    if not path.exists():
        return ResultadoValidacaoPdf(False, path, mensagem="Arquivo não encontrado")
    if path.suffix.lower() != ".pdf":
        return ResultadoValidacaoPdf(False, path, mensagem="Extensão diferente de .pdf")
    if path.stat().st_size == 0:
        return ResultadoValidacaoPdf(False, path, mensagem="Arquivo PDF vazio")
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # noqa: BLE001 - frontera de I/O
        return ResultadoValidacaoPdf(
            False, path, mensagem=f"PDF inválido ou corrompido: {exc}"
        )
    try:
        if doc.is_encrypted and not doc.authenticate(""):
            return ResultadoValidacaoPdf(
                False, path, mensagem="PDF criptografado sem senha disponível"
            )
        qtd = doc.page_count
        if qtd <= 0:
            return ResultadoValidacaoPdf(False, path, mensagem="PDF sem páginas")
        return ResultadoValidacaoPdf(True, path, quantidade_paginas=qtd)
    finally:
        doc.close()
