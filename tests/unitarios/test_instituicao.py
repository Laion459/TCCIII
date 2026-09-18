from extrato_pdf.modulos.instituicao import identificar_instituicao
from extrato_pdf.util.config import carregar_config


def test_sicoob():
    config = carregar_config()
    r = identificar_instituicao("Extrato SICOOB CREDISC", config)
    assert r.nome == "SICOOB"
    assert r.ambigua is False


def test_caixa():
    config = carregar_config()
    r = identificar_instituicao("Extrato por período - Caixa Econômica Federal", config)
    assert r.nome == "CAIXA"
    assert r.ambigua is False


def test_composto_prefere_layout_caixa():
    config = carregar_config()
    texto = (
        "Menção a SICOOB no rodapé.\n"
        "Extrato por período\n"
        "CAIXA\n"
        "SALDO ANTERIOR\n"
        "SALDO DIA\n"
    )
    r = identificar_instituicao(texto, config)
    assert r.nome == "CAIXA"
    assert r.ambigua is False


def test_ausente():
    config = carregar_config()
    r = identificar_instituicao("Documento sem banco conhecido", config)
    assert r.nome is None
