"""Geração de relatório completo de métricas experimentais A/B/C."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from extrato_pdf.modulos.metricas import comparar_com_referencia
from extrato_pdf.web.experimentos import CONDICOES, montar_laboratorio

_CAMPOS_VALOR = (
    "saldo_inicial",
    "total_entradas",
    "total_saidas",
    "saldo_final_informado",
    "saldo_final_calculado",
    "diferenca",
)


def _quase(a: Any, b: Any, tol: Decimal) -> bool:
    if a is None or b is None:
        return a == b
    try:
        return abs(Decimal(str(a)) - Decimal(str(b))) <= tol
    except Exception:  # noqa: BLE001
        return False


def _pct(itens: list[dict[str, Any]], campo: str) -> float:
    if not itens:
        return 0.0
    return round(100 * sum(1 for i in itens if i.get(campo)) / len(itens), 1)


def _score(itens: list[dict[str, Any]], campos: tuple[str, ...]) -> float:
    if not itens:
        return 0.0
    pontos = 0.0
    for item in itens:
        pontos += sum(1 for c in campos if item.get(c)) / len(campos)
    return round(100 * pontos / len(itens), 1)


def _fmt_num(valor: Any) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, float):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(valor)


def _fmt_bool(valor: Any) -> str:
    if valor is True:
        return "✓"
    if valor is False:
        return "✗"
    return "—"


def enriquecer_comparacao(
    resultado: dict[str, Any],
    referencia: dict[str, Any],
    tolerancia: Decimal,
) -> dict[str, Any]:
    """Compara resultado × referência com campos além do painel web."""
    base = comparar_com_referencia(resultado, referencia, tolerancia)
    tol = float(tolerancia)
    erro_e = base.get("erro_entradas")
    erro_s = base.get("erro_saidas")
    erro_sf = base.get("erro_saldo_final_informado")

    base["tipo_pdf"] = resultado.get("documento", {}).get("tipo_pdf")
    base["paginas"] = resultado.get("documento", {}).get("quantidade_paginas")
    base["instituicao_extraida"] = resultado.get("extrato", {}).get("instituicao")
    base["periodo_extraido"] = resultado.get("extrato", {}).get("periodo")
    base["valores"] = dict(resultado.get("valores") or {})
    base["ref_valores"] = {
        "saldo_inicial": referencia.get("saldo_inicial"),
        "total_entradas": referencia.get("total_entradas"),
        "total_saidas": referencia.get("total_saidas"),
        "saldo_final_informado": referencia.get("saldo_final_informado"),
        "periodo_inicio": referencia.get("periodo_inicio"),
        "periodo_fim": referencia.get("periodo_fim"),
        "instituicao": referencia.get("instituicao"),
    }
    base["acerto_entradas"] = erro_e is not None and erro_e <= tol
    base["acerto_saidas"] = erro_s is not None and erro_s <= tol
    base["acerto_saldo_final"] = erro_sf is not None and erro_sf <= tol
    base["acerto_campos_essenciais"] = all(
        [
            base.get("acerto_instituicao"),
            base.get("acerto_periodo"),
            base.get("acerto_saldo_inicial"),
            base["acerto_entradas"],
            base["acerto_saidas"],
            base["acerto_saldo_final"],
        ]
    )
    return base


def _carregar_refs(pasta_refs: Path) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    if not pasta_refs.exists():
        return refs
    for path in pasta_refs.glob("*.json"):
        if path.name == "exemplo_formato.json" or path.name.startswith("_"):
            continue
        dados = json.loads(path.read_text(encoding="utf-8"))
        doc = dados.get("documento")
        if not doc:
            continue
        refs[str(doc)] = dados
    return refs


def _carregar_condicao(pasta_experimentos: Path, cond: str) -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    pasta = pasta_experimentos / f"condicao_{cond.lower()}"
    if not pasta.exists():
        return docs
    for json_path in pasta.rglob("resultado.json"):
        try:
            dados = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        arq = dados.get("documento", {}).get("arquivo", json_path.parent.name)
        docs[arq] = dados
    return docs


def _media_erro(itens: list[dict[str, Any]], campo: str) -> float | None:
    vals = [i[campo] for i in itens if i.get(campo) is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def montar_consolidado(
    pasta_experimentos: Path,
    pasta_refs: Path,
    tolerancia: Decimal,
) -> dict[str, Any]:
    """Monta consolidado completo (mais rico que o painel)."""
    refs = _carregar_refs(pasta_refs)
    docs_por_cond = {c: _carregar_condicao(pasta_experimentos, c) for c in CONDICOES}
    metricas: list[dict[str, Any]] = []
    por_condicao: dict[str, Any] = {}

    for cond, docs in docs_por_cond.items():
        status = Counter(
            d.get("validacao", {}).get("status_processamento", "?") for d in docs.values()
        )
        total = sum(status.values())
        taxa = round(100 * status.get("consistente", 0) / total, 1) if total else 0.0
        tipos = Counter(d.get("documento", {}).get("tipo_pdf") for d in docs.values())
        por_condicao[cond] = {
            "total": total,
            "por_status": dict(status),
            "taxa_consistente": taxa,
            "tipos_pdf": {k: v for k, v in tipos.items() if k},
        }

    divergencias: list[dict[str, Any]] = []
    arqs_ac = sorted(set(docs_por_cond["A"]) | set(docs_por_cond["C"]))
    for arq in arqs_ac:
        a = docs_por_cond["A"].get(arq)
        c = docs_por_cond["C"].get(arq)
        if not a or not c:
            divergencias.append({"documento": arq, "motivo": "faltando"})
            continue
        sa = a.get("validacao", {}).get("status_processamento")
        sc = c.get("validacao", {}).get("status_processamento")
        va, vc = a.get("valores", {}), c.get("valores", {})
        same = all(_quase(va.get(k), vc.get(k), tolerancia) for k in _CAMPOS_VALOR)
        if sa != sc or not same:
            divergencias.append(
                {
                    "documento": arq,
                    "tipo_pdf": a.get("documento", {}).get("tipo_pdf"),
                    "status_a": sa,
                    "status_c": sc,
                    "valores_a": {k: va.get(k) for k in _CAMPOS_VALOR},
                    "valores_c": {k: vc.get(k) for k in _CAMPOS_VALOR},
                }
            )

    itens_por_cond: dict[str, list[dict[str, Any]]] = {c: [] for c in CONDICOES}
    for cond, docs in docs_por_cond.items():
        for arq, res in sorted(docs.items()):
            ref = refs.get(arq)
            if not ref:
                for dados in refs.values():
                    if dados.get("documento") == arq or arq in str(dados.get("documento", "")):
                        ref = dados
                        break
            if not ref:
                continue
            item = enriquecer_comparacao(res, ref, tolerancia)
            item["condicao"] = cond
            itens_por_cond[cond].append(item)
            metricas.append(
                {k: v for k, v in item.items() if k not in {"valores", "ref_valores"}}
            )

        itens = itens_por_cond[cond]
        por_condicao[cond]["vs_referencia"] = {
            "n": len(itens),
            "score4_web": _score(
                itens,
                ("acerto_instituicao", "acerto_periodo", "acerto_saldo_inicial", "consistente"),
            ),
            "score6_campos": _score(
                itens,
                (
                    "acerto_instituicao",
                    "acerto_periodo",
                    "acerto_saldo_inicial",
                    "acerto_entradas",
                    "acerto_saidas",
                    "acerto_saldo_final",
                ),
            ),
            "pct_acerto_completo": _pct(itens, "acerto_campos_essenciais"),
            "pct_instituicao": _pct(itens, "acerto_instituicao"),
            "pct_periodo": _pct(itens, "acerto_periodo"),
            "pct_saldo_inicial": _pct(itens, "acerto_saldo_inicial"),
            "pct_entradas": _pct(itens, "acerto_entradas"),
            "pct_saidas": _pct(itens, "acerto_saidas"),
            "pct_saldo_final": _pct(itens, "acerto_saldo_final"),
            "pct_consistente": _pct(itens, "consistente"),
            "media_erro_entradas": _media_erro(itens, "erro_entradas"),
            "media_erro_saidas": _media_erro(itens, "erro_saidas"),
            "media_erro_saldo_final": _media_erro(itens, "erro_saldo_final_informado"),
            "status": dict(Counter(i.get("status_processamento") for i in itens)),
        }

    inventario = []
    for arq, res in sorted(docs_por_cond["A"].items()):
        val = res.get("valores", {})
        inventario.append(
            {
                "arquivo": arq,
                "tipo": res.get("documento", {}).get("tipo_pdf"),
                "paginas": res.get("documento", {}).get("quantidade_paginas"),
                "status_a": res.get("validacao", {}).get("status_processamento"),
                "status_b": docs_por_cond["B"]
                .get(arq, {})
                .get("validacao", {})
                .get("status_processamento"),
                "status_c": docs_por_cond["C"]
                .get(arq, {})
                .get("validacao", {})
                .get("status_processamento"),
                "instituicao": res.get("extrato", {}).get("instituicao"),
                "diferenca": val.get("diferenca"),
                "acerto_completo_a": next(
                    (
                        m["acerto_campos_essenciais"]
                        for m in metricas
                        if m.get("condicao") == "A" and m.get("documento") == arq
                    ),
                    None,
                ),
                "acerto_completo_b": next(
                    (
                        m["acerto_campos_essenciais"]
                        for m in metricas
                        if m.get("condicao") == "B" and m.get("documento") == arq
                    ),
                    None,
                ),
                "acerto_completo_c": next(
                    (
                        m["acerto_campos_essenciais"]
                        for m in metricas
                        if m.get("condicao") == "C" and m.get("documento") == arq
                    ),
                    None,
                ),
            }
        )

    laboratorio = montar_laboratorio(
        [{k: v for k, v in m.items() if k not in {"valores", "ref_valores"}} for m in metricas],
        pasta_experimentos,
    )

    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "tolerancia": float(tolerancia),
        "qtd_referencias": len(refs),
        "por_condicao": por_condicao,
        "divergencias_a_c": divergencias,
        "metricas": metricas,
        "itens_detalhados": {
            cond: itens_por_cond[cond] for cond in CONDICOES
        },
        "inventario": inventario,
        "laboratorio": laboratorio,
    }


def _tabela_markdown(headers: list[str], rows: list[list[str]]) -> str:
    linhas = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        linhas.append("| " + " | ".join(row) + " |")
    return "\n".join(linhas)


def formatar_relatorio_markdown(consolidado: dict[str, Any]) -> str:
    """Texto Markdown completo, além do que o painel exibe."""
    lab = consolidado.get("laboratorio") or {}
    hip = lab.get("hipotese") or {}
    por = consolidado.get("por_condicao") or {}
    linhas: list[str] = []

    def h(nivel: int, texto: str) -> None:
        linhas.append(f"{'#' * nivel} {texto}")
        linhas.append("")

    def p(texto: str = "") -> None:
        linhas.append(texto)

    h(1, "Relatório completo de métricas experimentais")
    p(f"**Gerado em:** {consolidado.get('gerado_em', '—')}")
    p(f"**Tolerância monetária:** R$ {_fmt_num(consolidado.get('tolerancia'))}")
    p(f"**Referências manuais:** {consolidado.get('qtd_referencias', 0)}")
    p("")
    p(
        "Este relatório consolida o corpus A/B/C, métricas vs. referência manual, "
        "divergências A×C, inventário documental e tabelas detalhadas — "
        "incluindo campos e agregados não exibidos no painel web."
    )
    p("")

    # Hipótese
    h(2, "1. Hipótese do TCC")
    p(f"**Enunciado:** {hip.get('texto', 'Condição C ≥ A e C ≥ B')}")
    p(f"**Veredito:** `{hip.get('veredito', 'indeterminado')}`")
    scores = hip.get("scores") or {}
    p("")
    p(
        _tabela_markdown(
            ["Condição", "Score parcial (%)", "C ≥ condição?"],
            [
                ["A", _fmt_num(scores.get("A")), "—"],
                ["B", _fmt_num(scores.get("B")), "—"],
                [
                    "C",
                    _fmt_num(scores.get("C")),
                    f"≥A: {_fmt_bool(hip.get('c_maior_igual_a'))} · "
                    f"≥B: {_fmt_bool(hip.get('c_maior_igual_b'))}",
                ],
            ],
        )
    )
    p("")

    # Corpus operacional
    h(2, "2. Corpus operacional por condição")
    rows_corp = []
    for cond in CONDICOES:
        info = por.get(cond, {})
        st = info.get("por_status") or {}
        tipos = info.get("tipos_pdf") or {}
        rows_corp.append(
            [
                cond,
                str(info.get("total", 0)),
                _fmt_num(info.get("taxa_consistente")),
                str(st.get("consistente", 0)),
                str(st.get("inconsistente", 0)),
                str(st.get("incompleto", 0)),
                str(st.get("revisao_necessaria", 0)),
                str(st.get("nao_processavel", 0)),
                ", ".join(f"{k}:{v}" for k, v in sorted(tipos.items())) or "—",
            ]
        )
    p(
        _tabela_markdown(
            [
                "Cond.",
                "N",
                "Taxa cons. %",
                "Consistente",
                "Inconsistente",
                "Incompleto",
                "Revisão",
                "Não processável",
                "Tipos PDF",
            ],
            rows_corp,
        )
    )
    p("")

    # Vs referência
    h(2, "3. Métricas vs. referência manual")
    p(
        "Score 4 (painel): instituição, período, saldo inicial, consistente.  \n"
        "Score 6 (completo): + entradas, saídas e saldo final.  \n"
        "Acerto completo: todos os 6 campos essenciais corretos."
    )
    p("")
    rows_ref = []
    for cond in CONDICOES:
        vr = (por.get(cond) or {}).get("vs_referencia") or {}
        rows_ref.append(
            [
                cond,
                str(vr.get("n", 0)),
                _fmt_num(vr.get("score4_web")),
                _fmt_num(vr.get("score6_campos")),
                _fmt_num(vr.get("pct_acerto_completo")),
                _fmt_num(vr.get("pct_instituicao")),
                _fmt_num(vr.get("pct_periodo")),
                _fmt_num(vr.get("pct_saldo_inicial")),
                _fmt_num(vr.get("pct_entradas")),
                _fmt_num(vr.get("pct_saidas")),
                _fmt_num(vr.get("pct_saldo_final")),
                _fmt_num(vr.get("pct_consistente")),
                _fmt_num(vr.get("media_erro_entradas")),
                _fmt_num(vr.get("media_erro_saidas")),
                _fmt_num(vr.get("media_erro_saldo_final")),
            ]
        )
    p(
        _tabela_markdown(
            [
                "Cond.",
                "N",
                "Score4",
                "Score6",
                "Completo %",
                "Inst. %",
                "Período %",
                "SI %",
                "Entr. %",
                "Saíd. %",
                "SF %",
                "Cons. %",
                "Méd.err E",
                "Méd.err S",
                "Méd.err SF",
            ],
            rows_ref,
        )
    )
    p("")

    # Comparativo lado a lado
    h(2, "4. Comparativo agregado A × B × C")
    metricas_cmp = [
        ("Taxa consistente (corpus) %", "taxa_consistente", False),
        ("Score 4 (web) %", "score4_web", True),
        ("Score 6 (campos) %", "score6_campos", True),
        ("Acerto completo %", "pct_acerto_completo", True),
        ("Instituição %", "pct_instituicao", True),
        ("Período %", "pct_periodo", True),
        ("Saldo inicial %", "pct_saldo_inicial", True),
        ("Entradas %", "pct_entradas", True),
        ("Saídas %", "pct_saidas", True),
        ("Saldo final %", "pct_saldo_final", True),
        ("Consistente (ref) %", "pct_consistente", True),
    ]
    rows_cmp = []
    for rotulo, chave, via_ref in metricas_cmp:
        vals = []
        for cond in CONDICOES:
            info = por.get(cond) or {}
            if via_ref:
                vals.append(_fmt_num((info.get("vs_referencia") or {}).get(chave)))
            else:
                vals.append(_fmt_num(info.get(chave)))
        melhor = max(
            (
                (
                    float(
                        (
                            (por.get(c) or {}).get("vs_referencia") or {}
                            if via_ref
                            else (por.get(c) or {})
                        ).get(chave)
                        or 0
                    ),
                    c,
                )
                for c in CONDICOES
            ),
            default=(0, "—"),
        )
        rows_cmp.append([rotulo, *vals, melhor[1]])
    p(_tabela_markdown(["Métrica", "A", "B", "C", "Melhor"], rows_cmp))
    p("")

    # Divergências A×C
    h(2, "5. Divergências A × C")
    divs = consolidado.get("divergencias_a_c") or []
    if not divs:
        p("Nenhuma divergência de status ou valores entre A e C.")
        p("")
    else:
        p(f"**Total:** {len(divs)} documento(s).")
        p("")
        for d in divs:
            if d.get("motivo") == "faltando":
                p(f"- `{d.get('documento')}` — resultado ausente em A ou C")
                continue
            p(
                f"- `{d.get('documento')}` ({d.get('tipo_pdf') or '?'}) — "
                f"status A=`{d.get('status_a')}` / C=`{d.get('status_c')}`"
            )
            va, vc = d.get("valores_a") or {}, d.get("valores_c") or {}
            for k in _CAMPOS_VALOR:
                if va.get(k) != vc.get(k):
                    p(f"  - {k}: A={_fmt_num(va.get(k))} · C={_fmt_num(vc.get(k))}")
        p("")

    # Heatmap
    h(2, "6. Heatmap documento × condição (status)")
    heat = lab.get("heatmap") or []
    if heat:
        p(
            _tabela_markdown(
                ["Documento", "A", "B", "C"],
                [
                    [
                        hrow.get("documento", "—"),
                        str(hrow.get("A") or "—"),
                        str(hrow.get("B") or "—"),
                        str(hrow.get("C") or "—"),
                    ]
                    for hrow in heat
                ],
            )
        )
    else:
        p("Sem documentos no corpus.")
    p("")

    # Inventário
    h(2, "7. Inventário documental")
    inv = consolidado.get("inventario") or []
    if inv:
        p(
            _tabela_markdown(
                [
                    "Arquivo",
                    "Tipo",
                    "Págs",
                    "Inst.",
                    "St A",
                    "St B",
                    "St C",
                    "Δ",
                    "Compl. A",
                    "Compl. B",
                    "Compl. C",
                ],
                [
                    [
                        i.get("arquivo", "—"),
                        str(i.get("tipo") or "—"),
                        str(i.get("paginas") or "—"),
                        str(i.get("instituicao") or "—"),
                        str(i.get("status_a") or "—"),
                        str(i.get("status_b") or "—"),
                        str(i.get("status_c") or "—"),
                        _fmt_num(i.get("diferenca")),
                        _fmt_bool(i.get("acerto_completo_a")),
                        _fmt_bool(i.get("acerto_completo_b")),
                        _fmt_bool(i.get("acerto_completo_c")),
                    ]
                    for i in inv
                ],
            )
        )
    else:
        p("Inventário vazio.")
    p("")

    # Falhas
    h(2, "8. Casos com falha (acerto completo = não)")
    falhas_por_cond: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in consolidado.get("metricas") or []:
        if not m.get("acerto_campos_essenciais"):
            falhas_por_cond[m.get("condicao") or "?"].append(m)

    for cond in CONDICOES:
        falhas = falhas_por_cond.get(cond, [])
        h(3, f"Condição {cond} — {len(falhas)} falha(s)")
        if not falhas:
            p("Nenhuma.")
            p("")
            continue
        p(
            _tabela_markdown(
                [
                    "Documento",
                    "Tipo",
                    "Status",
                    "Inst",
                    "Per",
                    "SI",
                    "E",
                    "S",
                    "SF",
                    "err E",
                    "err S",
                    "err SF",
                ],
                [
                    [
                        f.get("documento", "—"),
                        str(f.get("tipo_pdf") or "—"),
                        str(f.get("status_processamento") or "—"),
                        _fmt_bool(f.get("acerto_instituicao")),
                        _fmt_bool(f.get("acerto_periodo")),
                        _fmt_bool(f.get("acerto_saldo_inicial")),
                        _fmt_bool(f.get("acerto_entradas")),
                        _fmt_bool(f.get("acerto_saidas")),
                        _fmt_bool(f.get("acerto_saldo_final")),
                        _fmt_num(f.get("erro_entradas")),
                        _fmt_num(f.get("erro_saidas")),
                        _fmt_num(f.get("erro_saldo_final_informado")),
                    ]
                    for f in falhas
                ],
            )
        )
        p("")

    # Detalhe completo por condição
    h(2, "9. Tabela detalhada por documento e condição")
    p(
        "Inclui acertos de campos monetários, erros absolutos e status — "
        "mais campos do que a tabela do painel."
    )
    p("")
    for cond in CONDICOES:
        itens = (consolidado.get("itens_detalhados") or {}).get(cond) or []
        h(3, f"Condição {cond} ({len(itens)} comparação(ões))")
        if not itens:
            p("Sem comparações com referência.")
            p("")
            continue
        p(
            _tabela_markdown(
                [
                    "Documento",
                    "Tipo",
                    "Status",
                    "Inst",
                    "Per",
                    "SI",
                    "E",
                    "S",
                    "SF",
                    "Cons.",
                    "Completo",
                    "err E",
                    "err S",
                    "err SF",
                ],
                [
                    [
                        i.get("documento", "—"),
                        str(i.get("tipo_pdf") or "—"),
                        str(i.get("status_processamento") or "—"),
                        _fmt_bool(i.get("acerto_instituicao")),
                        _fmt_bool(i.get("acerto_periodo")),
                        _fmt_bool(i.get("acerto_saldo_inicial")),
                        _fmt_bool(i.get("acerto_entradas")),
                        _fmt_bool(i.get("acerto_saidas")),
                        _fmt_bool(i.get("acerto_saldo_final")),
                        _fmt_bool(i.get("consistente")),
                        _fmt_bool(i.get("acerto_campos_essenciais")),
                        _fmt_num(i.get("erro_entradas")),
                        _fmt_num(i.get("erro_saidas")),
                        _fmt_num(i.get("erro_saldo_final_informado")),
                    ]
                    for i in itens
                ],
            )
        )
        p("")

        # Valores extraídos × referência nos incompletos/falhas
        detalhe_vals = [
            i
            for i in itens
            if not i.get("acerto_campos_essenciais") or i.get("status_processamento") != "consistente"
        ]
        if detalhe_vals:
            h(4, f"Valores extraídos × referência (falhas/não consistentes) — {cond}")
            for i in detalhe_vals:
                val = i.get("valores") or {}
                refv = i.get("ref_valores") or {}
                p(f"**`{i.get('documento')}`** · status=`{i.get('status_processamento')}`")
                p(
                    _tabela_markdown(
                        ["Campo", "Extraído", "Referência", "Erro"],
                        [
                            [
                                "Instituição",
                                str(i.get("instituicao_extraida") or "—"),
                                str(refv.get("instituicao") or "—"),
                                _fmt_bool(i.get("acerto_instituicao")),
                            ],
                            [
                                "Período",
                                str(i.get("periodo_extraido") or "—"),
                                f"{refv.get('periodo_inicio')} → {refv.get('periodo_fim')}",
                                _fmt_bool(i.get("acerto_periodo")),
                            ],
                            [
                                "Saldo inicial",
                                _fmt_num(val.get("saldo_inicial")),
                                _fmt_num(refv.get("saldo_inicial")),
                                _fmt_bool(i.get("acerto_saldo_inicial")),
                            ],
                            [
                                "Entradas",
                                _fmt_num(val.get("total_entradas")),
                                _fmt_num(refv.get("total_entradas")),
                                _fmt_num(i.get("erro_entradas")),
                            ],
                            [
                                "Saídas",
                                _fmt_num(val.get("total_saidas")),
                                _fmt_num(refv.get("total_saidas")),
                                _fmt_num(i.get("erro_saidas")),
                            ],
                            [
                                "Saldo final",
                                _fmt_num(val.get("saldo_final_informado")),
                                _fmt_num(refv.get("saldo_final_informado")),
                                _fmt_num(i.get("erro_saldo_final_informado")),
                            ],
                            [
                                "Saldo calc. / Δ",
                                f"{_fmt_num(val.get('saldo_final_calculado'))} / {_fmt_num(val.get('diferenca'))}",
                                "—",
                                "—",
                            ],
                        ],
                    )
                )
                p("")

    h(2, "10. Notas metodológicas")
    p(
        "- Condição **A**: texto nativo; **B**: OCR isolado; **C**: abordagem integrada.\n"
        "- Consistência aritmética: SI + E − S ≈ SF (tolerância configurada).\n"
        "- Referência manual: `dados/referencia_manual/`.\n"
        "- Arquivo JSON paralelo: `consolidado_avaliacao.json` (mesma pasta de saída)."
    )
    p("")
    p("---")
    p("*Relatório gerado automaticamente pela interface Extrato PDF (TCC 3).*")
    p("")
    return "\n".join(linhas)


def gerar_arquivos_relatorio(
    pasta_experimentos: Path,
    pasta_refs: Path,
    pasta_saida: Path,
    tolerancia: Decimal,
) -> dict[str, Any]:
    """Gera Markdown + JSON consolidado e retorna metadados dos arquivos."""
    consolidado = montar_consolidado(pasta_experimentos, pasta_refs, tolerancia)
    markdown = formatar_relatorio_markdown(consolidado)

    pasta_saida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = pasta_saida / f"relatorio_metricas_{stamp}.md"
    json_path = pasta_saida / "consolidado_avaliacao.json"
    latest_md = pasta_saida / "relatorio_metricas.md"

    json_publico = {k: v for k, v in consolidado.items() if k != "itens_detalhados"}
    md_path.write_text(markdown, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    json_path.write_text(
        json.dumps(json_publico, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return {
        "markdown_path": md_path,
        "markdown_latest": latest_md,
        "json_path": json_path,
        "gerado_em": consolidado.get("gerado_em"),
        "qtd_metricas": len(consolidado.get("metricas") or []),
        "veredito": (consolidado.get("laboratorio") or {}).get("hipotese", {}).get("veredito"),
    }
