from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from extrato_pdf.corpora import (
    CORPUS_NATIVO_ID,
    CORPORA,
    CorpusDesconhecidoError,
    obter_corpus,
)
from extrato_pdf.modelos import CondicaoExperimental
from extrato_pdf.modulos.metricas import comparar_com_referencia
from extrato_pdf.pipeline import processar_pdf
from extrato_pdf.modulos.localizador import soma_pesos_positivos
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
from extrato_pdf.web.formatacao import formatar_periodo, preparar_relatorio
from extrato_pdf.web.jobs import ItemJob, StatusItem, StatusJob, gerenciador
from extrato_pdf.web.relatorio_metricas import gerar_arquivos_relatorio


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
    qtd_corpora: int = 1


VISAO_TODOS = "todos"


@dataclass
class ResumoResultado:
    pasta: str
    arquivo: str
    status: str
    instituicao: Optional[str]
    condicao: Optional[str]
    consistente: Optional[bool]
    caminho_relativo: str
    corpus_id: str = ""
    corpus_rotulo: str = ""
    dpi: Optional[int] = None
    tipo_pdf: Optional[str] = None
    periodo: str = "-"
    saldo_inicial: Optional[float] = None
    total_entradas: Optional[float] = None
    total_saidas: Optional[float] = None
    saldo_final: Optional[float] = None
    diferenca: Optional[float] = None
    duracao_s: Optional[float] = None
    paginas_ocr: Optional[int] = None
    paginas_extrato: list[int] = field(default_factory=list)


def nome_pdf_seguro(nome_pdf: str) -> str:
    nome = Path(nome_pdf).name
    if nome != nome_pdf or Path(nome).suffix.lower() != ".pdf":
        raise ValueError(f"Nome de PDF inválido: {nome_pdf}")
    return nome


def descrever_corpus(corpus_id: str | None) -> dict[str, Any]:
    corpus = obter_corpus(corpus_id)
    pasta = pasta_entrada() / corpus.pasta
    qtd = len(list(pasta.glob("*.pdf"))) if pasta.is_dir() else 0
    gravacao = pasta_gravacao_corpus(corpus.id)
    leitura = pasta_leitura_corpus(corpus.id)
    return {
        "id": corpus.id,
        "rotulo": corpus.rotulo,
        "descricao": corpus.descricao,
        "sintetico": corpus.sintetico,
        "dpi": corpus.dpi,
        "qtd": qtd,
        "pasta": corpus.pasta,
        "leitura_legada": leitura.resolve() != gravacao.resolve(),
    }


def resumir_corpora() -> list[dict[str, Any]]:
    return [descrever_corpus(corpus.id) for corpus in CORPORA]


def pasta_gravacao_corpus(corpus_id: str | None) -> Path:
    corpus = obter_corpus(corpus_id)
    return pasta_experimentos() / corpus.id


def _tem_resultado_json(pasta: Path) -> bool:
    if not pasta.is_dir():
        return False
    return next(pasta.rglob("resultado.json"), None) is not None


def _legado_nativo_tem_resultado() -> bool:
    base = pasta_experimentos()
    return any(_tem_resultado_json(base / f"condicao_{cond.lower()}") for cond in CONDICOES)


def pasta_leitura_corpus(corpus_id: str | None) -> Path:
    """Pasta que contém condicao_a/b/c. O nativo antigo continua legível até a próxima bateria."""
    corpus = obter_corpus(corpus_id)
    nova = pasta_gravacao_corpus(corpus.id)
    if (
        corpus.id == CORPUS_NATIVO_ID
        and not _tem_resultado_json(nova)
        and _legado_nativo_tem_resultado()
    ):
        return pasta_experimentos()
    return nova


def _caminhos_resultado(
    corpus_id: str | None = None,
    condicao: str | None = None,
) -> list[Path]:
    base = pasta_leitura_corpus(corpus_id)
    condicoes = (condicao,) if condicao else CONDICOES
    caminhos: list[Path] = []
    for cond in condicoes:
        pasta = base / f"condicao_{cond.lower()}"
        if pasta.is_dir():
            caminhos.extend(sorted(pasta.rglob("resultado.json")))
    return caminhos


