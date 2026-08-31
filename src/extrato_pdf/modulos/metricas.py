from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional


def _quase_igual(a: Any, b: Any, tolerancia: Decimal) -> bool:
    if a is None or b is None:
        return a == b
    try:
        return abs(Decimal(str(a)) - Decimal(str(b))) <= tolerancia
    except Exception:  # noqa: BLE001
        return str(a) == str(b)


def comparar_com_referencia(
    resultado: dict[str, Any],
    referencia: dict[str, Any],
    tolerancia: Decimal = Decimal("0.01"),
) -> dict[str, Any]:
    """Compara JSON de saída com referência manual (métricas do TCC 2 §5.8)."""
    valores = resultado.get("valores", {})
    extrato = resultado.get("extrato", {})
    periodo = extrato.get("periodo", {})

    acerto_instituicao = (
        (extrato.get("instituicao") or "").upper()
        == (referencia.get("instituicao") or "").upper()
    )
    acerto_periodo = (
        periodo.get("inicio") == referencia.get("periodo_inicio")
        and periodo.get("fim") == referencia.get("periodo_fim")
    )

    def erro(campo_res: str, campo_ref: str) -> Optional[float]:
        if valores.get(campo_res) is None or referencia.get(campo_ref) is None:
            return None
        return float(
            abs(Decimal(str(valores[campo_res])) - Decimal(str(referencia[campo_ref])))
        )

    return {
        "documento": referencia.get("documento") or resultado.get("documento", {}).get("arquivo"),
        "acerto_instituicao": acerto_instituicao,
        "acerto_periodo": acerto_periodo,
        "acerto_saldo_inicial": _quase_igual(
            valores.get("saldo_inicial"),
            referencia.get("saldo_inicial"),
            tolerancia,
        ),
        "erro_entradas": erro("total_entradas", "total_entradas"),
        "erro_saidas": erro("total_saidas", "total_saidas"),
        "erro_saldo_final_informado": erro(
            "saldo_final_informado", "saldo_final_informado"
        ),
        "consistente": resultado.get("validacao", {}).get("consistente"),
        "status_processamento": resultado.get("validacao", {}).get(
            "status_processamento"
        ),
        "revisao_humana": resultado.get("validacao", {}).get("revisao_humana"),
    }


def carregar_json(caminho: Path) -> dict[str, Any]:
    return json.loads(caminho.read_text(encoding="utf-8"))
