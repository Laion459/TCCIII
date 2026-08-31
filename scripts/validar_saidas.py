#!/usr/bin/env python
"""Valida sanidade das saídas geradas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

STATUS_OK = {
    "consistente",
    "inconsistente",
    "incompleto",
    "revisao_necessaria",
    "nao_processavel",
}


def validar_pasta(pasta: Path) -> list[str]:
    erros: list[str] = []
    for json_path in pasta.rglob("resultado.json"):
        base = json_path.parent
        for nome in ("relatorio.txt", "execucao.log"):
            if not (base / nome).exists():
                erros.append(f"Falta {nome} em {base}")
        try:
            dados = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            erros.append(f"JSON inválido {json_path}: {exc}")
            continue
        status = dados.get("validacao", {}).get("status_processamento")
        if status not in STATUS_OK:
            erros.append(f"Status inválido em {json_path}: {status}")
    return erros


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pasta", type=Path, required=True)
    args = parser.parse_args()
    erros = validar_pasta(args.pasta)
    if erros:
        print("FALHAS:")
        for e in erros:
            print("-", e)
        return 1
    print("OK: saídas válidas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
