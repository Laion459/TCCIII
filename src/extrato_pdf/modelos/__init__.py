from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class StatusProcessamento(str, Enum):
    CONSISTENTE = "consistente"
    INCONSISTENTE = "inconsistente"
    INCOMPLETO = "incompleto"
    REVISAO_NECESSARIA = "revisao_necessaria"
    NAO_PROCESSAVEL = "nao_processavel"


class TipoPdf(str, Enum):
    NATIVO = "nativo"
    ESCANEADO = "escaneado"
    HIBRIDO = "hibrido"


class OrigemTexto(str, Enum):
    NATIVO = "nativo"
    OCR = "ocr"
    COMBINADO = "combinado"


class CondicaoExperimental(str, Enum):
    A = "A"
    B = "B"
    C = "C"


def decimal_para_json(valor: Optional[Decimal]) -> Optional[float]:
    if valor is None:
        return None
    return float(valor.quantize(Decimal("0.01")))


@dataclass(frozen=True)
class PaginaTexto:
    numero: int
    texto: str
    origem: OrigemTexto


@dataclass
class ClassificacaoPdf:
    tipo: TipoPdf
    total_paginas: int
    paginas_com_texto: int
    proporcao_com_texto: float
    evidencia: str = ""


@dataclass
class PaginaPontuada:
    numero: int
    score: int
    evidencias: list[str] = field(default_factory=list)


@dataclass
class CamposExtraidos:
    instituicao: Optional[str] = None
    tipo_conta: Optional[str] = None
    periodo_inicio: Optional[str] = None
    periodo_fim: Optional[str] = None
    saldo_inicial: Optional[Decimal] = None
    total_entradas: Optional[Decimal] = None
    total_saidas: Optional[Decimal] = None
    saldo_final_informado: Optional[Decimal] = None
    ambiguidade_instituicao: bool = False
    paginas_utilizadas: list[int] = field(default_factory=list)


@dataclass
class ItemValidacao:
    regra: str
    status: str
    mensagem: str
    evidencia: str = ""


@dataclass
class ResultadoValidacao:
    status_processamento: StatusProcessamento
    consistente: bool
    revisao_humana: bool
    tolerancia: Decimal
    saldo_final_calculado: Optional[Decimal] = None
    diferenca: Optional[Decimal] = None
    itens: list[ItemValidacao] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)


@dataclass
class ResultadoProcessamento:
    id_documento: str
    nome_arquivo: str
    caminho_pdf: str
    condicao: CondicaoExperimental
    classificacao: Optional[ClassificacaoPdf]
    campos: CamposExtraidos
    validacao: ResultadoValidacao
    paginas_pontuadas: list[PaginaPontuada] = field(default_factory=list)
    versoes: dict[str, str] = field(default_factory=dict)
    parametros: dict[str, Any] = field(default_factory=dict)
    log_etapas: list[str] = field(default_factory=list)

    def para_dict(self) -> dict[str, Any]:
        v = self.validacao
        c = self.campos
        tipo_pdf = self.classificacao.tipo.value if self.classificacao else None
        qtd = self.classificacao.total_paginas if self.classificacao else None
        return {
            "documento": {
                "id": self.id_documento,
                "arquivo": self.nome_arquivo,
                "tipo_pdf": tipo_pdf,
                "quantidade_paginas": qtd,
            },
            "extrato": {
                "instituicao": c.instituicao,
                "tipo_conta": c.tipo_conta,
                "periodo": {
                    "inicio": c.periodo_inicio,
                    "fim": c.periodo_fim,
                },
            },
            "valores": {
                "saldo_inicial": decimal_para_json(c.saldo_inicial),
                "total_entradas": decimal_para_json(c.total_entradas),
                "total_saidas": decimal_para_json(c.total_saidas),
                "saldo_final_informado": decimal_para_json(c.saldo_final_informado),
                "saldo_final_calculado": decimal_para_json(v.saldo_final_calculado),
                "diferenca": decimal_para_json(v.diferenca),
            },
            "validacao": {
                "consistente": v.consistente,
                "tolerancia": decimal_para_json(v.tolerancia),
                "revisao_humana": v.revisao_humana,
                "status_processamento": v.status_processamento.value,
            },
            "alertas": list(v.alertas),
            "experimento": {
                "condicao": self.condicao.value,
                "versoes": dict(self.versoes),
                "parametros": dict(self.parametros),
                "paginas_extrato": list(c.paginas_utilizadas),
            },
        }
