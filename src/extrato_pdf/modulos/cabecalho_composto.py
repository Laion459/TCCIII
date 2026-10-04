"""Tira o timbre repetido em cada folha do PDF composto."""

from __future__ import annotations

import re


_CABECALHO_COMPOSTO_RE = re.compile(
    r"^(ANEXO DE CONTAS FINANCEIRAS|Per[ií]odo base:|RESID\.?\s+PORTAL|"
    r"By Condominizar|EMBRACON|CONDOMINIZAR|"
    r"\d{1,3}\s*/\s*\d{1,3}$|"
    r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}$|"
    r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$|"
    r"^1$)",
    re.IGNORECASE,
)


def sem_cabecalho_composto(texto: str) -> str:
    mantidas = []
    for linha in texto.splitlines():
        limpa = linha.strip()
        if _CABECALHO_COMPOSTO_RE.match(limpa):
            continue
        if re.fullmatch(r"\d{1,3}\s*/\s*\d{1,3}", limpa):
            continue
        mantidas.append(linha)
    return "\n".join(mantidas)


def tem_texto_util(texto: str, min_chars: int) -> bool:
    """O timbre sozinho não conta como texto da folha."""
    return len(sem_cabecalho_composto(texto).strip()) >= min_chars
