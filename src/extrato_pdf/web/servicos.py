from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from extrato_pdf.modelos import CondicaoExperimental
from extrato_pdf.modulos.metricas import comparar_com_referencia
from extrato_pdf.pipeline import processar_pdf
from extrato_pdf.util.config import (
    ConfigInvalidaError,
    carregar_config,
    carregar_json,
    caminho_config_padrao,
    caminho_instituicoes_padrao,
    tolerancia,
)
from extrato_pdf.util.progresso import (
    ETAPAS,
    ProcessamentoCanceladoError,
    ProgressoFn,
    verificar_cancelamento,
)
from extrato_pdf.web.experimentos import CONDICOES, agregar_corpus_experimentos, montar_laboratorio
from extrato_pdf.web.formatacao import preparar_relatorio
from extrato_pdf.web.jobs import ItemJob, Job, StatusItem, StatusJob, gerenciador


def raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[3]


def pasta_entrada() -> Path:
    return raiz_projeto() / "dados" / "entrada"


def pasta_resultados() -> Path:
    return raiz_projeto() / "resultados"


def pasta_referencias() -> Path:
    return raiz_projeto() / "dados" / "referencia_manual"


def pasta_experimentos() -> Path:
    return pasta_resultados() / "experimentos"


@dataclass
class ResumoPdf:
    nome: str
    tamanho_mb: float
    modificado: str


@dataclass
class ResumoResultado:
    pasta: str
    arquivo: str
    status: str
    instituicao: Optional[str]
    condicao: Optional[str]
    consistente: Optional[bool]
    caminho_relativo: str


def listar_pdfs_entrada() -> list[ResumoPdf]:
    pasta = pasta_entrada()
    itens: list[ResumoPdf] = []
    if not pasta.exists():
        return itens
    for path in sorted(pasta.glob("*.pdf")):
        st = path.stat()
        itens.append(
            ResumoPdf(
                nome=path.name,
                tamanho_mb=round(st.st_size / (1024 * 1024), 1),
                modificado=datetime.fromtimestamp(st.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                ),
            )
        )
    return itens


def listar_resultados(
    base: Path | None = None,
    condicao: str | None = None,
) -> list[ResumoResultado]:
    """Lista resultados. Se `condicao` for A/B/C, restringe à pasta da condição."""
    raiz = base or pasta_resultados()
    cond = (condicao or "").strip().upper() or None
    if cond in CONDICOES:
        raiz = pasta_experimentos() / f"condicao_{cond.lower()}"
    itens: list[ResumoResultado] = []
    if not raiz.exists():
        return itens
    for json_path in sorted(raiz.rglob("resultado.json")):
        try:
            dados = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        cond_item = dados.get("experimento", {}).get("condicao")
        if not cond_item:
            # Inferir pela pasta condicao_x quando o JSON antigo não traz o campo.
            for parte in json_path.parts:
                if parte.startswith("condicao_"):
                    cond_item = parte.replace("condicao_", "").upper()
                    break
        if cond in CONDICOES and cond_item and str(cond_item).upper() != cond:
            continue
        rel = json_path.parent.relative_to(raiz_projeto())
        itens.append(
            ResumoResultado(
                pasta=json_path.parent.name,
                arquivo=dados.get("documento", {}).get("arquivo", json_path.parent.name),
                status=dados.get("validacao", {}).get("status_processamento", "?"),
                instituicao=dados.get("extrato", {}).get("instituicao"),
                condicao=cond_item,
                consistente=dados.get("validacao", {}).get("consistente"),
                caminho_relativo=str(rel).replace("\\", "/"),
            )
        )
    return itens


