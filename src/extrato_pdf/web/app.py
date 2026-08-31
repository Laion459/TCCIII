from __future__ import annotations

from pathlib import Path
import asyncio
import json

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from extrato_pdf.util.config import ConfigInvalidaError
from extrato_pdf.web import servicos
from extrato_pdf.web.formatacao import (
    classe_status,
    formatar_brl,
    formatar_periodo,
    rotulo_status,
)
from extrato_pdf.web.jobs import StatusJob

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _static_version() -> str:
    mtimes: list[float] = []
    for nome in ("styles.css", "app.js", "charts.js", "progress.js"):
        path = BASE_DIR / "static" / nome
        if path.exists():
            mtimes.append(path.stat().st_mtime)
    return str(int(max(mtimes))) if mtimes else "1"


STATIC_VERSION = _static_version()
TEMPLATES.env.filters["brl"] = formatar_brl
TEMPLATES.env.filters["periodo"] = formatar_periodo
TEMPLATES.env.filters["status_label"] = rotulo_status
TEMPLATES.env.filters["status_class"] = classe_status
TEMPLATES.env.globals["formatar_brl"] = formatar_brl
TEMPLATES.env.globals["static_v"] = STATIC_VERSION

app = FastAPI(
    title="Extrato PDF — TCC 3",
    description="Interface local para extração e validação de extratos bancários",
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)


@app.middleware("http")
async def static_no_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


def _ctx(**extra):
    return {
        "menu": [
            {"href": "/", "label": "Painel", "id": "painel"},
            {"href": "/pdfs", "label": "PDFs de entrada", "id": "pdfs"},
            {"href": "/processar", "label": "Processar", "id": "processar"},
            {"href": "/lote", "label": "Lote / Experimentos", "id": "lote"},
            {"href": "/resultados", "label": "Resultados", "id": "resultados"},
            {"href": "/metricas", "label": "Métricas experimentais", "id": "metricas"},
            {"href": "/validacao", "label": "Validação", "id": "validacao"},
            {"href": "/config", "label": "Configuração", "id": "config"},
            {"href": "/ajuda", "label": "Ajuda", "id": "ajuda"},
        ],
        **extra,
    }


def render(request: Request, template: str, **extra):
    return TEMPLATES.TemplateResponse(request, template, _ctx(**extra))


class IniciarLoteBody(BaseModel):
    condicao: str = "A"
    pdfs: list[str] | None = None


class IniciarUnitarioBody(BaseModel):
    pdf: str
    condicao: str = "C"


def _job_finalizado(status: str) -> bool:
    return status in {
        StatusJob.CONCLUIDO.value,
        StatusJob.ERRO.value,
        StatusJob.CANCELADO.value,
    }


async def _stream_job(job_id: str):
    """Server-Sent Events com snapshot do job a cada 400ms."""
    while True:
        job = servicos.obter_job(job_id)
        if not job:
            payload = json.dumps({"erro": "Job não encontrado"})
            yield f"data: {payload}\n\n"
            break
        yield f"data: {json.dumps(job.para_dict(), ensure_ascii=False)}\n\n"
        if _job_finalizado(job.status.value):
            break
        await asyncio.sleep(0.4)


@app.get("/", response_class=HTMLResponse)
def painel(request: Request):
    return render(
        request,
        "painel.html",
        ativo="painel",
        resumo=servicos.resumo_dashboard(),
    )


@app.get("/pdfs", response_class=HTMLResponse)
def pdfs(request: Request):
    return render(
        request,
        "pdfs.html",
        ativo="pdfs",
        pdfs=servicos.listar_pdfs_entrada(),
    )


@app.post("/pdfs/upload")
async def upload_pdf(arquivo: UploadFile = File(...)):
    conteudo = await arquivo.read()
    servicos.salvar_upload_pdf(arquivo.filename or "upload.pdf", conteudo)
    return RedirectResponse("/pdfs?ok=1", status_code=303)


@app.get("/processar", response_class=HTMLResponse)
def processar_form(request: Request):
    return render(
        request,
        "processar.html",
        ativo="processar",
        pdfs=servicos.listar_pdfs_entrada(),
        resultado=None,
        erro=None,
    )


@app.post("/processar", response_class=HTMLResponse)
def processar_exec(
    request: Request,
    pdf: str = Form(...),
    condicao: str = Form("C"),
):
    erro = None
    resultado = None
    try:
        resultado = servicos.processar_um(pdf, condicao=condicao)
    except Exception as exc:  # noqa: BLE001
        erro = str(exc)
    return render(
        request,
        "processar.html",
        ativo="processar",
        pdfs=servicos.listar_pdfs_entrada(),
        resultado=resultado,
        erro=erro,
        selecionado=pdf,
        condicao=condicao,
    )


@app.get("/lote", response_class=HTMLResponse)
def lote_form(request: Request):
    return render(
        request,
        "lote.html",
        ativo="lote",
        pdfs=servicos.listar_pdfs_entrada(),
        relatorio=None,
        erro=None,
    )