def listar_pdfs_esteira() -> list[ResumoPdf]:
    """Nomes únicos entre os corpora. O tamanho exibido é o do PDF nativo, quando existe."""
    por_nome: dict[str, tuple[ResumoPdf, int]] = {}
    for corpus in CORPORA:
        for item in listar_pdfs_entrada(corpus.id):
            atual, qtd = por_nome.get(item.nome, (item, 0))
            escolhido = item if corpus.id == CORPUS_NATIVO_ID or item.nome not in por_nome else atual
            por_nome[item.nome] = (escolhido, qtd + 1)
    lista: list[ResumoPdf] = []
    for nome in sorted(por_nome):
        resumo, qtd = por_nome[nome]
        lista.append(
            ResumoPdf(
                nome=resumo.nome,
                tamanho_mb=resumo.tamanho_mb,
                modificado=resumo.modificado,
                qtd_corpora=qtd,
            )
        )
    return lista


def normalizar_condicoes(valores: list[str] | None) -> list[str]:
    if not valores:
        raise ValueError("Selecione ao menos uma condição (A, B ou C).")
    pedidos = {str(valor).strip().upper() for valor in valores if str(valor).strip()}
    invalidos = sorted(pedidos - set(CONDICOES))
    if invalidos:
        raise ValueError(f"Condição desconhecida: {', '.join(invalidos)}.")
    return [condicao for condicao in CONDICOES if condicao in pedidos]


def normalizar_corpora(valores: list[str] | None) -> list[str]:
    if not valores:
        raise ValueError("Selecione ao menos um corpus.")
    pedidos = {str(valor).strip() for valor in valores if str(valor).strip()}
    desconhecidos = sorted(pedidos - {corpus.id for corpus in CORPORA})
    if desconhecidos:
        raise CorpusDesconhecidoError(
            "Corpus desconhecido: "
            + ", ".join(desconhecidos)
            + ". Use um destes: "
            + ", ".join(corpus.id for corpus in CORPORA)
            + "."
        )
    return [corpus.id for corpus in CORPORA if corpus.id in pedidos]


def montar_esteira(
    corpora_ids: list[str] | None,
    condicoes: list[str] | None,
    nomes: list[str] | None,
) -> list[ItemJob]:
    """Corpus na ordem do catálogo, condição A depois B depois C, PDF na ordem recebida."""
    ids = normalizar_corpora(corpora_ids)
    ordem_condicoes = normalizar_condicoes(condicoes)
    if nomes is not None and not nomes:
        raise ValueError("Nenhum PDF selecionado")
    escolhidos = [nome_pdf_seguro(nome) for nome in nomes] if nomes is not None else None
    itens: list[ItemJob] = []
    for corpus_id in ids:
        presentes = [pdf.nome for pdf in listar_pdfs_entrada(corpus_id)]
        arquivos = presentes if escolhidos is None else [nome for nome in escolhidos if nome in presentes]
        for condicao in ordem_condicoes:
            for nome in arquivos:
                itens.append(ItemJob(arquivo=nome, corpus=corpus_id, condicao=condicao))
    if not itens:
        raise ValueError("Nenhum PDF encontrado nos corpora selecionados")
    return itens


def listar_pdfs_entrada(corpus_id: str | None = None) -> list[ResumoPdf]:
    corpus = obter_corpus(corpus_id)
    pasta = pasta_entrada() / corpus.pasta
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


def eh_visao_todos(corpus_id: str | None) -> bool:
    return str(corpus_id or "").strip().lower() == VISAO_TODOS


def descrever_visao(corpus_id: str | None) -> dict[str, Any]:
    """Corpus de leitura, ou a visão que junta nativo e os três DPIs."""
    if eh_visao_todos(corpus_id):
        return {
            "id": VISAO_TODOS,
            "rotulo": "Todos os corpora",
            "descricao": (
                "PDF nativo e rasters de 100, 200 e 300 DPI lado a lado. "
                "Cada execução continua gravada na própria pasta."
            ),
            "sintetico": False,
            "dpi": None,
            "qtd": len(CORPORA),
            "pasta": "",
            "leitura_legada": False,
        }
    return descrever_corpus(corpus_id)


