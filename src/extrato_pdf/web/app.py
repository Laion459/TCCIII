from __future__ import annotations

from pathlib import Path
import asyncio
import json

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from extrato_pdf.corpora import CorpusDesconhecidoError
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
    title="Extrato PDF - TCC 3",
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


def _corpus_pagina(valor: str | None) -> tuple[dict, list[dict], str | None]:
    try:
        atual = servicos.descrever_corpus(valor)
        erro = None
    except CorpusDesconhecidoError as exc:
        atual = servicos.descrever_corpus(None)
        erro = str(exc)
    return atual, servicos.resumir_corpora(), erro


class IniciarLoteBody(BaseModel):
    condicao: str | None = None
    condicoes: list[str] | None = None
    pdfs: list[str] | None = None
    corpus: str | None = None
    corpora: list[str] | None = None


class IniciarUnitarioBody(BaseModel):
    pdf: str
    condicao: str | None = None
    condicoes: list[str] | None = None
    corpus: str | None = None
    corpora: list[str] | None = None


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
def painel(
    request: Request,
    ok: str | None = None,
    erro: str | None = None,
    corpus: str | None = None,
):
    mensagens_ok = {
        "limpo": (
            "Resultados limpos. Experimentos e métricas foram removidos; "
            "PDFs de entrada e referências manuais foram preservados."
        ),
    }
    mensagens_erro = {
        "job_ativo": (
            "Há um processamento em andamento. Cancele ou aguarde antes de limpar."
        ),
    }
    atual, corpora, erro_corpus = _corpus_pagina(corpus)
    return render(
        request,
        "painel.html",
        ativo="painel",
        resumo=servicos.resumo_dashboard(atual["id"]),
        matriz=servicos.matriz_experimental(),
        parametros=servicos.parametros_experimento(),
        ok=mensagens_ok.get(ok, ok),
        erro=erro_corpus or mensagens_erro.get(erro, erro),
        corpus=atual,
        corpora=corpora,
    )


@app.post("/painel/limpar-resultados")
def limpar_resultados_painel():
    try:
        servicos.limpar_resultados()
    except RuntimeError:
        return RedirectResponse("/?erro=job_ativo", status_code=303)
    return RedirectResponse("/?ok=limpo", status_code=303)


@app.get("/pdfs", response_class=HTMLResponse)
def pdfs(request: Request, corpus: str | None = None):
    atual, corpora, erro_corpus = _corpus_pagina(corpus)
    return render(
        request,
        "pdfs.html",
        ativo="pdfs",
        pdfs=servicos.listar_pdfs_entrada(atual["id"]),
        corpus=atual,
        corpora=corpora,
        erro_corpus=erro_corpus,
    )


@app.post("/pdfs/upload")
async def upload_pdf(arquivo: UploadFile = File(...)):
    conteudo = await arquivo.read()
    servicos.salvar_upload_pdf(arquivo.filename or "upload.pdf", conteudo)
    return RedirectResponse("/pdfs?ok=1", status_code=303)


@app.get("/processar", response_class=HTMLResponse)
def processar_form(request: Request, corpus: str | None = None):
    atual, corpora, erro_corpus = _corpus_pagina(corpus)
    return render(
        request,
        "processar.html",
        ativo="processar",
        pdfs=servicos.listar_pdfs_esteira(),
        resultado=None,
        erro=erro_corpus,
        corpus=atual,
        corpora=corpora,
    )


@app.get("/lote", response_class=HTMLResponse)
def lote_form(request: Request, corpus: str | None = None):
    atual, corpora, erro_corpus = _corpus_pagina(corpus)
    return render(
        request,
        "lote.html",
        ativo="lote",
        pdfs=servicos.listar_pdfs_esteira(),
        relatorio=None,
        erro=erro_corpus,
        corpus=atual,
        corpora=corpora,
    )


