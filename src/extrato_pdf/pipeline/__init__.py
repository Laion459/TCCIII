from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
from typing import Any, Callable, Optional

from extrato_pdf import __version__
from extrato_pdf.modelos import (
    CamposExtraidos,
    CondicaoExperimental,
    ResultadoProcessamento,
    ResultadoValidacao,
    StatusProcessamento,
)
from extrato_pdf.modulos.classificador import classificar_pdf
from extrato_pdf.modulos.estrategia_texto import obter_texto_trabalho
from extrato_pdf.modulos.extrator_nativo import extrair_texto_nativo
from extrato_pdf.modulos.localizador import localizar_paginas_extrato
from extrato_pdf.modulos.parser import extrair_campos
from extrato_pdf.modulos.regras import aplicar_regras
from extrato_pdf.modulos.serializador import serializar_resultado
from extrato_pdf.modulos.validador import validar_pdf
from extrato_pdf.util.config import tolerancia
from extrato_pdf.util.progresso import CancelarFn, ProgressoFn, emitir, verificar_cancelamento


def _gerar_id(nome_arquivo: str, config: dict[str, Any]) -> str:
    mapa = config.get("mapa_ids_documento", {})
    if nome_arquivo in mapa:
        return mapa[nome_arquivo]
    return "D" + hashlib.sha1(nome_arquivo.encode("utf-8")).hexdigest()[:6].upper()


def _versoes() -> dict[str, str]:
    versoes = {"extrato_pdf": __version__}
    for pacote in ("pymupdf", "pytesseract", "pillow"):
        try:
            versoes[pacote] = importlib.metadata.version(pacote)
        except importlib.metadata.PackageNotFoundError:
            versoes[pacote] = "desconhecido"
    return versoes


def processar_pdf(
    caminho_pdf: str | Path,
    config: dict[str, Any],
    condicao: CondicaoExperimental = CondicaoExperimental.C,
    diretorio_saida: str | Path | None = None,
    id_documento: Optional[str] = None,
    ocr_fn: Optional[Callable[..., list]] = None,
    on_progress: Optional[ProgressoFn] = None,
    deve_cancelar: Optional[CancelarFn] = None,
) -> ResultadoProcessamento:
    path = Path(caminho_pdf)
    log: list[str] = []
    alertas: list[str] = []

    emitir(on_progress, {"etapa": "validacao"}, deve_cancelar=deve_cancelar)

    validacao_pdf = validar_pdf(path)
    log.append(f"validacao_pdf ok={validacao_pdf.valido} msg={validacao_pdf.mensagem}")
    if not validacao_pdf.valido:
        resultado = ResultadoProcessamento(
            id_documento=id_documento or _gerar_id(path.name, config),
            nome_arquivo=path.name,
            caminho_pdf=str(path),
            condicao=condicao,
            classificacao=None,
            campos=CamposExtraidos(),
            validacao=ResultadoValidacao(
                status_processamento=StatusProcessamento.NAO_PROCESSAVEL,
                consistente=False,
                revisao_humana=True,
                tolerancia=tolerancia(config),
                alertas=[validacao_pdf.mensagem or "PDF não processável"],
            ),
            versoes=_versoes(),
            parametros={
                "condicao": condicao.value,
                "limiar_localizacao": config.get("limiar_localizacao"),
            },
            log_etapas=log,
        )
        if diretorio_saida:
            serializar_resultado(resultado, diretorio_saida)
        return resultado

    emitir(on_progress, {"etapa": "texto_nativo"}, deve_cancelar=deve_cancelar)
    paginas_nativas = extrair_texto_nativo(path)
    log.append(f"texto_nativo paginas={len(paginas_nativas)}")

    verificar_cancelamento(deve_cancelar)
    emitir(on_progress, {"etapa": "classificacao"}, deve_cancelar=deve_cancelar)
    classificacao = classificar_pdf(paginas_nativas, config)
    log.append(
        f"classificacao tipo={classificacao.tipo.value} evidencia={classificacao.evidencia}"
    )

    estrategia = obter_texto_trabalho(
        path,
        paginas_nativas,
        classificacao,
        condicao,
        config,
        ocr_fn=ocr_fn,
        on_progress=on_progress,
        deve_cancelar=deve_cancelar,
    )
    alertas.extend(estrategia.alertas)
    ocr_workers = config.get("ocr", {}).get("workers", 1)
    log.append(
        f"estrategia_texto condicao={condicao.value} ocr_workers={ocr_workers} "
        f"origens={[p.origem.value for p in estrategia.paginas[:5]]}..."
    )

    emitir(on_progress, {"etapa": "localizacao"}, deve_cancelar=deve_cancelar)
    pontuadas = localizar_paginas_extrato(estrategia.paginas, config)
    log.append(
        "localizacao "
        + (
            ", ".join(f"p{p.numero}={p.score}" for p in pontuadas[:10])
            if pontuadas
            else "nenhuma_pagina"
        )
    )
    if not pontuadas:
        alertas.append("Extrato bancário não identificável (limiar de localização)")

    emitir(on_progress, {"etapa": "parser"}, deve_cancelar=deve_cancelar)
    campos = extrair_campos(estrategia.paginas, pontuadas, config)
    log.append(
        f"parser instituicao={campos.instituicao} "
        f"periodo={campos.periodo_inicio}/{campos.periodo_fim} "
        f"paginas={campos.paginas_utilizadas}"
    )

    emitir(on_progress, {"etapa": "regras"}, deve_cancelar=deve_cancelar)
    validacao = aplicar_regras(campos, tolerancia(config), alertas_previos=alertas)
    log.append(f"regras status={validacao.status_processamento.value}")

    resultado = ResultadoProcessamento(
        id_documento=id_documento or _gerar_id(path.name, config),
        nome_arquivo=path.name,
        caminho_pdf=str(path),
        condicao=condicao,
        classificacao=classificacao,
        campos=campos,
        validacao=validacao,
        paginas_pontuadas=pontuadas,
        versoes=_versoes(),
        parametros={
            "condicao": condicao.value,
            "limiar_localizacao": config.get("limiar_localizacao"),
            "ocr_dpi": config.get("ocr", {}).get("dpi"),
            "ocr_workers": config.get("ocr", {}).get("workers", 1),
            "min_caracteres_pagina": config["classificacao_pdf"][
                "min_caracteres_pagina_com_texto"
            ],
        },
        log_etapas=log,
    )
    if diretorio_saida:
        emitir(on_progress, {"etapa": "serializacao"}, deve_cancelar=deve_cancelar)
        destino = serializar_resultado(resultado, diretorio_saida)
        log.append(f"saida={destino}")
        resultado.log_etapas = log
        # regrava log completo
        serializar_resultado(resultado, diretorio_saida)
    return resultado