def _resumo_resultado(json_path: Path, corpus_id: str | None) -> ResumoResultado | None:
    try:
        dados = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    cond_item = dados.get("experimento", {}).get("condicao")
    if not cond_item:
        for parte in json_path.parts:
            if parte.startswith("condicao_"):
                cond_item = parte.replace("condicao_", "").upper()
                break
    corpus = obter_corpus(corpus_id) if corpus_id else None
    valores = dados.get("valores", {})
    extrato = dados.get("extrato", {})
    periodo = extrato.get("periodo") or {}
    experimento = dados.get("experimento", {})
    rel = json_path.parent.relative_to(raiz_projeto())
    return ResumoResultado(
        pasta=json_path.parent.name,
        arquivo=dados.get("documento", {}).get("arquivo", json_path.parent.name),
        status=dados.get("validacao", {}).get("status_processamento", "?"),
        instituicao=extrato.get("instituicao"),
        condicao=cond_item,
        consistente=dados.get("validacao", {}).get("consistente"),
        caminho_relativo=str(rel).replace("\\", "/"),
        corpus_id=corpus.id if corpus else "",
        corpus_rotulo=corpus.rotulo if corpus else "",
        dpi=corpus.dpi if corpus else None,
        tipo_pdf=dados.get("documento", {}).get("tipo_pdf"),
        periodo=formatar_periodo(periodo.get("inicio"), periodo.get("fim")),
        saldo_inicial=valores.get("saldo_inicial"),
        total_entradas=valores.get("total_entradas"),
        total_saidas=valores.get("total_saidas"),
        saldo_final=valores.get("saldo_final_informado"),
        diferenca=valores.get("diferenca"),
        duracao_s=experimento.get("duracao_s"),
        paginas_ocr=experimento.get("paginas_ocr"),
        paginas_extrato=list(experimento.get("paginas_extrato") or []),
    )


def listar_resultados(
    base: Path | None = None,
    condicao: str | None = None,
    corpus: str | None = None,
) -> list[ResumoResultado]:
    """Lista resultados de um corpus. `corpus='todos'` junta nativo e os três DPIs."""
    cond = (condicao or "").strip().upper() or None
    if cond not in CONDICOES:
        cond = None
    if base is None and eh_visao_todos(corpus):
        itens: list[ResumoResultado] = []
        for item_corpus in CORPORA:
            itens.extend(listar_resultados(condicao=cond, corpus=item_corpus.id))
        return itens
    if base is None:
        caminhos = _caminhos_resultado(corpus, cond)
    else:
        caminhos = []
        condicoes = (cond,) if cond else CONDICOES
        for item in condicoes:
            pasta = base / f"condicao_{item.lower()}"
            if pasta.is_dir():
                caminhos.extend(sorted(pasta.rglob("resultado.json")))
    itens = []
    for json_path in caminhos:
        resumo = _resumo_resultado(json_path, None if base is not None else corpus)
        if resumo is None:
            continue
        if cond in CONDICOES and resumo.condicao and str(resumo.condicao).upper() != cond:
            continue
        itens.append(resumo)
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


def _corpus_id_do_caminho(caminho_relativo: str) -> str:
    partes = Path(caminho_relativo).parts
    if "experimentos" not in partes:
        return CORPUS_NATIVO_ID
    indice = partes.index("experimentos")
    if indice + 1 < len(partes):
        candidato = partes[indice + 1]
        if any(corpus.id == candidato for corpus in CORPORA):
            return candidato
    return CORPUS_NATIVO_ID