@app.post("/lote", response_class=HTMLResponse)
async def lote_exec(request: Request):
    """Fallback síncrono (sem JavaScript)."""
    form = await request.form()
    pares = list(form.multi_items())
    nomes = [str(v) for k, v in pares if k == "pdfs"]
    corpora_form = [str(v) for k, v in pares if k == "corpora"]
    condicoes_form = [str(v) for k, v in pares if k == "condicoes"]
    atual, corpora, erro_corpus = _corpus_pagina(None)
    erro = erro_corpus
    relatorio = None
    if erro is None:
        try:
            relatorio = servicos.processar_lote(
                nomes=nomes or None,
                corpora=corpora_form,
                condicoes=condicoes_form,
            )
        except Exception as exc:  # noqa: BLE001
            erro = str(exc)
    return render(
        request,
        "lote.html",
        ativo="lote",
        pdfs=servicos.listar_pdfs_esteira(),
        relatorio=relatorio,
        erro=erro,
        corpus=atual,
        corpora=corpora,
    )


@app.post("/api/lote/iniciar")
def api_iniciar_lote(body: IniciarLoteBody):
    try:
        job = servicos.iniciar_lote_async(
            body.condicao,
            body.pdfs,
            body.corpus,
            condicoes=body.condicoes,
            corpora=body.corpora,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"job_id": job.id, "total": job.total}


@app.post("/api/processar/iniciar")
def api_iniciar_unitario(body: IniciarUnitarioBody):
    try:
        job = servicos.iniciar_unitario_async(
            body.pdf,
            body.condicao,
            body.corpus,
            condicoes=body.condicoes,
            corpora=body.corpora,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
def resultados(request: Request, condicao: str | None = None, corpus: str | None = None):
    cond = (condicao or "").strip().upper() or None
    if cond and cond not in ("A", "B", "C"):
        cond = None
    if servicos.eh_visao_todos(corpus):
        atual = servicos.descrever_visao(corpus)
        corpora = servicos.resumir_corpora()
        erro_corpus = None
        corpus_lista = servicos.VISAO_TODOS
    else:
        atual, corpora, erro_corpus = _corpus_pagina(corpus)
        corpus_lista = atual["id"]
    return render(
        request,
        "resultados.html",
        ativo="resultados",
        itens=servicos.listar_resultados(condicao=cond, corpus=corpus_lista),
        filtro_condicao=cond,
        condicoes=("A", "B", "C"),
        corpus=atual,
        corpora=corpora,
        matriz=servicos.matriz_experimental(),
        erro=erro_corpus,
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
def metricas(request: Request, corpus: str | None = None):
    if servicos.eh_visao_todos(corpus):
        atual = servicos.descrever_visao(corpus)
        corpora = servicos.resumir_corpora()
        erro_corpus = None
    else:
        atual, corpora, erro_corpus = _corpus_pagina(corpus)
    erro = erro_corpus
    dados = None
    if erro is None and not servicos.eh_visao_todos(atual["id"]):
        try:
            dados = servicos.calcular_metricas(atual["id"])
        except Exception as exc:  # noqa: BLE001
            erro = str(exc)
    try:
        comparacao = servicos.comparacao_entre_corpora()
    except Exception as exc:  # noqa: BLE001
        comparacao = {"linhas": [], "matriz": []}
        erro = erro or str(exc)
    return render(
        request,
        "metricas.html",
        ativo="metricas",
        dados=dados,
        comparacao=comparacao,
        erro=erro,
        corpus=atual,
        corpora=corpora,
    )


@app.get("/metricas/relatorio")
def metricas_relatorio(corpus: str | None = None):
    """Gera e baixa relatório completo (Markdown) com todos os comparativos."""
    try:
        meta = servicos.gerar_relatorio_metricas(corpus)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    path = Path(meta["caminho_markdown"])
    if not path.exists():
        raise HTTPException(status_code=500, detail="Relatório não foi gerado.")
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=meta["nome_arquivo"],
        headers={"Content-Disposition": f'attachment; filename="{meta["nome_arquivo"]}"'},
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
        reload=True,
    )


if __name__ == "__main__":
    main()
