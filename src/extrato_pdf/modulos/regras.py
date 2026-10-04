from __future__ import annotations

from decimal import Decimal
from typing import Optional

from extrato_pdf.modelos import (
    METODOS_SEM_PONTUACAO,
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
    monetarios_completos = not ausentes
    if ausentes:
        itens.append(
            ItemValidacao(
                "R08",
                "falha",
                "Campos obrigatórios ausentes",
                ", ".join(ausentes),
            )
        )
        alertas.append(f"Campos ausentes: {', '.join(ausentes)}")

    if campos.divergencia_entradas_identidade:
        alertas.append(
            "Entradas lidas divergem da identidade contábil; "
            f"extraído={campos.total_entradas} inferido={campos.total_entradas_inferido}. "
            "O valor inferido não entra na validação."
        )

    instituicao_ok = bool(campos.instituicao)
    periodo_ok = bool(campos.periodo_inicio and campos.periodo_fim)
    completo = instituicao_ok and periodo_ok and monetarios_completos

    consistente_aritmetico = False
    calculado = None
    diferenca = None
    if monetarios_completos:
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
        consistente_aritmetico = diferenca <= tolerancia
        itens.append(
            ItemValidacao("R06", "ok", "Saldo final calculado", str(calculado))
        )
        itens.append(
            ItemValidacao(
                "R07",
                "ok" if consistente_aritmetico else "falha",
                "Diferença dentro da tolerância"
                if consistente_aritmetico
                else "Diferença fora da tolerância",
                str(diferenca),
            )
        )
        if not consistente_aritmetico:
            alertas.append(
                "Saldo inconsistente: "
                f"calculado={calculado} informado={campos.saldo_final_informado}"
            )

    if campos.ambiguidade_instituicao:
        alertas.append("Ambiguidade na identificação da instituição")

    if campos.periodo_exige_revisao:
        alertas.append(
            "Período acima de 62 dias; deixa de ser um extrato mensal e exige revisão"
        )

    divergencia_textual = any(
        "divergência" in alerta.lower() or "divergencia" in alerta.lower()
        for alerta in alertas
    )
    localizacao_fraca = campos.metodo_localizacao in METODOS_SEM_PONTUACAO

    if not completo:
        status = StatusProcessamento.INCOMPLETO
    elif not consistente_aritmetico:
        status = StatusProcessamento.INCONSISTENTE
    elif (
        campos.ambiguidade_instituicao
        or divergencia_textual
        or localizacao_fraca
        or campos.periodo_exige_revisao
    ):
        status = StatusProcessamento.REVISAO_NECESSARIA
    else:
        status = StatusProcessamento.CONSISTENTE

    return ResultadoValidacao(
        status_processamento=status,
        consistente=consistente_aritmetico,
        revisao_humana=status != StatusProcessamento.CONSISTENTE,
        tolerancia=tolerancia,
        saldo_final_calculado=calculado,
        diferenca=diferenca,
        completo=completo,
        itens=itens,
        alertas=alertas,
    )
