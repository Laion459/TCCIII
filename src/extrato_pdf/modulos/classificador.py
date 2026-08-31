from __future__ import annotations

from typing import Any, Iterable

from extrato_pdf.modelos import ClassificacaoPdf, PaginaTexto, TipoPdf


def classificar_pdf(
    paginas_nativas: Iterable[PaginaTexto],
    config: dict[str, Any],
) -> ClassificacaoPdf:
    cfg = config["classificacao_pdf"]
    min_chars = int(cfg["min_caracteres_pagina_com_texto"])
    pct_nativo = float(cfg["percentual_minimo_nativo"])

    paginas = list(paginas_nativas)
    total = len(paginas)
    if total == 0:
        return ClassificacaoPdf(
            tipo=TipoPdf.ESCANEADO,
            total_paginas=0,
            paginas_com_texto=0,
            proporcao_com_texto=0.0,
            evidencia="Documento sem páginas",
        )

    com_texto = sum(1 for p in paginas if len(p.texto.strip()) >= min_chars)
    proporcao = (com_texto / total) * 100.0

    if com_texto == 0:
        tipo = TipoPdf.ESCANEADO
    elif proporcao >= pct_nativo:
        tipo = TipoPdf.NATIVO
    else:
        tipo = TipoPdf.HIBRIDO

    return ClassificacaoPdf(
        tipo=tipo,
        total_paginas=total,
        paginas_com_texto=com_texto,
        proporcao_com_texto=round(proporcao, 2),
        evidencia=(
            f"{com_texto}/{total} páginas com >= {min_chars} chars "
            f"({proporcao:.1f}%; limiar nativo {pct_nativo}%)"
        ),
    )
