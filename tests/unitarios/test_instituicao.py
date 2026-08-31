from extrato_pdf.modulos.instituicao import identificar_instituicao
from extrato_pdf.util.config import carregar_config


def test_sicoob():
    config = carregar_config()
    r = identificar_instituicao("Extrato SICOOB CREDISC", config)
    assert r.nome == "SICOOB"
    assert r.ambigua is False


def test_ausente():
    config = carregar_config()
    r = identificar_instituicao("Documento sem banco conhecido", config)
    assert r.nome is None
