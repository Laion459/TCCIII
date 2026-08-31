from extrato_pdf.modulos.localizador import pontuar_pagina
from extrato_pdf.util.config import carregar_config


def test_pagina_extrato_passa_limiar():
    config = carregar_config()
    texto = (
        "EXTRATO CONTA CORRENTE SICOOB saldo anterior conta corrente "
        "lançamento 01/01/2025 R$ 1.234,56 crédito débito agência"
    )
    score, evidencias = pontuar_pagina(
        texto,
        config["pesos_localizacao"],
        ["SICOOB"],
    )
    assert score >= config["limiar_localizacao"]
    assert evidencias


def test_boleto_nao_passa():
    config = carregar_config()
    texto = "Boleto NF recibo pagamento"
    score, _ = pontuar_pagina(texto, config["pesos_localizacao"], ["SICOOB"])
    assert score < config["limiar_localizacao"]


def test_conta_capital_penaliza():
    config = carregar_config()
    texto = "extrato conta capital SICOOB"
    score, evidencias = pontuar_pagina(
        texto, config["pesos_localizacao"], ["SICOOB"]
    )
    assert any("conta capital" in e for e in evidencias)
    assert score < 8 or "conta capital:-5" in evidencias
