from __future__ import annotations

from typing import Any, Optional


ETAPAS_PIPELINE: list[tuple[str, str]] = [
    ("validacao", "Validação"),
    ("texto_nativo", "Texto nativo"),
    ("classificacao", "Classificação"),
    ("ocr", "OCR"),
    ("localizacao", "Localização"),
    ("parser", "Parser"),
    ("regras", "Regras"),
    ("serializacao", "Saída"),
]

_STATUS_LABELS = {
    "consistente": "Consistente",
    "inconsistente": "Inconsistente",
    "incompleto": "Incompleto",
    "revisao_necessaria": "Revisão necessária",
    "nao_processavel": "Não processável",
}


def rotulo_status(status: str | None) -> str:
    if not status:
        return "Desconhecido"
    return _STATUS_LABELS.get(status, status.replace("_", " ").capitalize())


def classe_status(status: str | None) -> str:
    if status == "consistente":
        return "ok"
    if status in {"incompleto", "revisao_necessaria", "cancelado"}:
        return "warn"
    if status in {"inconsistente", "erro", "falha", "nao_processavel"}:
        return "err"
    return "info"


def formatar_brl(valor: float | int | None) -> str:
    if valor is None:
        return "-"
    negativo = float(valor) < 0
    absoluto = abs(float(valor))
    partes = f"{absoluto:.2f}".split(".")
    inteiro = partes[0]
    grupos: list[str] = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    formatado = ".".join(grupos) + "," + partes[1]
    return f"-R$ {formatado}" if negativo else f"R$ {formatado}"


def formatar_periodo(inicio: str | None, fim: str | None) -> str:
    if inicio and fim:
        return f"{_data_br(inicio)} → {_data_br(fim)}"
    if inicio or fim:
        return _data_br(inicio or fim or "")
    return "-"


def _data_br(iso: str) -> str:
    if not iso or len(iso) < 10:
        return iso or "-"
    ano, mes, dia = iso[:10].split("-")
    return f"{dia}/{mes}/{ano}"


def montar_equacao(dados: dict[str, Any]) -> Optional[dict[str, Any]]:
    valores = dados.get("valores", {})
    campos = ("saldo_inicial", "total_entradas", "total_saidas", "saldo_final_calculado")
    if any(valores.get(c) is None for c in campos):
        return None
    si = float(valores["saldo_inicial"])
    te = float(valores["total_entradas"])
    ts = float(valores["total_saidas"])
    calc = float(valores["saldo_final_calculado"])
    informado = valores.get("saldo_final_informado")
    diferenca = valores.get("diferenca")
    tolerancia = dados.get("validacao", {}).get("tolerancia", 0.01)
    return {
        "saldo_inicial": si,
        "total_entradas": te,
        "total_saidas": ts,
        "saldo_final_calculado": calc,
        "saldo_final_informado": float(informado) if informado is not None else None,
        "diferenca": float(diferenca) if diferenca is not None else None,
        "tolerancia": float(tolerancia),
        "dentro_tolerancia": diferenca is not None and float(diferenca) <= float(tolerancia),
    }


def montar_regras(dados: dict[str, Any]) -> list[dict[str, Any]]:
    extrato = dados.get("extrato", {})
    valores = dados.get("valores", {})
    validacao = dados.get("validacao", {})
    alertas = dados.get("alertas") or []

    instituicao = extrato.get("instituicao")
    periodo = extrato.get("periodo") or {}
    regras: list[dict[str, Any]] = []

    regras.append(
        {
            "codigo": "R01",
            "titulo": "Instituição identificada",
            "status": "ok" if instituicao else "falha",
            "evidencia": instituicao or "Não identificada",
        }
    )

    periodo_ok = bool(periodo.get("inicio") and periodo.get("fim"))
    regras.append(
        {
            "codigo": "R05",
            "titulo": "Período do extrato",
            "status": "ok" if periodo_ok else "falha",
            "evidencia": formatar_periodo(periodo.get("inicio"), periodo.get("fim")),
        }
    )

    essenciais = {
        "saldo_inicial": "Saldo inicial",
        "total_entradas": "Total entradas",
        "total_saidas": "Total saídas",
        "saldo_final_informado": "Saldo final informado",
    }
    ausentes = [rotulo for chave, rotulo in essenciais.items() if valores.get(chave) is None]
    regras.append(
        {
            "codigo": "R08",
            "titulo": "Campos obrigatórios",
            "status": "ok" if not ausentes else "falha",
            "evidencia": "Completos" if not ausentes else ", ".join(ausentes),
        }
    )

    calculado = valores.get("saldo_final_calculado")
    regras.append(
        {
            "codigo": "R06",
            "titulo": "Saldo final calculado",
            "status": "ok" if calculado is not None else "falha",
            "evidencia": formatar_brl(calculado),
        }
    )

    diferenca = valores.get("diferenca")
    tolerancia = validacao.get("tolerancia", 0.01)
    if diferenca is None:
        r07_status = "falha"
        r07_evidencia = "Diferença não calculada"
    elif float(diferenca) <= float(tolerancia):
        r07_status = "ok"
        r07_evidencia = f"{formatar_brl(diferenca)} (tol. {formatar_brl(tolerancia)})"
    else:
        r07_status = "falha"
        r07_evidencia = f"{formatar_brl(diferenca)} - fora da tolerância"
    regras.append(
        {
            "codigo": "R07",
            "titulo": "Consistência aritmética",
            "status": r07_status,
            "evidencia": r07_evidencia,
        }
    )

    if alertas:
        regras.append(
            {
                "codigo": "RN",
                "titulo": "Alertas operacionais",
                "status": "warn",
                "evidencia": "; ".join(alertas),
            }
        )

    return regras


def preparar_relatorio(dados: dict[str, Any]) -> dict[str, Any]:
    validacao = dados.get("validacao", {})
    status = validacao.get("status_processamento")
    return {
        "status": status,
        "status_label": rotulo_status(status),
        "status_class": classe_status(status),
        "equacao": montar_equacao(dados),
        "regras": montar_regras(dados),
        "paginas_extrato": dados.get("experimento", {}).get("paginas_extrato") or [],
    }
