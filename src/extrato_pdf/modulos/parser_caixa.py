"""Parser nativo do extrato Caixa 'Extrato por período' (layouts BR e US)."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from extrato_pdf.modulos.normalizador import (
    ErroNormalizacaoMonetaria,
    normalizar_monetario_br,
)


TOL = Decimal("0.01")
Q = Decimal("0.01")

_RE_CAIXA_MARCA = re.compile(
    r"Extrato por per[ií]odo|caixa\.gov\.br|imprime_ext_periodo",
    re.IGNORECASE,
)
_RE_CAIXA_CONTA = re.compile(
    r"Ag[eê]ncia:\s*(\d+)\s*/\s*Produto:\s*(\d+)\s*/\s*Conta:\s*([\d\-]+)",
    re.I,
)
_RE_CAIXA_CONTA_ALT = re.compile(
    r"Conta:\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d\-]+)",
    re.I,
)
_RE_NUM_US = re.compile(r"^-?\d+\.\d{2}$")
_RE_MES = re.compile(r"M[eê]s:\s*(\w+)/(\d{4})", re.I)
_RE_INTERVALO = re.compile(
    r"PER[IÍ]ODO\s*:\s*(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)

_MESES = {
    "janeiro": "01",
    "fevereiro": "02",
    "março": "03",
    "marco": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}


def texto_parece_caixa(texto: str) -> bool:
    return bool(_RE_CAIXA_MARCA.search(texto))


@dataclass(frozen=True)
class AgregadoCaixa:
    """Valores lidos no texto. A identidade contábil fica só como diagnóstico."""

    saldo_inicial: Optional[Decimal]
    total_entradas: Optional[Decimal]
    total_saidas: Optional[Decimal]
    saldo_final: Optional[Decimal]
    periodo_inicio: Optional[str]
    periodo_fim: Optional[str]
    total_entradas_inferido: Optional[Decimal] = None
    entradas_divergem_identidade: bool = False


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(Q, rounding=ROUND_HALF_UP)


def _cortar_lancamentos_do_dia(texto: str) -> str:
    """Remove seção de emissão posterior ao período (Lançamentos do Dia)."""
    return re.split(r"Lan[cç]amentos do Dia", texto, flags=re.I)[0]


def _iso_de_data_br(data_br: str) -> str:
    dia, mes, ano = data_br.split("/")
    return f"{ano}-{mes}-{dia}"


def _periodo_caixa(texto: str) -> tuple[Optional[str], Optional[str]]:
    intervalo = _RE_INTERVALO.search(texto)
    if intervalo:
        return _iso_de_data_br(intervalo.group(1)), _iso_de_data_br(intervalo.group(2))

    mm = _RE_MES.search(texto)
    if mm and mm.group(1).lower() in _MESES:
        ano = int(mm.group(2))
        mes = int(_MESES[mm.group(1).lower()])
        ultimo = calendar.monthrange(ano, mes)[1]
        return f"{ano:04d}-{mes:02d}-01", f"{ano:04d}-{mes:02d}-{ultimo:02d}"

    datas = re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", texto)
    if datas:
        try:
            iso = sorted(
                {
                    f"{a}-{m}-{d}"
                    for d, m, a in (x.split("/") for x in datas)
                }
            )
            return iso[0], iso[-1]
        except Exception:  # noqa: BLE001
            return None, None
    return None, None


def _agregar_caixa_br(texto: str) -> tuple[
    Optional[Decimal],
    Optional[Decimal],
    Optional[Decimal],
    Optional[Decimal],
]:
    """Layout BR: valores '1.234,56 C/D'; SI/SF por rótulo; saídas = soma dos D."""
    texto = _cortar_lancamentos_do_dia(texto)
    linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]

    si: Optional[Decimal] = None
    for i, ln in enumerate(linhas):
        if "SALDO ANTERIOR" in ln.upper():
            for j in range(i + 1, min(i + 5, len(linhas))):
                m = re.fullmatch(r"([\d.]+,\d{2})\s*C", linhas[j], re.I)
                if m:
                    try:
                        si = normalizar_monetario_br(m.group(1))
                    except ErroNormalizacaoMonetaria:
                        si = None
                    break
            break

    sf: Optional[Decimal] = None
    for i, ln in enumerate(linhas):
        if "SALDO DIA" in ln.upper():
            for j in range(i + 1, min(i + 4, len(linhas))):
                m = re.fullmatch(r"([\d.]+,\d{2})\s*C", linhas[j], re.I)
                if m:
                    try:
                        sf = normalizar_monetario_br(m.group(1))
                    except ErroNormalizacaoMonetaria:
                        sf = None
                    break

    debitos: list[Decimal] = []
    for v in re.findall(r"([\d.]+,\d{2})\s*D\b", texto):
        try:
            debitos.append(normalizar_monetario_br(v))
        except ErroNormalizacaoMonetaria:
            continue
    saidas = _q(sum(debitos, Decimal("0.00")))

    entradas = Decimal("0.00")
    i = 0
    while i < len(linhas) - 1:
        m1 = re.fullmatch(r"([\d.]+,\d{2})\s*C", linhas[i], re.I)
        m2 = re.fullmatch(r"([\d.]+,\d{2})\s*C", linhas[i + 1], re.I)
        if m1 and m2:
            prev = linhas[i - 1].upper() if i > 0 else ""
            if "SALDO" not in prev:
                try:
                    entradas += normalizar_monetario_br(m1.group(1))
                except ErroNormalizacaoMonetaria:
                    pass
                i += 2
                continue
        i += 1
    return si, _q(entradas), saidas, sf


def _diagnosticar_entradas(
    saldo_inicial: Optional[Decimal],
    entradas: Optional[Decimal],
    saidas: Optional[Decimal],
    saldo_final: Optional[Decimal],
) -> tuple[Optional[Decimal], bool]:
    """Calcula E = saídas + saldo_final − saldo_inicial sem substituir o valor lido."""
    if None in (saldo_inicial, entradas, saidas, saldo_final):
        return None, False
    inferido = _q(saidas + (saldo_final - saldo_inicial))
    return inferido, abs(entradas - inferido) > TOL


def _agregar_caixa_us(texto: str) -> tuple[
    Optional[Decimal],
    Optional[Decimal],
    Optional[Decimal],
    Optional[Decimal],
]:
    """Layout US impresso: valor e saldo em linhas '-1234.56' / '1234.56'."""
    texto = _cortar_lancamentos_do_dia(texto)
    linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    movimentos: list[tuple[Decimal, Decimal, str]] = []
    i = 0
    while i < len(linhas) - 1:
        if _RE_NUM_US.match(linhas[i]) and _RE_NUM_US.match(linhas[i + 1]):
            hist = linhas[i - 1] if i >= 1 else ""
            try:
                valor = Decimal(linhas[i]).quantize(Q)
                saldo = Decimal(linhas[i + 1]).quantize(Q)
            except Exception:  # noqa: BLE001
                i += 1
                continue
            movimentos.append((valor, saldo, hist.upper()))
            i += 2
            continue
        i += 1

    if not movimentos:
        return None, None, None, None

    entradas = Decimal("0.00")
    saidas = Decimal("0.00")
    movs_reais = [
        (v, s, h) for v, s, h in movimentos if "SALDO DIA" not in h and v != 0
    ]
    saldos_dia = [(v, s) for v, s, h in movimentos if "SALDO DIA" in h]

    for valor, _saldo, _hist in movs_reais:
        if valor > 0:
            entradas += valor
        elif valor < 0:
            saidas += -valor

    if movs_reais:
        v0, s0, _ = movs_reais[0]
        saldo_inicial = _q(s0 - v0)
    elif saldos_dia:
        saldo_inicial = saldos_dia[0][1]
    else:
        saldo_inicial = None

    saldo_final = movimentos[-1][1]
    return (
        saldo_inicial,
        _q(entradas),
        _q(saidas),
        saldo_final,
    )


def agregar_movimentos_caixa(texto: str) -> AgregadoCaixa:
    """Lê saldos e movimentos. A identidade contábil não altera total_entradas."""
    texto = _cortar_lancamentos_do_dia(texto)
    pi, pf = _periodo_caixa(texto)

    if re.search(r"[\d.]+,\d{2}\s*[CD]\b", texto, re.I):
        si, entradas, saidas, sf = _agregar_caixa_br(texto)
    else:
        si, entradas, saidas, sf = _agregar_caixa_us(texto)

    inferido, diverge = _diagnosticar_entradas(si, entradas, saidas, sf)
    return AgregadoCaixa(
        saldo_inicial=si,
        total_entradas=entradas,
        total_saidas=saidas,
        saldo_final=sf,
        periodo_inicio=pi,
        periodo_fim=pf,
        total_entradas_inferido=inferido,
        entradas_divergem_identidade=diverge,
    )
