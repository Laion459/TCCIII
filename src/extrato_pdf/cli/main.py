from __future__ import annotations

import argparse
import sys
from pathlib import Path

from extrato_pdf.modelos import CondicaoExperimental
from extrato_pdf.pipeline import processar_pdf
from extrato_pdf.util.config import carregar_config, caminho_config_padrao


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="extrato-pdf",
        description=(
            "Extrai e valida dados essenciais de extratos bancários "
            "em PDFs heterogêneos (TCC 3)."
        ),
    )
    parser.add_argument(
        "pdf",
        type=str,
        help="Caminho do PDF ou nome relativo à pasta de entrada",
    )
    parser.add_argument(
        "--condicao",
        choices=["A", "B", "C", "a", "b", "c"],
        default="C",
        help="Condição experimental A (nativo), B (OCR) ou C (integrada)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Caminho para config/default.json",
    )
    parser.add_argument(
        "--instituicoes",
        type=str,
        default=None,
        help="Caminho para config/instituicoes.json",
    )
    parser.add_argument(
        "--saida",
        type=str,
        default=None,
        help="Diretório base de saída (default: resultados/)",
    )
    parser.add_argument(
        "--entrada",
        type=str,
        default=None,
        help="Pasta de entrada usada quando o PDF não é caminho absoluto",
    )
    parser.add_argument("--id", type=str, default=None, help="ID do documento (ex.: D01)")
    return parser.parse_args(argv)


def _resolver_pdf(args: argparse.Namespace) -> Path:
    candidato = Path(args.pdf)
    if candidato.exists():
        return candidato
    raiz = Path(__file__).resolve().parents[3]
    pasta_entrada = Path(args.entrada) if args.entrada else raiz / "dados" / "entrada"
    alternativo = pasta_entrada / args.pdf
    if alternativo.exists():
        return alternativo
    raise FileNotFoundError(f"PDF não encontrado: {args.pdf}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    raiz = Path(__file__).resolve().parents[3]
    try:
        pdf = _resolver_pdf(args)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    config = carregar_config(
        Path(args.config) if args.config else caminho_config_padrao(),
        Path(args.instituicoes) if args.instituicoes else None,
    )
    saida = Path(args.saida) if args.saida else raiz / "resultados"
    condicao = CondicaoExperimental(args.condicao.upper())

    resultado = processar_pdf(
        pdf,
        config=config,
        condicao=condicao,
        diretorio_saida=saida,
        id_documento=args.id,
    )
    status = resultado.validacao.status_processamento.value
    print(
        f"{resultado.nome_arquivo}: status={status} "
        f"instituicao={resultado.campos.instituicao} "
        f"saida={saida / Path(resultado.nome_arquivo).stem}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
