from pathlib import Path

from extrato_pdf.modelos import (
    CamposExtraidos,
    CondicaoExperimental,
    ResultadoProcessamento,
    ResultadoValidacao,
    StatusProcessamento,
)
from extrato_pdf.modulos.serializador import serializar_resultado
from decimal import Decimal
import json


def test_serializador_gera_tres_arquivos(tmp_path: Path):
    resultado = ResultadoProcessamento(
        id_documento="D01",
        nome_arquivo="contas 012025.pdf",
        caminho_pdf="x",
        condicao=CondicaoExperimental.C,
        classificacao=None,
        campos=CamposExtraidos(instituicao="SICOOB"),
        validacao=ResultadoValidacao(
            status_processamento=StatusProcessamento.INCOMPLETO,
            consistente=False,
            revisao_humana=True,
            tolerancia=Decimal("0.01"),
            alertas=["teste"],
        ),
        log_etapas=["etapa1"],
        versoes={"extrato_pdf": "0.1.0"},
    )
    dest = serializar_resultado(resultado, tmp_path)
    assert (dest / "resultado.json").exists()
    assert (dest / "relatorio.txt").exists()
    assert (dest / "execucao.log").exists()
    dados = json.loads((dest / "resultado.json").read_text(encoding="utf-8"))
    assert dados["validacao"]["status_processamento"] == "incompleto"
    assert dados["documento"]["id"] == "D01"
