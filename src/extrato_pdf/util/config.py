from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any


class ConfigInvalidaError(ValueError):
    """Configuração ausente ou inválida."""


def _raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[3]


def caminho_config_padrao() -> Path:
    return _raiz_projeto() / "config" / "default.json"


def caminho_instituicoes_padrao() -> Path:
    return _raiz_projeto() / "config" / "instituicoes.json"


def carregar_json(caminho: Path) -> dict[str, Any]:
    if not caminho.exists():
        raise ConfigInvalidaError(f"Arquivo de configuração não encontrado: {caminho}")
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigInvalidaError(f"JSON inválido em {caminho}: {exc}") from exc
    if not isinstance(dados, dict):
        raise ConfigInvalidaError(f"Configuração deve ser um objeto JSON: {caminho}")
    return dados


def carregar_config(
    caminho_default: Path | None = None,
    caminho_instituicoes: Path | None = None,
) -> dict[str, Any]:
    default_path = caminho_default or caminho_config_padrao()
    inst_path = caminho_instituicoes or caminho_instituicoes_padrao()
    config = deepcopy(carregar_json(default_path))
    instituicoes = carregar_json(inst_path)
    config["instituicoes"] = instituicoes.get("instituicoes", [])
    _validar_config(config)
    return config


def _validar_config(config: dict[str, Any]) -> None:
    obrigatorios = [
        "tolerancia_monetaria",
        "limiar_localizacao",
        "pesos_localizacao",
        "classificacao_pdf",
        "ocr",
    ]
    for chave in obrigatorios:
        if chave not in config:
            raise ConfigInvalidaError(f"Chave obrigatória ausente: {chave}")
    classif = config["classificacao_pdf"]
    for chave in ("min_caracteres_pagina_com_texto", "percentual_minimo_nativo"):
        if not isinstance(classif.get(chave), (int, float)):
            raise ConfigInvalidaError(
                f"classificacao_pdf.{chave} deve ser numérico (DP03 resolvido)"
            )
    ocr = config["ocr"]
    if not isinstance(ocr.get("dpi"), int):
        raise ConfigInvalidaError("ocr.dpi deve ser inteiro")
    workers = ocr.get("workers", 1)
    if not isinstance(workers, int) or workers < 1 or workers > 8:
        raise ConfigInvalidaError("ocr.workers deve ser inteiro entre 1 e 8")
    config["tolerancia_monetaria"] = Decimal(str(config["tolerancia_monetaria"]))


def tolerancia(config: dict[str, Any]) -> Decimal:
    return Decimal(str(config["tolerancia_monetaria"]))
