from extrato_pdf.modelos import OrigemTexto, PaginaTexto, TipoPdf
from extrato_pdf.modulos.classificador import classificar_pdf
from extrato_pdf.util.config import carregar_config


def test_nativo():
    config = carregar_config()
    pags = [PaginaTexto(i, "x" * 50, OrigemTexto.NATIVO) for i in range(1, 6)]
    c = classificar_pdf(pags, config)
    assert c.tipo == TipoPdf.NATIVO


def test_escaneado():
    config = carregar_config()
    pags = [PaginaTexto(i, "", OrigemTexto.NATIVO) for i in range(1, 4)]
    c = classificar_pdf(pags, config)
    assert c.tipo == TipoPdf.ESCANEADO


def test_timbre_sozinho_nao_conta_como_texto():
    config = carregar_config()
    timbre = "\n".join(
        [
            "ANEXO DE CONTAS FINANCEIRAS",
            "Período base: AGO 2023",
            "RESID. PORTAL DO SANTINHO",
            "21.444.827/0001-64",
            "1",
            "EMBRACON CONDOMINIOS",
            "31/05/2024 10:47:34",
            "28 / 159",
        ]
    )
    pags = [
        PaginaTexto(1, "x" * 50, OrigemTexto.NATIVO),
        PaginaTexto(2, timbre, OrigemTexto.NATIVO),
        PaginaTexto(3, "", OrigemTexto.NATIVO),
        PaginaTexto(4, "", OrigemTexto.NATIVO),
        PaginaTexto(5, "", OrigemTexto.NATIVO),
    ]
    c = classificar_pdf(pags, config)
    assert c.paginas_com_texto == 1
    assert c.tipo == TipoPdf.HIBRIDO


def test_hibrido():
    config = carregar_config()
    pags = [
        PaginaTexto(1, "texto suficiente aqui para classificar como nativo xx", OrigemTexto.NATIVO),
        PaginaTexto(2, "", OrigemTexto.NATIVO),
        PaginaTexto(3, "", OrigemTexto.NATIVO),
        PaginaTexto(4, "", OrigemTexto.NATIVO),
        PaginaTexto(5, "", OrigemTexto.NATIVO),
    ]
    c = classificar_pdf(pags, config)
    assert c.tipo == TipoPdf.HIBRIDO
