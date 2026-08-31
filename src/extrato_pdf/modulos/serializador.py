from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from extrato_pdf.modelos import ResultadoProcessamento


def _stem_saida(nome_arquivo: str) -> str:
    return Path(nome_arquivo).stem


def gerar_relatorio_txt(resultado: ResultadoProcessamento) -> str:
    d = resultado.para_dict()
    linhas = [
        "Relatório de extração e validação de extrato bancário",
        f"Arquivo: {d['documento']['arquivo']}",
        f"ID: {d['documento']['id']}",
        f"Tipo PDF: {d['documento']['tipo_pdf']}",
        f"Condição experimental: {d['experimento']['condicao']}",
        f"Instituição: {d['extrato']['instituicao']}",
        f"Tipo conta: {d['extrato']['tipo_conta']}",
        f"Período: {d['extrato']['periodo']['inicio']} a {d['extrato']['periodo']['fim']}",
        f"Saldo inicial: {d['valores']['saldo_inicial']}",
        f"Total entradas: {d['valores']['total_entradas']}",
        f"Total saídas: {d['valores']['total_saidas']}",
        f"Saldo final informado: {d['valores']['saldo_final_informado']}",
        f"Saldo final calculado: {d['valores']['saldo_final_calculado']}",
        f"Diferença: {d['valores']['diferenca']}",
        f"Status: {d['validacao']['status_processamento']}",
        f"Consistente: {d['validacao']['consistente']}",
        f"Revisão humana: {d['validacao']['revisao_humana']}",
        "Alertas:",
    ]
    if d["alertas"]:
        linhas.extend(f"- {a}" for a in d["alertas"])
    else:
        linhas.append("- (nenhum)")
    return "\n".join(linhas) + "\n"


def gerar_log(resultado: ResultadoProcessamento) -> str:
    agora = datetime.now(timezone.utc).isoformat()
    linhas = [
        f"[{agora}] inicio_serializacao arquivo={resultado.nome_arquivo}",
        f"condicao={resultado.condicao.value}",
        f"versoes={json.dumps(resultado.versoes, ensure_ascii=False)}",
        f"parametros={json.dumps(resultado.parametros, ensure_ascii=False, default=str)}",
    ]
    linhas.extend(resultado.log_etapas)
    linhas.append(
        f"status_final={resultado.validacao.status_processamento.value} "
        f"alertas={len(resultado.validacao.alertas)}"
    )
    return "\n".join(linhas) + "\n"


def serializar_resultado(
    resultado: ResultadoProcessamento,
    diretorio_saida: str | Path,
) -> Path:
    base = Path(diretorio_saida) / _stem_saida(resultado.nome_arquivo)
    base.mkdir(parents=True, exist_ok=True)

    json_path = base / "resultado.json"
    txt_path = base / "relatorio.txt"
    log_path = base / "execucao.log"

    json_path.write_text(
        json.dumps(resultado.para_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    txt_path.write_text(gerar_relatorio_txt(resultado), encoding="utf-8")
    log_path.write_text(gerar_log(resultado), encoding="utf-8")
    return base