def buscar_condicoes_alternativas(
    dados: dict[str, Any],
    caminho_atual: str,
) -> list[dict[str, Any]]:
    """Outras condições experimentais para o mesmo PDF, no mesmo corpus."""
    arquivo = dados.get("documento", {}).get("arquivo", "")
    condicao_atual = dados.get("experimento", {}).get("condicao")
    if not arquivo:
        return []

    stem = Path(arquivo).stem
    base = pasta_leitura_corpus(_corpus_id_do_caminho(caminho_atual))
    alternativas: list[dict[str, Any]] = []
    for cond in ("A", "B", "C"):
        if cond == condicao_atual:
            continue
        pasta = base / f"condicao_{cond.lower()}" / stem
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
    corpus: str | None = None,
) -> dict[str, Any]:
    nome = nome_pdf_seguro(nome_pdf)
    item_corpus = obter_corpus(corpus)
    pdf = pasta_entrada() / item_corpus.pasta / nome
    if not pdf.exists():
        raise FileNotFoundError(
            f"PDF não encontrado em dados/entrada/{item_corpus.pasta}/: {nome}"
        )
    config = carregar_config()
    cond = CondicaoExperimental(condicao.upper())
    if destino_rel:
        saida = raiz_projeto() / destino_rel
    else:
        saida = pasta_gravacao_corpus(item_corpus.id) / f"condicao_{cond.value.lower()}"
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
    corpus: str | None = None,
    condicoes: list[str] | None = None,
    corpora: list[str] | None = None,
) -> dict[str, Any]:
    """Processamento síncrono (fallback sem JavaScript)."""
    fila = montar_esteira(
        corpora if corpora is not None else ([corpus] if corpus else [CORPUS_NATIVO_ID]),
        condicoes if condicoes is not None else ([condicao] if condicao else ["A"]),
        nomes,
    )
    inicio_total = time.perf_counter()
    itens = []
    contagem: dict[str, int] = {}
    for passo in fila:
        try:
            item = processar_um(passo.arquivo, condicao=passo.condicao, corpus=passo.corpus)
            item["corpus"] = passo.corpus
            item["condicao"] = passo.condicao
            itens.append(item)
            contagem[item["status"]] = contagem.get(item["status"], 0) + 1
        except Exception as exc:  # noqa: BLE001
            itens.append(
                {
                    "arquivo": passo.arquivo,
                    "corpus": passo.corpus,
                    "condicao": passo.condicao,
                    "status": "erro",
                    "erro": str(exc),
                    "consistente": False,
                    "duracao_s": 0,
                }
            )
            contagem["erro"] = contagem.get("erro", 0) + 1

    return {
        "condicao": "+".join(dict.fromkeys(passo.condicao for passo in fila)),
        "total": len(itens),
        "contagem": contagem,
        "duracao_total_s": round(time.perf_counter() - inicio_total, 2),
        "itens": itens,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "corpus": ",".join(dict.fromkeys(passo.corpus for passo in fila)),
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
    job.status = StatusJob.EXECUTANDO
    job.iniciado_em = time.perf_counter()
    job.adicionar_log(f"Esteira com {job.total} execução(ões)")
    grupo_atual: tuple[str, str] | None = None

    for idx, item in enumerate(job.itens):
        if job.cancelar:
            job.status = StatusJob.CANCELADO
            job.mensagem = "Cancelado pelo usuário"
            job.adicionar_log("Lote cancelado")
            return

        grupo = (item.corpus, item.condicao)
        if grupo != grupo_atual:
            grupo_atual = grupo
            rotulo = obter_corpus(item.corpus).rotulo
            job.adicionar_log(f"- {rotulo} · condição {item.condicao}")

        job.indice_atual = idx + 1
        job.arquivo_atual = item.arquivo
        item.status = StatusItem.PROCESSANDO
        item.mensagem = "Extraindo texto e validando..."
        job.mensagem = (
            f"{obter_corpus(item.corpus).rotulo} · {item.condicao} · "
            f"{item.arquivo} ({idx + 1}/{job.total})"
        )
        job.adicionar_log(f"→ {item.condicao} {item.arquivo}")

        inicio = time.perf_counter()
        try:
            callback = _criar_callback_progresso(job, item)
            resultado = processar_um(
                item.arquivo,
                condicao=item.condicao,
                on_progress=callback,
                deve_cancelar=lambda: job.cancelar,
                corpus=item.corpus,
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
            job.adicionar_log(
                f"✓ {item.condicao} {item.arquivo} - {resultado['status']} ({item.duracao_s}s)"
            )
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
            job.adicionar_log(f"✗ {item.condicao} {item.arquivo} - {exc}")

    job.arquivo_atual = None
    job.status = StatusJob.CONCLUIDO
    job.mensagem = f"Concluído - {job.concluidos}/{job.total} execução(ões)"
    job.adicionar_log("Esteira finalizada")


def _executar_job_unitario(job) -> None:
    _executar_job_lote(job)


def iniciar_lote_async(
    condicao: str | None = None,
    nomes: list[str] | None = None,
    corpus: str | None = None,
    condicoes: list[str] | None = None,
    corpora: list[str] | None = None,
):
    itens = montar_esteira(
        corpora if corpora is not None else ([corpus] if corpus else [CORPUS_NATIVO_ID]),
        condicoes if condicoes is not None else ([condicao] if condicao else ["A"]),
        nomes,
    )
    job = gerenciador.criar_esteira("lote", itens)
    gerenciador.executar_em_thread(job, _executar_job_lote)
    return job


def iniciar_unitario_async(
    arquivo: str,
    condicao: str | None = None,
    corpus: str | None = None,
    condicoes: list[str] | None = None,
    corpora: list[str] | None = None,
):
    itens = montar_esteira(
        corpora if corpora is not None else ([corpus] if corpus else [CORPUS_NATIVO_ID]),
        condicoes if condicoes is not None else ([condicao] if condicao else ["C"]),
        [arquivo],
    )
    tipo = "unitario" if len(itens) == 1 else "lote"
    job = gerenciador.criar_esteira(tipo, itens)
    gerenciador.executar_em_thread(job, _executar_job_lote)
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


def calcular_metricas(corpus: str | None = None) -> dict[str, Any]:
    item_corpus = obter_corpus(corpus)
    config = carregar_config()
    tol = tolerancia(config)
    refs = []
    for path in pasta_referencias().glob("*.json"):
        if path.name == "exemplo_formato.json":
            continue
        refs.append(json.loads(path.read_text(encoding="utf-8")))

    metricas = []
    for json_path in _caminhos_resultado(item_corpus.id):
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

    saida = pasta_resultados() / "metricas" / item_corpus.id
    saida.mkdir(parents=True, exist_ok=True)
    out = saida / "metricas.json"
    out.write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    laboratorio = montar_laboratorio(metricas, pasta_leitura_corpus(item_corpus.id))
    return {
        "total": len(metricas),
        "itens": metricas,
        "arquivo": str(out),
        "laboratorio": laboratorio,
        "corpus": descrever_corpus(item_corpus.id),
    }


def gerar_relatorio_metricas(corpus: str | None = None) -> dict[str, Any]:
    """Gera relatório Markdown + JSON consolidado (mais completo que o painel)."""
    item_corpus = obter_corpus(corpus)
    config = carregar_config()
    saida = pasta_resultados() / "metricas" / item_corpus.id
    meta = gerar_arquivos_relatorio(
        pasta_experimentos=pasta_leitura_corpus(item_corpus.id),
        pasta_refs=pasta_referencias(),
        pasta_saida=saida,
        tolerancia=tolerancia(config),
        corpus_rotulo=item_corpus.rotulo,
    )
    return {
        "caminho_markdown": str(meta["markdown_path"]),
        "caminho_latest": str(meta["markdown_latest"]),
        "caminho_json": str(meta["json_path"]),
        "nome_arquivo": meta["markdown_path"].name,
        "gerado_em": meta["gerado_em"],
        "qtd_metricas": meta["qtd_metricas"],
        "veredito": meta["veredito"],
        "bytes": meta["markdown_path"].stat().st_size,
    }


def matriz_experimental() -> list[dict[str, Any]]:
    """Taxa de consistência de cada corpus em A, B e C, sem somar os corpora."""
    linhas: list[dict[str, Any]] = []
    for corpus in CORPORA:
        agregado = agregar_corpus_experimentos(pasta_leitura_corpus(corpus.id))
        celulas = []
        for cond in CONDICOES:
            info = agregado.get(cond, {})
            celulas.append(
                {
                    "condicao": cond,
                    "total": int(info.get("total", 0)),
                    "taxa_consistente": float(info.get("taxa_consistente", 0.0)),
                    "por_status": dict(info.get("por_status") or {}),
                    "href": f"/resultados?corpus={corpus.id}&condicao={cond}",
                }
            )
        linhas.append(
            {
                "id": corpus.id,
                "rotulo": corpus.rotulo,
                "dpi": corpus.dpi,
                "sintetico": corpus.sintetico,
                "celulas": celulas,
            }
        )
    return linhas


def parametros_experimento() -> dict[str, Any]:
    config = carregar_config()
    ocr = config.get("ocr", {})
    classif = config.get("classificacao_pdf", {})
    return {
        "tolerancia": float(config.get("tolerancia_monetaria", 0)),
        "limiar_localizacao": config.get("limiar_localizacao"),
        "ocr_dpi": ocr.get("dpi"),
        "ocr_workers": ocr.get("workers"),
        "ocr_idioma": ocr.get("idioma"),
        "min_caracteres": classif.get("min_caracteres_pagina_com_texto"),
        "percentual_nativo": classif.get("percentual_minimo_nativo"),
    }


def _referencias_manuais() -> list[dict[str, Any]]:
    refs = []
    for path in pasta_referencias().glob("*.json"):
        if path.name.startswith("_") or path.name == "exemplo_formato.json":
            continue
        refs.append(json.loads(path.read_text(encoding="utf-8")))
    return refs


def _referencia_do_arquivo(
    refs: list[dict[str, Any]], arquivo: str
) -> dict[str, Any] | None:
    return next(
        (
            ref
            for ref in refs
            if ref.get("documento") == arquivo or arquivo in str(ref.get("documento", ""))
        ),
        None,
    )


def comparacao_entre_corpora() -> dict[str, Any]:
    """Uma linha por execução, com o gabarito, para nativo e cada DPI."""
    tol = tolerancia(carregar_config())
    refs = _referencias_manuais()
    linhas: list[dict[str, Any]] = []
    for corpus in CORPORA:
        for json_path in _caminhos_resultado(corpus.id):
            try:
                resultado = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            arquivo = resultado.get("documento", {}).get("arquivo", "")
            ref = _referencia_do_arquivo(refs, arquivo)
            metrica = comparar_com_referencia(resultado, ref, tol) if ref else {}
            experimento = resultado.get("experimento", {})
            valores = resultado.get("valores", {})
            rel = str(json_path.parent.relative_to(raiz_projeto())).replace("\\", "/")
            linhas.append(
                {
                    "documento": arquivo,
                    "corpus_id": corpus.id,
                    "corpus_rotulo": corpus.rotulo,
                    "dpi": corpus.dpi,
                    "condicao": experimento.get("condicao"),
                    "tipo_pdf": resultado.get("documento", {}).get("tipo_pdf"),
                    "status_processamento": resultado.get("validacao", {}).get(
                        "status_processamento"
                    ),
                    "acerto_instituicao": metrica.get("acerto_instituicao"),
                    "acerto_periodo": metrica.get("acerto_periodo"),
                    "acerto_saldo_inicial": metrica.get("acerto_saldo_inicial"),
                    "erro_entradas": metrica.get("erro_entradas"),
                    "erro_saidas": metrica.get("erro_saidas"),
                    "erro_saldo_final_informado": metrica.get(
                        "erro_saldo_final_informado"
                    ),
                    "paginas_f1": metrica.get("paginas_f1"),
                    "consistente": resultado.get("validacao", {}).get("consistente"),
                    "duracao_s": experimento.get("duracao_s"),
                    "paginas_ocr": experimento.get("paginas_ocr"),
                    "saldo_final_informado": valores.get("saldo_final_informado"),
                    "caminho_resultado": rel,
                }
            )
    return {"linhas": linhas, "matriz": matriz_experimental()}


def resumo_dashboard(corpus_id: str | None = None) -> dict[str, Any]:
    """Resumo do painel com métricas separadas por condição A/B/C (sem misturar)."""
    item_corpus = obter_corpus(corpus_id)
    pdfs = listar_pdfs_entrada(item_corpus.id)
    resultados = listar_resultados(corpus=item_corpus.id)
    refs = [
        p.name
        for p in pasta_referencias().glob("*.json")
        if not p.name.startswith("_") and p.name != "exemplo_formato.json"
    ]
    agregado = agregar_corpus_experimentos(pasta_leitura_corpus(item_corpus.id))
    por_condicao = []
    for cond in CONDICOES:
        info = agregado.get(cond, {})
        por_condicao.append(
            {
                "condicao": cond,
                "total": int(info.get("total", 0)),
                "por_status": dict(info.get("por_status") or {}),
                "taxa_consistente": float(info.get("taxa_consistente", 0.0)),
                "href_resultados": f"/resultados?corpus={item_corpus.id}&condicao={cond}",
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

    for corpus in CORPORA:
        (raiz / "experimentos" / corpus.id).mkdir(parents=True, exist_ok=True)
    (raiz / "metricas").mkdir(parents=True, exist_ok=True)

    return {
        "itens_removidos": removidos,
        "qtd_resultados": len(listar_resultados()),
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
    limiar = int(dados["limiar_localizacao"])
    teto = soma_pesos_positivos(atual["pesos_localizacao"])
    if limiar > teto:
        raise ConfigInvalidaError(
            f"limiar_localizacao ({limiar}) excede a soma dos pesos positivos ({teto})"
        )
    atual["limiar_localizacao"] = limiar

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
    nome_seguro = nome_pdf_seguro(Path(nome).name)
    destino = pasta_entrada() / obter_corpus(CORPUS_NATIVO_ID).pasta / nome_seguro
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    return destino.name
