from __future__ import annotations

from decimal import Decimal
from typing import Optional

from extrato_pdf.modelos import (
    CamposExtraidos,
    ItemValidacao,
    ResultadoValidacao,
    StatusProcessamento,
)


CAMPOS_ESSENCIAIS = (
    "saldo_inicial",
    "total_entradas",
    "total_saidas",
    "saldo_final_informado",
)


def aplicar_regras(
    campos: CamposExtraidos,
    tolerancia: Decimal,
    alertas_previos: Optional[list[str]] = None,
) -> ResultadoValidacao:
    """Aplica R01–R08 e RN relevantes sobre campos já normalizados."""
    alertas = list(alertas_previos or [])
    itens: list[ItemValidacao] = []

    if campos.instituicao:
        itens.append(
            ItemValidacao("R01", "ok", "Instituição identificada", campos.instituicao)
        )
    else:
        itens.append(ItemValidacao("R01", "falha", "Instituição não identificada"))
        alertas.append("Instituição financeira não identificada")

    if campos.periodo_inicio and campos.periodo_fim:
        itens.append(
            ItemValidacao(
                "R05",
                "ok",
                "Período validado",
                f"{campos.periodo_inicio} a {campos.periodo_fim}",
            )
        )
    else:
        itens.append(ItemValidacao("R05", "falha", "Período ausente ou incompleto"))
        alertas.append("Período do extrato ausente ou incompleto")

    ausentes = [nome for nome in CAMPOS_ESSENCIAIS if getattr(campos, nome) is None]
    if ausentes:
        itens.append(
            ItemValidacao(
                "R08",
                "falha",
                "Campos obrigatórios ausentes",
                ", ".join(ausentes),
            )
        )
        return ResultadoValidacao(
            status_processamento=StatusProcessamento.INCOMPLETO,
            consistente=False,
            revisao_humana=True,
            tolerancia=tolerancia,
            itens=itens,
            alertas=alertas + [f"Campos ausentes: {', '.join(ausentes)}"],
        )

    if campos.ambiguidade_instituicao:
        alertas.append("Ambiguidade na identificação da instituição")
        return ResultadoValidacao(
            status_processamento=StatusProcessamento.REVISAO_NECESSARIA,
            consistente=False,
            revisao_humana=True,
            tolerancia=tolerancia,
            itens=itens,
            alertas=alertas,
        )

    divergencia = any("divergência" in a.lower() or "divergencia" in a.lower() for a in alertas)
    if divergencia:
        return ResultadoValidacao(
            status_processamento=StatusProcessamento.REVISAO_NECESSARIA,
            consistente=False,
            revisao_humana=True,
            tolerancia=tolerancia,
            itens=itens,
            alertas=alertas,
        )

    assert campos.saldo_inicial is not None
    assert campos.total_entradas is not None
    assert campos.total_saidas is not None
    assert campos.saldo_final_informado is not None

    calculado = (
        campos.saldo_inicial + campos.total_entradas - campos.total_saidas
    ).quantize(Decimal("0.01"))
    diferenca = (calculado - campos.saldo_final_informado).copy_abs().quantize(
        Decimal("0.01")
    )
    itens.append(
        ItemValidacao(
            "R06",
            "ok",
            "Saldo final calculado",
            str(calculado),
        )
    )

    if diferenca <= tolerancia:
        itens.append(
            ItemValidacao(
                "R07",
                "ok",
                "Diferença dentro da tolerância",
                str(diferenca),
            )
        )
        return ResultadoValidacao(
            status_processamento=StatusProcessamento.CONSISTENTE,
            consistente=True,
            revisao_humana=False,
            tolerancia=tolerancia,
            saldo_final_calculado=calculado,
            diferenca=diferenca,
            itens=itens,
            alertas=alertas,
        )

    itens.append(
        ItemValidacao(
            "R07",
            "falha",
            "Diferença fora da tolerância",
            str(diferenca),
        )
    )
    alertas.append(
        f"Saldo inconsistente: calculado={calculado} informado={campos.saldo_final_informado}"
    )
    return ResultadoValidacao(
        status_processamento=StatusProcessamento.INCONSISTENTE,
        consistente=False,
        revisao_humana=True,
        tolerancia=tolerancia,
        saldo_final_calculado=calculado,
        diferenca=diferenca,
        itens=itens,
        alertas=alertas,
    )