def carregar_resultado(caminho_relativo: str) -> dict[str, Any]:
    base = raiz_projeto() / caminho_relativo
    json_path = base / "resultado.json"
    txt_path = base / "relatorio.txt"
    log_path = base / "execucao.log"
    dados = json.loads(json_path.read_text(encoding="utf-8"))
    return {
        "dados": dados,
        "relatorio": txt_path.read_text(encoding="utf-8") if txt_path.exists() else "",
        "log": log_path.read_text(encoding="utf-8") if log_path.exists() else "",
        "caminho": str(base),
        "caminho_relativo": caminho_relativo,
        "relatorio_ui": preparar_relatorio(dados),
        "condicoes_alternativas": buscar_condicoes_alternativas(dados, caminho_relativo),
    }


def buscar_condicoes_alternativas(
    dados: dict[str, Any],
    caminho_atual: str,
) -> list[dict[str, Any]]:
    """Outras condições experimentais para o mesmo PDF."""
    arquivo = dados.get("documento", {}).get("arquivo", "")
    condicao_atual = dados.get("experimento", {}).get("condicao")
    if not arquivo:
        return []

    stem = Path(arquivo).stem
    alternativas: list[dict[str, Any]] = []
    for cond in ("A", "B", "C"):
        if cond == condicao_atual:
            continue
        pasta = pasta_experimentos() / f"condicao_{cond.lower()}" / stem
        json_path = pasta / "resultado.json"
        if not json_path.exists():
            continue
        try:
            outro = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rel = str(pasta.relative_to(raiz_projeto())).replace("\\", "/")
        alternativas.append(
            {
                "condicao": cond,
                "status": outro.get("validacao", {}).get("status_processamento"),
                "consistente": outro.get("validacao", {}).get("consistente"),
                "caminho_relativo": rel,
            }
        )
    return alternativas


def _formatar_mensagem_ocr(evento: dict[str, Any]) -> str:
    return (
        f"OCR {evento['concluidas']}/{evento['total']} páginas "
        f"({evento.get('workers', 1)} workers)"
    )


def _criar_callback_progresso(job: Job, item: ItemJob) -> ProgressoFn:
    def on_progress(evento: dict[str, Any]) -> None:
        verificar_cancelamento(lambda: job.cancelar)

        etapa = str(evento.get("etapa", ""))
        if etapa == "ocr":
            sub = {
                "concluidas": int(evento.get("concluidas", 0)),
                "total": int(evento.get("total", 0)),
                "workers": int(evento.get("workers", 1)),
            }
            detalhe = _formatar_mensagem_ocr(evento)
            job.atualizar_progresso(
                etapa=etapa,
                mensagem=f"{item.arquivo} - {detalhe}",
                sub_progresso=sub,
            )
            item.mensagem = detalhe
            return

        rotulo = ETAPAS.get(etapa, etapa.replace("_", " ").capitalize())
        job.atualizar_progresso(
            etapa=etapa,
            mensagem=f"{item.arquivo} - {rotulo}",
            sub_progresso=None,
        )
        item.mensagem = rotulo

    return on_progress