@app.post("/lote", response_class=HTMLResponse)
async def lote_exec(request: Request):
    """Fallback síncrono (sem JavaScript)."""
    form = await request.form()
    condicao = str(form.get("condicao") or "A")
    nomes = [str(v) for k, v in form.multi_items() if k == "pdfs"]
    erro = None
    relatorio = None
    try:
        if not nomes:
            nomes = None
        relatorio = servicos.processar_lote(condicao=condicao, nomes=nomes)
    except Exception as exc:  # noqa: BLE001
        erro = str(exc)
    return render(
        request,
        "lote.html",
        ativo="lote",
        pdfs=servicos.listar_pdfs_entrada(),
        relatorio=relatorio,
        erro=erro,
        condicao=condicao,
    )


@app.post("/api/lote/iniciar")
def api_iniciar_lote(body: IniciarLoteBody):
    try:
        job = servicos.iniciar_lote_async(body.condicao, body.pdfs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"job_id": job.id, "total": job.total}


@app.post("/api/processar/iniciar")
def api_iniciar_unitario(body: IniciarUnitarioBody):
    job = servicos.iniciar_unitario_async(body.pdf, body.condicao)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def api_status_job(job_id: str):
    job = servicos.obter_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job.para_dict()


@app.get("/api/jobs/{job_id}/stream")
async def api_stream_job(job_id: str):
    job = servicos.obter_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return StreamingResponse(
        _stream_job(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/jobs/{job_id}/cancelar")
def api_cancelar_job(job_id: str):
    if not servicos.cancelar_job(job_id):
        raise HTTPException(status_code=400, detail="Não foi possível cancelar")
    return {"ok": True}


@app.get("/resultados", response_class=HTMLResponse)
def resultados(request: Request):
    return render(
        request,
        "resultados.html",
        ativo="resultados",
        itens=servicos.listar_resultados(),
    )


@app.get("/resultados/ver", response_class=HTMLResponse)
def resultado_detalhe(request: Request, path: str):
    try:
        detalhe = servicos.carregar_resultado(path)
        erro = None
    except Exception as exc:  # noqa: BLE001
        detalhe = None
        erro = str(exc)
    return render(
        request,
        "resultado_detalhe.html",
        ativo="resultados",
        detalhe=detalhe,
        erro=erro,
    )


@app.get("/metricas", response_class=HTMLResponse)
def metricas(request: Request):
    erro = None
    dados = None
    try:
        dados = servicos.calcular_metricas()
    except Exception as exc:  # noqa: BLE001
        erro = str(exc)
    return render(
        request,
        "metricas.html",
        ativo="metricas",
        dados=dados,
        erro=erro,
    )


@app.get("/validacao", response_class=HTMLResponse)
def validacao(request: Request):
    return render(
        request,
        "validacao.html",
        ativo="validacao",
        resultado=servicos.validar_saidas(),
    )


@app.get("/config", response_class=HTMLResponse)
def config_pagina(request: Request, ok: str | None = None, erro: str | None = None):
    cfg = None
    msg_erro = erro
    try:
        cfg = servicos.montar_config_ui()
    except ConfigInvalidaError as exc:
        msg_erro = str(exc)
    return render(
        request,
        "config.html",
        ativo="config",
        cfg=cfg,
        ok=bool(ok),
        erro=msg_erro,
    )


@app.post("/config", response_class=HTMLResponse)
async def config_salvar(request: Request):
    form = await request.form()
    dados = {
        "tolerancia_monetaria": form.get("tolerancia_monetaria"),
        "limiar_localizacao": form.get("limiar_localizacao"),
        "min_caracteres_pagina": form.get("min_caracteres_pagina"),
        "percentual_minimo_nativo": form.get("percentual_minimo_nativo"),
        "ocr_dpi": form.get("ocr_dpi"),
        "ocr_workers": form.get("ocr_workers"),
        "ocr_idioma": form.get("ocr_idioma"),
        "tesseract_cmd": form.get("tesseract_cmd"),
    }
    try:
        servicos.salvar_config_ui(dados)
        return RedirectResponse("/config?ok=1", status_code=303)
    except (ConfigInvalidaError, ValueError, TypeError) as exc:
        cfg = servicos.montar_config_ui()
        # Mantém valores digitados em caso de erro
        for chave, valor in dados.items():
            if valor is not None and chave in cfg:
                try:
                    if chave in {"limiar_localizacao", "min_caracteres_pagina", "ocr_dpi", "ocr_workers"}:
                        cfg[chave] = int(valor)
                    elif chave in {"tolerancia_monetaria", "percentual_minimo_nativo"}:
                        cfg[chave] = float(str(valor).replace(",", "."))
                    else:
                        cfg[chave] = valor
                except ValueError:
                    cfg[chave] = valor
        return render(
            request,
            "config.html",
            ativo="config",
            cfg=cfg,
            ok=False,
            erro=str(exc),
        )


@app.get("/ajuda", response_class=HTMLResponse)
def ajuda(request: Request):
    return render(request, "ajuda.html", ativo="ajuda")


def main() -> None:
    uvicorn.run(
        "extrato_pdf.web.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
