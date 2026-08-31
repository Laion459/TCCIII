from __future__ import annotations

import re
from typing import Any

from extrato_pdf.modelos import PaginaPontuada, PaginaTexto


_DATA_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
_MONETARIO_RE = re.compile(r"R\$\s*[\d.]+,\d{2}|\b\d{1,3}(?:\.\d{3})*,\d{2}\b")


def _compilar_pesos(pesos: dict[str, int]) -> list[tuple[re.Pattern[str], int, str]]:
    compilados: list[tuple[re.Pattern[str], int, str]] = []
    for padrao, peso in pesos.items():
        if padrao in {"data_dd_mm_aaaa", "valor_monetario_br", "instituicao"}:
            continue
        compilados.append((re.compile(padrao, re.IGNORECASE), int(peso), padrao))
    return compilados


def pontuar_pagina(
    texto: str,
    pesos: dict[str, int],
    nomes_instituicao: list[str] | None = None,
) -> tuple[int, list[str]]:
    low = texto.lower()
    score = 0
    evidencias: list[str] = []

    for regex, peso, rotulo in _compilar_pesos(pesos):
        if regex.search(low):
            score += peso
            evidencias.append(f"{rotulo}:{peso:+d}")

    if pesos.get("data_dd_mm_aaaa") and _DATA_RE.search(texto):
        score += int(pesos["data_dd_mm_aaaa"])
        evidencias.append(f"data_dd_mm_aaaa:{int(pesos['data_dd_mm_aaaa']):+d}")

    if pesos.get("valor_monetario_br") and _MONETARIO_RE.search(texto):
        score += int(pesos["valor_monetario_br"])
        evidencias.append(f"valor_monetario_br:{int(pesos['valor_monetario_br']):+d}")

    peso_inst = int(pesos.get("instituicao", 0))
    if peso_inst and nomes_instituicao:
        for nome in nomes_instituicao:
            if nome.lower() in low:
                score += peso_inst
                evidencias.append(f"instituicao:{peso_inst:+d}")
                break

    return score, evidencias


def localizar_paginas_extrato(
    paginas: list[PaginaTexto],
    config: dict[str, Any],
) -> list[PaginaPontuada]:
    pesos = config.get("pesos_localizacao", {})
    limiar = int(config.get("limiar_localizacao", 8))
    nomes = [
        p
        for inst in config.get("instituicoes", [])
        for p in inst.get("padroes", [inst.get("nome_canonico", "")])
        if p
    ]

    pontuadas: list[PaginaPontuada] = []
    for pagina in paginas:
        score, evidencias = pontuar_pagina(pagina.texto, pesos, nomes)
        if score >= limiar:
            pontuadas.append(
                PaginaPontuada(
                    numero=pagina.numero,
                    score=score,
                    evidencias=evidencias,
                )
            )
    pontuadas.sort(key=lambda p: (-p.score, p.numero))
    return pontuadas
