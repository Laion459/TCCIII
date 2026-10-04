from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Optional

from extrato_pdf.modelos import (
    METODO_CABECALHO_CAIXA,
    METODO_CABECALHO_SICOOB,
    METODO_FALLBACK,
    METODO_PONTUACAO,
    CamposExtraidos,
    PaginaPontuada,
    PaginaTexto,
)
from extrato_pdf.modulos.instituicao import identificar_instituicao
from extrato_pdf.modulos.normalizador import (
    ErroNormalizacaoMonetaria,
    normalizar_monetario_br,
)
from extrato_pdf.modulos.cabecalho_composto import sem_cabecalho_composto
from extrato_pdf.modulos.parser_caixa import agregar_movimentos_caixa, texto_parece_caixa


_PERIODO_RE = re.compile(
    r"PER[IÍ]ODO\s*:\s*(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_PERIODO_ALT_RE = re.compile(
    r"Compensado entre\s*(\d{2}/\d{2}/\d{4})\s*e\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_VALOR_SIG_RE = re.compile(r"^([\d.]+,\d{2})\*?([CD])?$", re.IGNORECASE)
_VALOR_NO_FIM_RE = re.compile(r"([\d.]+,\d{2})\s*\*?([CD])\s*$", re.IGNORECASE)
_TOL_SALDO = Decimal("0.01")
_LOOKAHEAD_SIGLA = 6
_BLOQUEIA_LOOKAHEAD = ("SALDO DO DIA", "SALDO ANTERIOR", "SALDO BLOQ", "RESUMO")
_RE_NUM_US_LINHA = re.compile(r"^-?\d+\.\d{2}$", re.M)


def _data_iso(data_br: str) -> str:
    dia, mes, ano = data_br.split("/")
    return f"{ano}-{mes}-{dia}"


def _eh_cabecalho_extrato_cc(texto: str) -> bool:
    """Cabeçalho do extrato Sicoob CC (evita falso positivo do consolidado Embracon)."""
    up = texto.upper()
    if "EXTRATO DA CONTA CAPITAL" in up:
        return False
    if "EXTRATO CONSOLIDADO" in up or "CONTA FINANCEIRA" in up:
        return False
    return "EXTRATO CONTA CORRENTE" in up


def _eh_cabecalho_caixa(texto: str) -> bool:
    if not re.search(r"Extrato por per[ií]odo", texto, re.I):
        return False
    low = texto.lower()
    up = texto.upper()
    return (
        "caixa.gov" in low
        or "imprime_ext_periodo" in low
        or "CAIXA" in up
        or "Conta:" in texto
        or "Agência:" in texto
        or "Agencia:" in texto
        or "Cliente" in texto
    )


def _cortar_conta_capital(texto: str) -> str:
    corte = re.search(
        r"EXTRATO DA CONTA CAPITAL|\nRESUMO\n",
        texto,
        flags=re.IGNORECASE,
    )
    if not corte:
        return texto
    if corte.group(0).upper().strip() == "RESUMO":
        resto = texto[corte.start() :]
        capital = re.search(r"EXTRATO DA CONTA CAPITAL", resto, re.IGNORECASE)
        if capital:
            return texto[: corte.start()] + resto[: capital.start()]
        return texto[: corte.start()] + resto
    return texto[: corte.start()]


def _paginas_por_numero(paginas: list[PaginaTexto]) -> dict[int, str]:
    return {p.numero: p.texto for p in paginas}


def _candidatas(
    paginas: list[PaginaTexto],
    pontuadas: list[PaginaPontuada],
) -> list[int]:
    return [p.numero for p in pontuadas] or [p.numero for p in paginas]


def _selecionar_texto_sicoob(
    paginas: list[PaginaTexto],
    pontuadas: list[PaginaPontuada],
) -> tuple[str, list[int]] | None:
    """Prioriza páginas de extrato SICOOB conta corrente."""
    por_numero = _paginas_por_numero(paginas)
    candidatas = _candidatas(paginas, pontuadas)

    inicio = None
    for numero in sorted(candidatas):
        texto = por_numero.get(numero, "")
        if _eh_cabecalho_extrato_cc(texto):
            inicio = numero
            break
        up = texto.upper()
        if "SICOOB" in up and "EXTRATO CONTA CORRENTE" in up:
            inicio = numero
            break
        if (
            "SICOOB" in up
            and "HISTÓRICO DE MOVIMENTAÇÃO" in up.replace("HISTORICO", "HISTÓRICO")
            and "EXTRATO CONSOLIDADO" not in up
        ):
            inicio = numero
            break

    if inicio is None:
        return None

    nums: list[int] = []
    blocos: list[str] = []
    for numero in range(inicio, max(por_numero) + 1):
        texto = por_numero.get(numero, "")
        up = texto.upper()
        if numero > inicio and (
            "EXTRATO DA CONTA CAPITAL" in up
            or (up.strip().startswith("SICOOB") and "CONTA CAPITAL" in up)
        ):
            break
        if numero > inicio + 20 and "uCondo" in texto:
            break
        nums.append(numero)
        blocos.append(texto)
        if "RESUMO" in up and re.search(r"SALDO EM C\.?\s*CORRENTE", up):
            break
        if "OUVIDORIA SICOOB" in up and "SALDO EM C" in up:
            break
    texto = _cortar_conta_capital("\n".join(blocos))
    return texto, nums


def _selecionar_texto_caixa(
    paginas: list[PaginaTexto],
    pontuadas: list[PaginaPontuada],
) -> tuple[str, list[int]] | None:
    """Bloco contínuo do primeiro 'Extrato por período' Caixa."""
    por_numero = _paginas_por_numero(paginas)
    todos = sorted(por_numero)
    starts = [n for n in todos if _eh_cabecalho_caixa(por_numero.get(n, ""))]
    if not starts:
        starts = [
            n
            for n in todos
            if re.search(r"Extrato por per[ií]odo", por_numero.get(n, ""), re.I)
        ]
    if not starts:
        # fallback: candidatas pontuadas com marca Caixa
        for n in _candidatas(paginas, pontuadas):
            if texto_parece_caixa(por_numero.get(n, "")):
                starts = [n]
                break
    if not starts:
        return None

    start = starts[0]
    out = [start]
    for num in todos:
        if num <= start:
            continue
        if num > start + 6:
            break
        texto = por_numero.get(num, "")
        low = texto.lower()
        up = texto.upper()
        continua = (
            "extrato por per" in low
            or "imprime_ext_periodo" in low
            or "caixa.gov" in low
            or re.search(r"\b\d/\d\b", texto)
            or re.search(r"[\d.]+,\d{2}\s*[CD]\b", texto, re.I)
            or bool(_RE_NUM_US_LINHA.search(texto))
        )
        if continua and any(
            k in up
            for k in (
                "SALDO",
                "ENVIO PIX",
                "CRED",
                "PAG ",
                "LANÇAMENTOS",
                "LANCAMENTOS",
                "DATA",
            )
        ):
            out.append(num)
            continue
        break

    texto = "\n".join(por_numero[i] for i in out)
    return texto, out


def _selecionar_texto_regiao(
    paginas: list[PaginaTexto],
    pontuadas: list[PaginaPontuada],
) -> tuple[str, list[int], str]:
    """Escolhe região e layout: sicoob_cc | caixa_periodo | generico.

    Em PDF composto com ambos, prioriza Sicoob CC (conta operacional do piloto);
    senão Caixa 'Extrato por período'.
    """
    sicoob = _selecionar_texto_sicoob(paginas, pontuadas)
    caixa = _selecionar_texto_caixa(paginas, pontuadas)

    if sicoob is not None:
        texto, nums = sicoob
        return texto, nums, "sicoob_cc"
    if caixa is not None:
        texto, nums = caixa
        return texto, nums, "caixa_periodo"

    por_numero = _paginas_por_numero(paginas)
    nums = _candidatas(paginas, pontuadas)[:8]
    texto = "\n".join(por_numero.get(n, "") for n in nums)
    return texto, nums, "generico"


def _parse_valor_sig(
    linhas: list[str], indice: int
) -> tuple[Optional[tuple[Decimal, Optional[str]]], int]:
    if indice >= len(linhas):
        return None, indice
    linha = linhas[indice].strip()
    m = _VALOR_SIG_RE.fullmatch(linha)
    if not m:
        m2 = re.fullmatch(r"([\d.]+,\d{2})\*?([CD])", linha, re.IGNORECASE)
        if not m2:
            return None, indice
        try:
            valor = normalizar_monetario_br(m2.group(1))
        except ErroNormalizacaoMonetaria:
            return None, indice
        return (valor, m2.group(2).upper()), indice + 1

    try:
        valor = normalizar_monetario_br(m.group(1))
    except ErroNormalizacaoMonetaria:
        return None, indice
    sig = m.group(2).upper() if m.group(2) else None
    prox = indice + 1
    if sig is None and prox < len(linhas) and linhas[prox].strip().upper() in {"C", "D"}:
        sig = linhas[prox].strip().upper()
        prox += 1
    return (valor, sig), prox


def _valor_no_fim(linha: str) -> Optional[tuple[Decimal, str]]:
    """Valor e C/D no fim da linha do histórico, como o OCR de 100 DPI devolve."""
    achado = _VALOR_NO_FIM_RE.search(linha.strip())
    if not achado:
        return None
    try:
        valor = normalizar_monetario_br(achado.group(1))
    except ErroNormalizacaoMonetaria:
        return None
    return valor, achado.group(2).upper()


def _indice_coluna_valor(linhas: list[str]) -> Optional[int]:
    """OCR em coluna deixa os valores depois de uma linha só com VALOR."""
    for indice, linha in enumerate(linhas):
        if linha.strip().upper() != "VALOR":
            continue
        proximo = indice + 1
        while proximo < len(linhas) and not linhas[proximo].strip():
            proximo += 1
        if proximo < len(linhas) and _VALOR_SIG_RE.fullmatch(linhas[proximo].strip()):
            return proximo
    return None


def _ler_coluna_valor(linhas: list[str], inicio: int) -> list[tuple[Decimal, Optional[str]]]:
    valores: list[tuple[Decimal, Optional[str]]] = []
    indice = inicio
    while indice < len(linhas):
        if not linhas[indice].strip():
            indice += 1
            continue
        parsed, proximo = _parse_valor_sig(linhas, indice)
        if parsed is None:
            break
        valores.append(parsed)
        indice = proximo
    return valores


def _agregar_coluna_valor(
    valores: list[tuple[Decimal, Optional[str]]],
) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    """Separa lançamento de saldo do dia pela posição do saldo corrente."""
    saldo_inicial: Optional[Decimal] = None
    corrente: Optional[Decimal] = None
    saldo_final: Optional[Decimal] = None
    entradas = Decimal("0.00")
    saidas = Decimal("0.00")
    creditos = 0
    debitos = 0
    for valor, sigla in valores:
        if sigla not in {"C", "D"}:
            continue
        if saldo_inicial is None and sigla == "C":
            saldo_inicial = valor
            corrente = valor
            continue
        if sigla == "C" and valor == 0:
            continue
        if (
            sigla == "C"
            and corrente is not None
            and abs(corrente - valor) <= _TOL_SALDO
        ):
            saldo_final = valor
            continue
        if sigla == "C":
            entradas += valor
            creditos += 1
            corrente = (corrente or Decimal("0.00")) + valor
            continue
        saidas += valor
        debitos += 1
        corrente = (corrente or Decimal("0.00")) - valor
    return (
        saldo_inicial,
        entradas.quantize(Decimal("0.01")) if creditos else None,
        saidas.quantize(Decimal("0.01")) if debitos else None,
        saldo_final,
    )


def _sigla_a_frente(
    linhas: list[str], inicio: int
) -> tuple[Optional[str], int]:
    """C ou D algumas linhas à frente, quando o timbre da folha separou o valor."""
    limite = min(len(linhas), inicio + _LOOKAHEAD_SIGLA)
    indice = inicio
    while indice < limite:
        linha = linhas[indice].strip().upper()
        if linha in {"C", "D"}:
            return linha, indice + 1
        if any(marca in linha for marca in _BLOQUEIA_LOOKAHEAD):
            return None, inicio
        if _parse_valor_sig(linhas, indice)[0] is not None:
            return None, inicio
        indice += 1
    return None, inicio


def _equacao_fecha(
    saldo_inicial: Optional[Decimal],
    entradas: Optional[Decimal],
    saidas: Optional[Decimal],
    saldo_final: Optional[Decimal],
) -> bool:
    if None in (saldo_inicial, entradas, saidas, saldo_final):
        return False
    return abs((saldo_inicial + entradas - saidas) - saldo_final) <= _TOL_SALDO


def _agregar_movimentos_sicoob(
    texto: str, *, _lookahead: Optional[bool] = None
) -> tuple[
    Optional[Decimal],
    Optional[Decimal],
    Optional[Decimal],
    Optional[Decimal],
]:
    """Extrai saldo inicial/final e soma C/D ignorando saldos diários (piloto SICOOB)."""
    if _lookahead is None:
        estrito = _agregar_movimentos_sicoob(texto, _lookahead=False)
        if _equacao_fecha(*estrito):
            return estrito
        folgado = _agregar_movimentos_sicoob(texto, _lookahead=True)
        if _equacao_fecha(*folgado):
            return folgado
        return estrito

    texto = sem_cabecalho_composto(texto)
    texto = _cortar_conta_capital(texto)
    resumo = re.search(r"\nRESUMO\n", texto, re.IGNORECASE)
    texto_mov = texto[: resumo.start()] if resumo else texto
    texto_resumo = texto[resumo.start() :] if resumo else ""

    linhas_completas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    inicio_coluna = _indice_coluna_valor(linhas_completas)
    if inicio_coluna is not None:
        saldo_inicial, entradas, saidas, saldo_coluna = _agregar_coluna_valor(
            _ler_coluna_valor(linhas_completas, inicio_coluna)
        )
        return (
            saldo_inicial,
            entradas,
            saidas,
            saldo_coluna if saldo_coluna is not None else _saldo_final_sicoob(texto_resumo, texto_mov),
        )

    linhas = [ln.strip() for ln in texto_mov.splitlines() if ln.strip()]
    skip_hdr = ("SALDO ANTERIOR", "SALDO DO DIA", "SALDO BLOQ")
    saldo_inicial: Optional[Decimal] = None
    entradas = Decimal("0.00")
    saidas = Decimal("0.00")
    creditos = 0
    debitos = 0
    i = 0
    while i < len(linhas):
        up = linhas[i].upper()
        if any(k in up for k in skip_hdr):
            if "SALDO ANTERIOR" in up and "BLOQ" not in up:
                na_linha = _valor_no_fim(linhas[i])
                if na_linha is not None and saldo_inicial is None:
                    saldo_inicial = na_linha[0]
                    i += 1
                    continue
                j = i + 1
                while j < len(linhas):
                    parsed, j2 = _parse_valor_sig(linhas, j)
                    if parsed:
                        if saldo_inicial is None:
                            saldo_inicial = parsed[0]
                        i = j2
                        break
                    if linhas[j].strip().upper() in {"C", "D"}:
                        j += 1
                        continue
                    i = j
                    break
                else:
                    i += 1
                continue
            j = i + 1
            parsed, j2 = _parse_valor_sig(linhas, j) if j < len(linhas) else (None, j)
            i = j2 if parsed else i + 1
            continue

        parsed, j2 = _parse_valor_sig(linhas, i)
        if parsed and parsed[1] in {"C", "D"}:
            valor, sig = parsed
        elif parsed is not None and _lookahead:
            sigla, j3 = _sigla_a_frente(linhas, j2)
            if sigla is None:
                i += 1
                continue
            valor, sig = parsed[0], sigla
            j2 = j3
        else:
            no_fim = _valor_no_fim(linhas[i])
            if no_fim is None:
                i += 1
                continue
            valor, sig = no_fim
            j2 = i + 1
        if sig == "C":
            entradas += valor
            creditos += 1
        else:
            saidas += valor
            debitos += 1
        i = j2

    return (
        saldo_inicial,
        entradas.quantize(Decimal("0.01")) if creditos else None,
        saidas.quantize(Decimal("0.01")) if debitos else None,
        _saldo_final_sicoob(texto_resumo, texto_mov),
    )


def _saldo_final_sicoob(texto_resumo: str, texto_mov: str) -> Optional[Decimal]:
    saldo_final: Optional[Decimal] = None
    m_final = re.search(
        r"SALDO EM C\.?\s*CORRENTE\s*\(?\+?\)?\s*:?\s*([\d.]+,\d{2})\s*C?",
        texto_resumo or texto_mov,
        flags=re.IGNORECASE,
    )
    if m_final:
        try:
            saldo_final = normalizar_monetario_br(m_final.group(1))
        except ErroNormalizacaoMonetaria:
            saldo_final = None
    if saldo_final is not None:
        return saldo_final
    matches = list(
        re.finditer(
            r"SALDO DO DIA\s*([\d.]+,\d{2})\s*C?",
            texto_mov,
            flags=re.IGNORECASE,
        )
    )
    if not matches:
        return None
    try:
        return normalizar_monetario_br(matches[-1].group(1))
    except ErroNormalizacaoMonetaria:
        return None


def _extrair_periodo(texto: str) -> tuple[Optional[str], Optional[str]]:
    for regex in (_PERIODO_RE, _PERIODO_ALT_RE):
        m = regex.search(texto)
        if m:
            return _data_iso(m.group(1)), _data_iso(m.group(2))
    return None, None


def _metodo_localizacao(
    layout: str,
    numeros: list[int],
    pontuadas: list[PaginaPontuada],
    limiar: int,
) -> str:
    """A região continua sendo aberta pelo cabeçalho e estendida por continuidade.

    pontuacao significa que a página inicial também atingiu o limiar.
    """
    scores = {pagina.numero: pagina.score for pagina in pontuadas}
    inicio = numeros[0] if numeros else None
    abertura_pontuada = inicio is not None and scores.get(inicio, -1) >= limiar
    if layout == "generico":
        return METODO_PONTUACAO if pontuadas else METODO_FALLBACK
    if abertura_pontuada:
        return METODO_PONTUACAO
    if layout == "sicoob_cc":
        return METODO_CABECALHO_SICOOB
    if layout == "caixa_periodo":
        return METODO_CABECALHO_CAIXA
    return METODO_FALLBACK


def extrair_campos(
    paginas: list[PaginaTexto],
    pontuadas: list[PaginaPontuada],
    config: dict[str, Any],
) -> CamposExtraidos:
    texto, nums, layout = _selecionar_texto_regiao(paginas, pontuadas)
    inst = identificar_instituicao(texto, config)
    metodo = _metodo_localizacao(
        layout, nums, pontuadas, int(config.get("limiar_localizacao", 8))
    )

    saldo_inicial = total_entradas = total_saidas = saldo_final = None
    periodo_inicio = periodo_fim = None
    entradas_inferido = None
    entradas_divergem = False
    periodo_exige_revisao = False

    if layout == "caixa_periodo" or (
        layout == "generico" and texto_parece_caixa(texto)
    ):
        agregado = agregar_movimentos_caixa(texto)
        saldo_inicial = agregado.saldo_inicial
        total_entradas = agregado.total_entradas
        total_saidas = agregado.total_saidas
        saldo_final = agregado.saldo_final
        periodo_inicio = agregado.periodo_inicio
        periodo_fim = agregado.periodo_fim
        entradas_inferido = agregado.total_entradas_inferido
        entradas_divergem = agregado.entradas_divergem_identidade
        periodo_exige_revisao = agregado.periodo_exige_revisao
        if inst.nome is None and not inst.ambigua:
            inst_nome = "CAIXA"
        else:
            inst_nome = inst.nome or "CAIXA"
    elif layout == "sicoob_cc" or (
        "EXTRATO CONTA CORRENTE" in texto.upper() or "HIST" in texto.upper()
    ):
        periodo_inicio, periodo_fim = _extrair_periodo(texto)
        if "EXTRATO CONTA CORRENTE" in texto.upper() or "HIST" in texto.upper():
            saldo_inicial, total_entradas, total_saidas, saldo_final = (
                _agregar_movimentos_sicoob(texto)
            )
        inst_nome = inst.nome
    else:
        periodo_inicio, periodo_fim = _extrair_periodo(texto)
        inst_nome = inst.nome

    return CamposExtraidos(
        instituicao=inst_nome,
        tipo_conta="conta_corrente" if saldo_inicial is not None else None,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        saldo_inicial=saldo_inicial,
        total_entradas=total_entradas if total_entradas is not None else None,
        total_saidas=total_saidas if total_saidas is not None else None,
        saldo_final_informado=saldo_final,
        ambiguidade_instituicao=inst.ambigua and inst_nome is None,
        paginas_utilizadas=nums,
        total_entradas_extraido=total_entradas if total_entradas is not None else None,
        total_entradas_inferido=entradas_inferido,
        divergencia_entradas_identidade=entradas_divergem,
        periodo_exige_revisao=periodo_exige_revisao,
        metodo_localizacao=metodo,
        layout=layout,
    )
