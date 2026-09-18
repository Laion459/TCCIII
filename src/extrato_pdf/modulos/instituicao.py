from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ResultadoInstituicao:
    nome: Optional[str]
    ambigua: bool
    evidencias: list[str]


def _preferir_por_layout(texto: str, candidatos: dict[str, str]) -> Optional[str]:
    """Em PDF composto, prioriza o banco do extrato nativo presente no texto."""
    up = texto.upper()
    if "CAIXA" in candidatos and re.search(
        r"EXTRATO POR PER[IÍ]ODO|CAIXA\.GOV",
        up,
    ):
        return "CAIXA"
    if "SICOOB" in candidatos and (
        "EXTRATO CONTA CORRENTE" in up
        or "HISTÓRICO DE MOVIMENTAÇÃO" in up
        or "HISTORICO DE MOVIMENTACAO" in up
    ):
        return "SICOOB"
    # marcadores mais fracos
    if "CAIXA" in candidatos and "SALDO DIA" in up and "SALDO ANTERIOR" in up:
        return "CAIXA"
    if "SICOOB" in candidatos and "SALDO EM C" in up:
        return "SICOOB"
    return None


def identificar_instituicao(
    texto: str,
    config: dict[str, Any],
) -> ResultadoInstituicao:
    encontrados: dict[str, str] = {}
    evidencias: list[str] = []
    for inst in config.get("instituicoes", []):
        canonico = inst.get("nome_canonico")
        if not canonico:
            continue
        for padrao in inst.get("padroes", [canonico]):
            if re.search(re.escape(padrao), texto, flags=re.IGNORECASE):
                encontrados[canonico] = padrao
                evidencias.append(padrao)
                break

    if not encontrados:
        return ResultadoInstituicao(nome=None, ambigua=False, evidencias=[])
    if len(encontrados) == 1:
        nome = next(iter(encontrados.keys()))
        return ResultadoInstituicao(nome=nome, ambigua=False, evidencias=evidencias)

    preferido = _preferir_por_layout(texto, encontrados)
    if preferido:
        return ResultadoInstituicao(
            nome=preferido,
            ambigua=False,
            evidencias=evidencias,
        )
    return ResultadoInstituicao(
        nome=None,
        ambigua=True,
        evidencias=evidencias,
    )
