#!/usr/bin/env python
"""Executa lote de PDFs nas condições A/B/C."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from extrato_pdf.corpora import obter_corpus
from extrato_pdf.modelos import CondicaoExperimental
from extrato_pdf.pipeline import processar_pdf
from extrato_pdf.util.config import carregar_config


def _raiz() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        default=None,
        help="pdf-nativo, pdf-100-dpi, pdf-200-dpi ou pdf-300-dpi. Define entrada e saída.",
    )
    parser.add_argument("--entrada", type=Path, default=None)
    parser.add_argument("--saida", type=Path, default=None)
    parser.add_argument(
        "--condicoes",
        default="A,C",
        help="Lista separada por vírgula. Default A,C (B pode ser lento em PDFs grandes).",
    )
    args = parser.parse_args()
    raiz = _raiz()
    entrada = args.entrada
    saida = args.saida
    if args.corpus:
        corpus = obter_corpus(args.corpus)
        if entrada is None:
            entrada = raiz / "dados" / "entrada" / corpus.pasta
        if saida is None:
            saida = raiz / "resultados" / "experimentos" / corpus.id
    if entrada is None or saida is None:
        parser.error("Informe --corpus ou os dois caminhos --entrada e --saida.")
    config = carregar_config()
    pdfs = sorted(entrada.glob("*.pdf"))
    if not pdfs:
        print("Nenhum PDF encontrado")
        return 1
    for cond_txt in [c.strip().upper() for c in args.condicoes.split(",") if c.strip()]:
        cond = CondicaoExperimental(cond_txt)
        destino = saida / f"condicao_{cond.value.lower()}"
        destino.mkdir(parents=True, exist_ok=True)
        for pdf in pdfs:
            inicio = time.perf_counter()
            r = processar_pdf(pdf, config, condicao=cond, diretorio_saida=destino)
            dur = time.perf_counter() - inicio
            print(
                f"{cond.value} {pdf.name}: {r.validacao.status_processamento.value} "
                f"({dur:.1f}s)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
