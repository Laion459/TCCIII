#!/usr/bin/env python
"""Calcula métricas comparando resultados com referência manual."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from extrato_pdf.modulos.metricas import comparar_com_referencia
from extrato_pdf.util.config import carregar_config, tolerancia


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resultados", type=Path, required=True)
    parser.add_argument("--referencias", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args()

    config = carregar_config()
    tol = tolerancia(config)
    refs = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in args.referencias.glob("*.json")
        if p.name != "exemplo_formato.json"
    }
    metricas = []
    for json_path in args.resultados.rglob("resultado.json"):
        resultado = json.loads(json_path.read_text(encoding="utf-8"))
        arquivo = resultado.get("documento", {}).get("arquivo", "")
        ref = None
        for dados in refs.values():
            if dados.get("documento") == arquivo or arquivo in str(dados.get("documento")):
                ref = dados
                break
        if not ref:
            print(f"Sem referência para {arquivo}")
            continue
        m = comparar_com_referencia(resultado, ref, tol)
        m["caminho_resultado"] = str(json_path)
        metricas.append(m)

    args.saida.mkdir(parents=True, exist_ok=True)
    out = args.saida / "metricas.json"
    out.write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Métricas: {len(metricas)} registros -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
