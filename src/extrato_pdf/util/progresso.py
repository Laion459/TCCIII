from __future__ import annotations

from typing import Any, Callable, Optional

ProgressoFn = Callable[[dict[str, Any]], None]
CancelarFn = Callable[[], bool]


class ProcessamentoCanceladoError(Exception):
    """Processamento interrompido pelo usuário."""


ETAPAS: dict[str, str] = {
    "validacao": "Validando PDF",
    "texto_nativo": "Extraindo texto nativo",
    "classificacao": "Classificando documento",
    "ocr": "OCR",
    "localizacao": "Localizando extrato",
    "parser": "Extraindo campos",
    "regras": "Validando consistência",
    "serializacao": "Gravando resultados",
}


def verificar_cancelamento(deve_cancelar: Optional[CancelarFn]) -> None:
    if deve_cancelar and deve_cancelar():
        raise ProcessamentoCanceladoError("Cancelado pelo usuário")


def emitir(
    on_progress: Optional[ProgressoFn],
    evento: dict[str, Any],
    *,
    deve_cancelar: Optional[CancelarFn] = None,
) -> None:
    verificar_cancelamento(deve_cancelar)
    if on_progress:
        on_progress(evento)
    verificar_cancelamento(deve_cancelar)
