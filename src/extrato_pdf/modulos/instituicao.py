from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ResultadoInstituicao:
    nome: Optional[str]
    ambigua: bool
    evidencias: list[str]


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
    if len(encontrados) > 1:
        return ResultadoInstituicao(
            nome=None,
            ambigua=True,
            evidencias=evidencias,
        )
    nome = next(iter(encontrados.keys()))
    return ResultadoInstituicao(nome=nome, ambigua=False, evidencias=evidencias)
