#!/usr/bin/env python
"""Gera PDFs só com imagem a 100, 200 e 300 DPI, preservando o nome original."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from extrato_pdf.corpora import DPIS_RASTER
from extrato_pdf.modulos.rasterizador import ItemRaster, gerar_corpus_rasterizado


def _raiz() -> Path:
    return Path(__file__).resolve().parents[1]


def _imprimir_inicio(arquivo: str, dpi: int) -> None:
    print(f"… {dpi:>3} DPI  {arquivo}", flush=True)


def _imprimir_fim(item: ItemRaster) -> None:
    marca = {"gerado": "ok ", "reaproveitado": "ok ", "falha": "erro"}.get(item.status, "?  ")
    print(
        f"{marca} {item.dpi:>3} DPI  {item.arquivo}  {item.detalhe}  ({item.duracao_s:.1f}s)",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rasteriza os PDFs de dados/entrada/pdf nativo para pastas "
            "pdf-100-dpi, pdf-200-dpi e pdf-300-dpi, com o mesmo nome de arquivo."
        )
    )
    parser.add_argument(
        "--dpi",
        default=",".join(str(dpi) for dpi in DPIS_RASTER),
        help="Lista separada por vírgula. Padrão: 100,200,300.",
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="Regera mesmo quando o PDF de saída já está válido.",
    )
    args = parser.parse_args(argv)

    try:
        dpis = tuple(int(parte.strip()) for parte in args.dpi.split(",") if parte.strip())
    except ValueError:
        print("DPI inválido. Use inteiros separados por vírgula, por exemplo 100,200,300.")
        return 1
    if not dpis or any(dpi < 1 for dpi in dpis):
        print("Informe ao menos um DPI positivo.")
        return 1

    raiz = _raiz()
    entrada = raiz / "dados" / "entrada"
    nativo = entrada / "pdf nativo"
    if not nativo.is_dir():
        print(f"Pasta não encontrada: {nativo}")
        return 1

    inicio = time.perf_counter()
    resumo = gerar_corpus_rasterizado(
        pasta_nativo=nativo,
        pasta_entrada=entrada,
        dpis=dpis,
        forcar=args.forcar,
        ao_iniciar=_imprimir_inicio,
        ao_concluir=_imprimir_fim,
    )
    duracao = time.perf_counter() - inicio
    print()
    print(f"PDFs nativos:        {resumo.nativos}")
    print(f"Arquivos esperados:  {resumo.esperados}")
    print(f"Gerados agora:       {resumo.gerados}")
    print(f"Já válidos:          {resumo.reaproveitados}")
    print(f"Sucesso:             {resumo.sucesso}")
    print(f"Falhas:              {len(resumo.falhas)}")
    for falha in resumo.falhas:
        print(f"  - {falha}")
    print(f"Tempo total:         {duracao:.1f}s")
    return 1 if resumo.falhas or resumo.sucesso != resumo.esperados else 0


if __name__ == "__main__":
    sys.exit(main())
