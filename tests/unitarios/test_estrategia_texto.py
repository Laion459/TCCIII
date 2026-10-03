from extrato_pdf.modelos import (
    ClassificacaoPdf,
    CondicaoExperimental,
    OrigemTexto,
    PaginaTexto,
    TipoPdf,
)
from extrato_pdf.modulos.estrategia_texto import obter_texto_trabalho


def _config():
    return {"classificacao_pdf": {"min_caracteres_pagina_com_texto": 40}}


def _nativo_com_pagina_fraca():
    return [
        PaginaTexto(1, "x" * 50, OrigemTexto.NATIVO),
        PaginaTexto(2, "", OrigemTexto.NATIVO),
    ]


def test_condicao_c_nativo_aplica_ocr_na_pagina_fraca():
    classificacao = ClassificacaoPdf(TipoPdf.NATIVO, 2, 1, 50.0)

    def ocr_fn(_caminho, _config, paginas=None):
        assert list(paginas) == [2]
        return [PaginaTexto(2, "extrato lido", OrigemTexto.OCR)]

    resultado = obter_texto_trabalho(
        "x.pdf",
        _nativo_com_pagina_fraca(),
        classificacao,
        CondicaoExperimental.C,
        _config(),
        ocr_fn=ocr_fn,
    )
    assert resultado.paginas[0].origem == OrigemTexto.NATIVO
    assert resultado.paginas[1].origem == OrigemTexto.OCR
    assert resultado.paginas[1].texto == "extrato lido"


def test_falha_de_ocr_permanece_distinta_de_pagina_vazia():
    classificacao = ClassificacaoPdf(TipoPdf.HIBRIDO, 2, 1, 50.0)

    def ocr_fn(_caminho, _config, paginas=None):
        return [
            PaginaTexto(
                2,
                "",
                OrigemTexto.OCR,
                falha_ocr=True,
                erro_ocr="RuntimeError: falha de reconhecimento",
            )
        ]

    resultado = obter_texto_trabalho(
        "x.pdf",
        _nativo_com_pagina_fraca(),
        classificacao,
        CondicaoExperimental.C,
        _config(),
        ocr_fn=ocr_fn,
    )
    pagina = resultado.paginas[1]
    assert pagina.falha_ocr is True
    assert pagina.origem == OrigemTexto.OCR
    assert any("OCR falhou na página 2" in alerta for alerta in resultado.alertas)