def processar_um(
    nome_pdf: str,
    condicao: str = "C",
    destino_rel: str | None = None,
    on_progress: ProgressoFn | None = None,
    deve_cancelar: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    pdf = pasta_entrada() / nome_pdf
    if not pdf.exists():
        raise FileNotFoundError(f"PDF não encontrado em entrada/: {nome_pdf}")
    config = carregar_config()
    cond = CondicaoExperimental(condicao.upper())
    if destino_rel:
        saida = raiz_projeto() / destino_rel
    else:
        saida = pasta_experimentos() / f"condicao_{cond.value.lower()}"
    inicio = time.perf_counter()
    resultado = processar_pdf(
        pdf,
        config=config,
        condicao=cond,
        diretorio_saida=saida,
        on_progress=on_progress,
        deve_cancelar=deve_cancelar,
    )
    duracao = round(time.perf_counter() - inicio, 2)
    pasta = saida / Path(nome_pdf).stem
    return {
        "arquivo": nome_pdf,
        "status": resultado.validacao.status_processamento.value,
        "instituicao": resultado.campos.instituicao,
        "consistente": resultado.validacao.consistente,
        "duracao_s": duracao,
        "caminho_relativo": str(pasta.relative_to(raiz_projeto())).replace("\\", "/"),
        "valores": {
            "saldo_inicial": float(resultado.campos.saldo_inicial)
            if resultado.campos.saldo_inicial is not None
            else None,
            "total_entradas": float(resultado.campos.total_entradas)
            if resultado.campos.total_entradas is not None
            else None,
            "total_saidas": float(resultado.campos.total_saidas)
            if resultado.campos.total_saidas is not None
            else None,
            "saldo_final": float(resultado.campos.saldo_final_informado)
            if resultado.campos.saldo_final_informado is not None
            else None,
        },
    }


def processar_lote(
    condicao: str = "A",
    nomes: list[str] | None = None,
) -> dict[str, Any]:
    """Processamento síncrono (CLI / fallback)."""
    pdfs = listar_pdfs_entrada()
    if nomes:
        selecionados = [p.nome for p in pdfs if p.nome in nomes]
    else:
        selecionados = [p.nome for p in pdfs]

    cond = CondicaoExperimental(condicao.upper())
    saida = pasta_experimentos() / f"condicao_{cond.value.lower()}"
    destino_rel = str(saida.relative_to(raiz_projeto()))
    inicio_total = time.perf_counter()
    itens = []
    contagem: dict[str, int] = {}
    for nome in selecionados:
        try:
            item = processar_um(nome, condicao=cond.value, destino_rel=destino_rel)
            itens.append(item)
            contagem[item["status"]] = contagem.get(item["status"], 0) + 1
        except Exception as exc:  # noqa: BLE001
            itens.append(
                {
                    "arquivo": nome,
                    "status": "erro",
                    "erro": str(exc),
                    "consistente": False,
                    "duracao_s": 0,
                }
            )
            contagem["erro"] = contagem.get("erro", 0) + 1

    return {
        "condicao": cond.value,
        "total": len(itens),
        "contagem": contagem,
        "duracao_total_s": round(time.perf_counter() - inicio_total, 2),
        "itens": itens,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }


def _finalizar_cancelamento(job, item, inicio: float) -> None:
    job.limpar_sub_progresso()
    item.status = StatusItem.CANCELADO
    item.mensagem = "cancelado"
    item.duracao_s = round(time.perf_counter() - inicio, 2)
    job.arquivo_atual = None
    job.status = StatusJob.CANCELADO
    job.mensagem = "Cancelado pelo usuário"
    job.adicionar_log(f"⊘ {item.arquivo} - cancelado")


def _executar_job_lote(job) -> None:
    cond = job.condicao
    saida = pasta_experimentos() / f"condicao_{cond.lower()}"
    destino_rel = str(saida.relative_to(raiz_projeto()))

    job.status = StatusJob.EXECUTANDO
    job.iniciado_em = time.perf_counter()
    job.adicionar_log(f"Iniciando lote - condição {cond}")

    for idx, item in enumerate(job.itens):
        if job.cancelar:
            job.status = StatusJob.CANCELADO
            job.mensagem = "Cancelado pelo usuário"
            job.adicionar_log("Lote cancelado")
            return

        job.indice_atual = idx + 1
        job.arquivo_atual = item.arquivo
        item.status = StatusItem.PROCESSANDO
        item.mensagem = "Extraindo texto e validando..."
        job.mensagem = f"Processando {item.arquivo} ({idx + 1}/{job.total})"
        job.adicionar_log(f"→ {item.arquivo}")

        inicio = time.perf_counter()
        try:
            callback = _criar_callback_progresso(job, item)
            resultado = processar_um(
                item.arquivo,
                condicao=cond,
                destino_rel=destino_rel,
                on_progress=callback,
                deve_cancelar=lambda: job.cancelar,
            )
            job.limpar_sub_progresso()
            item.status = StatusItem.OK
            item.resultado_status = resultado["status"]
            item.instituicao = resultado.get("instituicao")
            item.duracao_s = resultado.get("duracao_s", round(time.perf_counter() - inicio, 2))
            item.caminho_relativo = resultado.get("caminho_relativo")
            item.mensagem = resultado["status"]
            chave = resultado["status"]
            job.contagem[chave] = job.contagem.get(chave, 0) + 1
            job.adicionar_log(f"✓ {item.arquivo} - {resultado['status']} ({item.duracao_s}s)")
        except ProcessamentoCanceladoError:
            _finalizar_cancelamento(job, item, inicio)
            return
        except Exception as exc:  # noqa: BLE001
            job.limpar_sub_progresso()
            item.status = StatusItem.FALHA
            item.erro = str(exc)
            item.duracao_s = round(time.perf_counter() - inicio, 2)
            item.mensagem = "erro"
            job.contagem["erro"] = job.contagem.get("erro", 0) + 1
            job.adicionar_log(f"✗ {item.arquivo} - {exc}")

    job.arquivo_atual = None
    job.status = StatusJob.CONCLUIDO
    job.mensagem = f"Concluído - {job.concluidos}/{job.total} arquivo(s)"
    job.adicionar_log("Lote finalizado")


def _executar_job_unitario(job) -> None:
    item = job.itens[0]
    job.status = StatusJob.EXECUTANDO
    job.iniciado_em = time.perf_counter()
    job.arquivo_atual = item.arquivo
    item.status = StatusItem.PROCESSANDO
    job.mensagem = f"Processando {item.arquivo}"
    job.adicionar_log(f"→ {item.arquivo}")

    inicio = time.perf_counter()
    try:
        callback = _criar_callback_progresso(job, item)
        resultado = processar_um(
            item.arquivo,
            condicao=job.condicao,
            on_progress=callback,
            deve_cancelar=lambda: job.cancelar,
        )
        job.limpar_sub_progresso()
        item.status = StatusItem.OK
        item.resultado_status = resultado["status"]
        item.instituicao = resultado.get("instituicao")
        item.duracao_s = resultado.get("duracao_s", round(time.perf_counter() - inicio, 2))
        item.caminho_relativo = resultado.get("caminho_relativo")
        item.mensagem = resultado["status"]
        job.contagem[resultado["status"]] = 1
        job.status = StatusJob.CONCLUIDO
        job.mensagem = f"Concluído - {resultado['status']}"
        job.adicionar_log(f"✓ {resultado['status']} ({item.duracao_s}s)")
    except ProcessamentoCanceladoError:
        _finalizar_cancelamento(job, item, inicio)
    except Exception as exc:  # noqa: BLE001
        job.limpar_sub_progresso()
        item.status = StatusItem.FALHA
        item.erro = str(exc)
        item.duracao_s = round(time.perf_counter() - inicio, 2)
        job.status = StatusJob.ERRO
        job.mensagem = str(exc)
        job.adicionar_log(f"✗ {exc}")
    finally:
        job.arquivo_atual = None


def iniciar_lote_async(condicao: str, nomes: list[str] | None = None):
    pdfs = listar_pdfs_entrada()
    if nomes is None:
        selecionados = [p.nome for p in pdfs]
    elif not nomes:
        raise ValueError("Nenhum PDF selecionado")
    else:
        selecionados = [p.nome for p in pdfs if p.nome in nomes]
    if not selecionados:
        raise ValueError("Nenhum PDF selecionado")

    job = gerenciador.criar_lote(condicao, selecionados)
    gerenciador.executar_em_thread(job, _executar_job_lote)
    return job


def iniciar_unitario_async(arquivo: str, condicao: str = "C"):
    job = gerenciador.criar_unitario(arquivo, condicao)
    gerenciador.executar_em_thread(job, _executar_job_unitario)
    return job


def obter_job(job_id: str):
    return gerenciador.obter(job_id)


def cancelar_job(job_id: str) -> bool:
    return gerenciador.cancelar(job_id)


def validar_saidas(base_rel: str = "resultados") -> dict[str, Any]:
    status_ok = {
        "consistente",
        "inconsistente",
        "incompleto",
        "revisao_necessaria",
        "nao_processavel",
    }
    base = raiz_projeto() / base_rel
    erros: list[str] = []
    ok = 0
    for json_path in base.rglob("resultado.json"):
        pasta = json_path.parent
        for nome in ("relatorio.txt", "execucao.log"):
            if not (pasta / nome).exists():
                erros.append(f"Falta {nome} em {pasta}")
        try:
            dados = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            erros.append(f"JSON inválido {json_path}: {exc}")
            continue
        status = dados.get("validacao", {}).get("status_processamento")
        if status not in status_ok:
            erros.append(f"Status inválido em {json_path}: {status}")
        else:
            ok += 1
    return {"ok": ok, "erros": erros, "valido": len(erros) == 0}


def calcular_metricas() -> dict[str, Any]:
    config = carregar_config()
    tol = tolerancia(config)
    refs = []
    for path in pasta_referencias().glob("*.json"):
        if path.name == "exemplo_formato.json":
            continue
        refs.append(json.loads(path.read_text(encoding="utf-8")))

    metricas = []
    for json_path in pasta_resultados().rglob("resultado.json"):
        resultado = json.loads(json_path.read_text(encoding="utf-8"))
        arquivo = resultado.get("documento", {}).get("arquivo", "")
        ref = next(
            (
                r
                for r in refs
                if r.get("documento") == arquivo or arquivo in str(r.get("documento", ""))
            ),
            None,
        )
        if not ref:
            continue
        m = comparar_com_referencia(resultado, ref, tol)
        m["caminho_resultado"] = str(json_path.relative_to(raiz_projeto())).replace(
            "\\", "/"
        )
        m["condicao"] = resultado.get("experimento", {}).get("condicao")
        metricas.append(m)

    saida = pasta_resultados() / "metricas"
    saida.mkdir(parents=True, exist_ok=True)
    out = saida / "metricas.json"
    out.write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    laboratorio = montar_laboratorio(metricas, pasta_experimentos())
    return {
        "total": len(metricas),
        "itens": metricas,
        "arquivo": str(out),
        "laboratorio": laboratorio,
    }


def resumo_dashboard() -> dict[str, Any]:
    """Resumo do painel com métricas separadas por condição A/B/C (sem misturar)."""
    pdfs = listar_pdfs_entrada()
    resultados = listar_resultados()
    refs = [
        p.name
        for p in pasta_referencias().glob("*.json")
        if not p.name.startswith("_") and p.name != "exemplo_formato.json"
    ]
    corpus = agregar_corpus_experimentos(pasta_experimentos())
    por_condicao = []
    for cond in CONDICOES:
        info = corpus.get(cond, {})
        por_condicao.append(
            {
                "condicao": cond,
                "total": int(info.get("total", 0)),
                "por_status": dict(info.get("por_status") or {}),
                "taxa_consistente": float(info.get("taxa_consistente", 0.0)),
                "href_resultados": f"/resultados?condicao={cond}",
            }
        )
    return {
        "qtd_pdfs": len(pdfs),
        "qtd_resultados": len(resultados),
        "qtd_referencias": len(refs),
        "por_condicao": por_condicao,
        "condicoes": list(CONDICOES),
        "ultimos_resultados": resultados[-8:][::-1],
    }


def limpar_resultados() -> dict[str, Any]:
    """Remove saídas geradas sob resultados/, preservando README e estrutura base.

    Não apaga PDFs de entrada, referências manuais nem configuração.
    """
    if gerenciador.tem_job_ativo():
        raise RuntimeError(
            "Há um processamento em andamento. Cancele ou aguarde antes de limpar."
        )

    raiz = pasta_resultados()
    raiz.mkdir(parents=True, exist_ok=True)

    removidos = 0
    for item in list(raiz.iterdir()):
        if item.name.lower() == "readme.md":
            continue
        if item.is_dir():
            shutil.rmtree(item)
            removidos += 1
        elif item.is_file():
            item.unlink()
            removidos += 1

    for sub in (
        raiz / "experimentos" / "condicao_a",
        raiz / "experimentos" / "condicao_b",
        raiz / "experimentos" / "condicao_c",
        raiz / "metricas",
    ):
        sub.mkdir(parents=True, exist_ok=True)

    return {
        "itens_removidos": removidos,
        "qtd_resultados": len(listar_resultados()),
    }


def obter_config_legivel() -> dict[str, Any]:
    config = carregar_config()
    # Decimal não serializa direto
    config["tolerancia_monetaria"] = float(config["tolerancia_monetaria"])
    return {
        "default_path": str(caminho_config_padrao()),
        "instituicoes_path": str(caminho_instituicoes_padrao()),
        "config": config,
    }


def montar_config_ui() -> dict[str, Any]:
    """Campos editáveis + metadados para a tela de configuração."""
    config = carregar_config()
    classif = config["classificacao_pdf"]
    ocr = config["ocr"]
    instituicoes = carregar_json(caminho_instituicoes_padrao()).get("instituicoes", [])
    return {
        "tolerancia_monetaria": float(config["tolerancia_monetaria"]),
        "limiar_localizacao": int(config["limiar_localizacao"]),
        "min_caracteres_pagina": int(classif["min_caracteres_pagina_com_texto"]),
        "percentual_minimo_nativo": float(classif["percentual_minimo_nativo"]),
        "ocr_dpi": int(ocr["dpi"]),
        "ocr_workers": int(ocr.get("workers", 1)),
        "ocr_idioma": str(ocr.get("idioma", "por")),
        "tesseract_cmd": str(ocr.get("tesseract_cmd", "")),
        "qtd_pesos_localizacao": len(config.get("pesos_localizacao", {})),
        "qtd_mapa_ids": len(config.get("mapa_ids_documento", {})),
        "instituicoes": instituicoes,
        "default_path": str(caminho_config_padrao()),
        "instituicoes_path": str(caminho_instituicoes_padrao()),
    }


def salvar_config_ui(dados: dict[str, Any]) -> None:
    """Persiste campos editáveis em config/default.json preservando o restante."""
    path = caminho_config_padrao()
    atual = carregar_json(path)

    atual["tolerancia_monetaria"] = float(dados["tolerancia_monetaria"])
    atual["limiar_localizacao"] = int(dados["limiar_localizacao"])

    classif = atual.setdefault("classificacao_pdf", {})
    classif["min_caracteres_pagina_com_texto"] = int(dados["min_caracteres_pagina"])
    classif["percentual_minimo_nativo"] = float(dados["percentual_minimo_nativo"])

    ocr = atual.setdefault("ocr", {})
    ocr["dpi"] = int(dados["ocr_dpi"])
    workers = int(dados["ocr_workers"])
    if workers < 1 or workers > 8:
        raise ConfigInvalidaError("ocr.workers deve ser inteiro entre 1 e 8")
    ocr["workers"] = workers
    ocr["idioma"] = str(dados["ocr_idioma"]).strip() or "por"
    ocr["tesseract_cmd"] = str(dados["tesseract_cmd"]).strip()

    path.write_text(
        json.dumps(atual, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    carregar_config(caminho_default=path)


def salvar_upload_pdf(nome: str, conteudo: bytes) -> str:
    destino = pasta_entrada() / Path(nome).name
    if destino.suffix.lower() != ".pdf":
        raise ValueError("Apenas arquivos PDF são aceitos")
    destino.write_bytes(conteudo)
    return destino.name
