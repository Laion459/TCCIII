#!/usr/bin/env python
"""Avalia resultados A/B/C atuais contra referência manual e imprime consolidado."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
EXP = BASE / "resultados" / "experimentos"
REFS_DIR = BASE / "dados" / "referencia_manual"
SAIDA = BASE / "resultados" / "metricas"


def quase(a, b, tol: Decimal = Decimal("0.01")) -> bool:
    if a is None or b is None:
        return a == b
    try:
        return abs(Decimal(str(a)) - Decimal(str(b))) <= tol
    except Exception:  # noqa: BLE001
        return False


def carregar_refs() -> dict[str, dict]:
    refs: dict[str, dict] = {}
    for p in REFS_DIR.glob("D*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        docs = d.get("documento")
        if docs:
            refs[str(docs)] = d
    return refs


def carregar_condicao(cond: str) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    pasta = EXP / f"condicao_{cond.lower()}"
    for jp in pasta.rglob("resultado.json"):
        d = json.loads(jp.read_text(encoding="utf-8"))
        arq = d.get("documento", {}).get("arquivo", jp.parent.name)
        docs[arq] = d
    return docs


def comparar(res: dict, ref: dict) -> dict:
    extr = res.get("extrato", {})
    per = extr.get("periodo", {})
    val = res.get("valores", {})

    def erro(campo_res: str, campo_ref: str):
        if val.get(campo_res) is None or ref.get(campo_ref) is None:
            return None
        return float(abs(Decimal(str(val[campo_res])) - Decimal(str(ref[campo_ref]))))

    item = {
        "documento": ref.get("documento"),
        "tipo_pdf": res.get("documento", {}).get("tipo_pdf"),
        "acerto_instituicao": (extr.get("instituicao") or "").upper()
        == (ref.get("instituicao") or "").upper(),
        "acerto_periodo": per.get("inicio") == ref.get("periodo_inicio")
        and per.get("fim") == ref.get("periodo_fim"),
        "acerto_saldo_inicial": quase(val.get("saldo_inicial"), ref.get("saldo_inicial")),
        "erro_entradas": erro("total_entradas", "total_entradas"),
        "erro_saidas": erro("total_saidas", "total_saidas"),
        "erro_saldo_final_informado": erro(
            "saldo_final_informado", "saldo_final_informado"
        ),
        "consistente": bool(res.get("validacao", {}).get("consistente")),
        "status_processamento": res.get("validacao", {}).get("status_processamento"),
        "valores": val,
        "ref_valores": {
            "saldo_inicial": ref.get("saldo_inicial"),
            "total_entradas": ref.get("total_entradas"),
            "total_saidas": ref.get("total_saidas"),
            "saldo_final_informado": ref.get("saldo_final_informado"),
        },
    }
    item["acerto_entradas"] = (
        item["erro_entradas"] is not None and item["erro_entradas"] <= 0.01
    )
    item["acerto_saidas"] = (
        item["erro_saidas"] is not None and item["erro_saidas"] <= 0.01
    )
    item["acerto_saldo_final"] = (
        item["erro_saldo_final_informado"] is not None
        and item["erro_saldo_final_informado"] <= 0.01
    )
    item["acerto_campos_essenciais"] = all(
        [
            item["acerto_instituicao"],
            item["acerto_periodo"],
            item["acerto_saldo_inicial"],
            item["acerto_entradas"],
            item["acerto_saidas"],
            item["acerto_saldo_final"],
        ]
    )
    return item


def score4(itens: list[dict]) -> float:
    if not itens:
        return 0.0
    pts = 0.0
    for i in itens:
        campos = (
            i["acerto_instituicao"],
            i["acerto_periodo"],
            i["acerto_saldo_inicial"],
            i["consistente"],
        )
        pts += sum(1 for c in campos if c) / 4
    return round(100 * pts / len(itens), 1)


def score6(itens: list[dict]) -> float:
    if not itens:
        return 0.0
    pts = 0.0
    for i in itens:
        campos = (
            i["acerto_instituicao"],
            i["acerto_periodo"],
            i["acerto_saldo_inicial"],
            i["acerto_entradas"],
            i["acerto_saidas"],
            i["acerto_saldo_final"],
        )
        pts += sum(1 for c in campos if c) / 6
    return round(100 * pts / len(itens), 1)


def pct(itens: list[dict], campo: str) -> float:
    if not itens:
        return 0.0
    return round(100 * sum(1 for i in itens if i.get(campo)) / len(itens), 1)


def main() -> int:
    refs = carregar_refs()
    print(f"Referencias: {len(refs)}")

    consolidado: dict = {"por_condicao": {}, "divergencias_a_c": [], "metricas": []}

    docs_por_cond = {c: carregar_condicao(c) for c in "ABC"}

    print("\n=== STATUS OPERACIONAL ===")
    for cond, docs in docs_por_cond.items():
        st = Counter(
            d.get("validacao", {}).get("status_processamento", "?") for d in docs.values()
        )
        total = sum(st.values())
        taxa = round(100 * st.get("consistente", 0) / total, 1) if total else 0.0
        tipos = Counter(d.get("documento", {}).get("tipo_pdf") for d in docs.values())
        consolidado["por_condicao"][cond] = {
            "total": total,
            "por_status": dict(st),
            "taxa_consistente": taxa,
            "tipos_pdf": dict(tipos),
        }
        print(f"{cond}: n={total} status={dict(st)} taxa_consistente={taxa}% tipos={dict(tipos)}")

    print("\n=== DIVERGENCIAS A vs C ===")
    arqs = sorted(set(docs_por_cond["A"]) | set(docs_por_cond["C"]))
    for arq in arqs:
        a = docs_por_cond["A"].get(arq)
        c = docs_por_cond["C"].get(arq)
        if not a or not c:
            consolidado["divergencias_a_c"].append({"documento": arq, "motivo": "faltando"})
            print("faltando", arq)
            continue
        sa = a["validacao"]["status_processamento"]
        sc = c["validacao"]["status_processamento"]
        va, vc = a.get("valores", {}), c.get("valores", {})
        keys = (
            "saldo_inicial",
            "total_entradas",
            "total_saidas",
            "saldo_final_informado",
            "saldo_final_calculado",
            "diferenca",
        )
        same = all(va.get(k) == vc.get(k) for k in keys)
        if sa != sc or not same:
            item = {
                "documento": arq,
                "tipo_pdf": a.get("documento", {}).get("tipo_pdf"),
                "status_a": sa,
                "status_c": sc,
                "valores_a": {k: va.get(k) for k in keys},
                "valores_c": {k: vc.get(k) for k in keys},
            }
            consolidado["divergencias_a_c"].append(item)
            print(
                f"{arq} tipo={item['tipo_pdf']} A={sa} C={sc} "
                f"SI A/C={va.get('saldo_inicial')}/{vc.get('saldo_inicial')} "
                f"E A/C={va.get('total_entradas')}/{vc.get('total_entradas')} "
                f"S A/C={va.get('total_saidas')}/{vc.get('total_saidas')} "
                f"SF A/C={va.get('saldo_final_informado')}/{vc.get('saldo_final_informado')}"
            )
    print(f"Total divergencias A/C: {len(consolidado['divergencias_a_c'])}")

    print("\n=== METRICAS vs REFERENCIA ===")
    for cond, docs in docs_por_cond.items():
        itens = []
        for arq, res in sorted(docs.items()):
            ref = refs.get(arq)
            if not ref:
                print(f"Sem ref: {cond} {arq}")
                continue
            item = comparar(res, ref)
            item["condicao"] = cond
            itens.append(item)
            consolidado["metricas"].append(
                {
                    k: item[k]
                    for k in item
                    if k not in {"valores", "ref_valores"}
                }
            )

        s4 = score4(itens)
        s6 = score6(itens)
        ess = pct(itens, "acerto_campos_essenciais")
        consolidado["por_condicao"][cond]["vs_referencia"] = {
            "n": len(itens),
            "score4_web": s4,
            "score6_campos": s6,
            "pct_acerto_completo": ess,
            "pct_instituicao": pct(itens, "acerto_instituicao"),
            "pct_periodo": pct(itens, "acerto_periodo"),
            "pct_saldo_inicial": pct(itens, "acerto_saldo_inicial"),
            "pct_entradas": pct(itens, "acerto_entradas"),
            "pct_saidas": pct(itens, "acerto_saidas"),
            "pct_saldo_final": pct(itens, "acerto_saldo_final"),
            "pct_consistente": pct(itens, "consistente"),
            "status": dict(Counter(i["status_processamento"] for i in itens)),
        }
        print(
            f"{cond}: n={len(itens)} score4={s4} score6={s6} "
            f"completo={ess}% SI={pct(itens,'acerto_saldo_inicial')}% "
            f"E={pct(itens,'acerto_entradas')}% S={pct(itens,'acerto_saidas')}% "
            f"SF={pct(itens,'acerto_saldo_final')}% cons={pct(itens,'consistente')}%"
        )
        falhas = [i for i in itens if not i["acerto_campos_essenciais"]]
        print(f"  falhas essenciais: {len(falhas)}")
        for i in falhas:
            print(
                f"    {i['documento']} tipo={i['tipo_pdf']} st={i['status_processamento']} "
                f"I={i['acerto_instituicao']} P={i['acerto_periodo']} "
                f"SI={i['acerto_saldo_inicial']} E={i['acerto_entradas']} "
                f"S={i['acerto_saidas']} SF={i['acerto_saldo_final']} "
                f"errE={i['erro_entradas']} errS={i['erro_saidas']} errSF={i['erro_saldo_final_informado']}"
            )

    # Inventario tipo/status A para apendice
    inventario = []
    for arq, res in sorted(docs_por_cond["A"].items()):
        val = res.get("valores", {})
        inventario.append(
            {
                "arquivo": arq,
                "tipo": res.get("documento", {}).get("tipo_pdf"),
                "paginas": res.get("documento", {}).get("quantidade_paginas"),
                "status_a": res.get("validacao", {}).get("status_processamento"),
                "status_c": docs_por_cond["C"]
                .get(arq, {})
                .get("validacao", {})
                .get("status_processamento"),
                "status_b": docs_por_cond["B"]
                .get(arq, {})
                .get("validacao", {})
                .get("status_processamento"),
                "instituicao": res.get("extrato", {}).get("instituicao"),
                "diferenca": val.get("diferenca"),
                "acerto_completo_a": next(
                    (
                        m["acerto_campos_essenciais"]
                        for m in consolidado["metricas"]
                        if m["condicao"] == "A" and m["documento"] == arq
                    ),
                    None,
                ),
                "acerto_completo_c": next(
                    (
                        m["acerto_campos_essenciais"]
                        for m in consolidado["metricas"]
                        if m["condicao"] == "C" and m["documento"] == arq
                    ),
                    None,
                ),
            }
        )
    consolidado["inventario"] = inventario

    SAIDA.mkdir(parents=True, exist_ok=True)
    out = SAIDA / "consolidado_avaliacao.json"
    out.write_text(json.dumps(consolidado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSalvo: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
