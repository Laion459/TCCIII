from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from extrato_pdf.corpora import DPIS_RASTER


TOLERANCIA_PONTO = 0.5


class RasterInvalidoError(ValueError):
    """PDF rasterizado não cumpre página, tamanho ou ausência de texto."""


@dataclass(frozen=True)
class ItemRaster:
    arquivo: str
    dpi: int
    status: str
    detalhe: str
    duracao_s: float


@dataclass(frozen=True)
class ResumoRaster:
    nativos: int
    esperados: int
    gerados: int
    reaproveitados: int
    falhas: tuple[str, ...]
    duracao_s: float

    @property
    def sucesso(self) -> int:
        return self.gerados + self.reaproveitados


def rasterizar_pdf(origem: Path, destino: Path, dpi: int) -> None:
    """Gera um PDF só com imagem, sem reaproveitar texto ou vetor do original."""
    if dpi < 1:
        raise ValueError(f"DPI inválido: {dpi}")
    origem_resolvida = origem.resolve()
    destino_resolvido = destino.resolve()
    if origem_resolvida == destino_resolvido:
        raise ValueError("O destino não pode ser o PDF original")
    if not origem_resolvida.is_file():
        raise FileNotFoundError(origem)
    if _esta_dentro(destino_resolvido, origem_resolvida.parent):
        raise ValueError("O destino não pode ficar na pasta do PDF original")

    destino_resolvido.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".raster-{dpi}-",
        dir=destino_resolvido.parent,
    ) as temporario:
        parcial = Path(temporario) / destino_resolvido.name
        _gravar_somente_imagem(origem_resolvida, parcial, dpi)
        validar_raster(origem_resolvida, parcial)
        os.replace(parcial, destino_resolvido)


def validar_raster(origem: Path, destino: Path) -> None:
    if not destino.is_file():
        raise RasterInvalidoError(f"arquivo ausente: {destino.name}")
    if destino.stat().st_size == 0:
        raise RasterInvalidoError(f"arquivo vazio: {destino.name}")

    with pymupdf.open(origem) as original, pymupdf.open(destino) as gerado:
        if gerado.page_count != original.page_count:
            raise RasterInvalidoError(
                f"{destino.name}: {gerado.page_count} páginas, "
                f"original tem {original.page_count}"
            )
        if gerado.page_count == 0:
            raise RasterInvalidoError(f"{destino.name}: PDF sem páginas")
        for indice, (pagina_original, pagina_gerada) in enumerate(
            zip(original, gerado),
            start=1,
        ):
            _validar_pagina(destino.name, indice, pagina_original, pagina_gerada)


def gerar_corpus_rasterizado(
    pasta_nativo: Path,
    pasta_entrada: Path,
    dpis: tuple[int, ...] = DPIS_RASTER,
    forcar: bool = False,
    ao_iniciar: Callable[[str, int], None] | None = None,
    ao_concluir: Callable[[ItemRaster], None] | None = None,
) -> ResumoRaster:
    """Rasteriza cada PDF nativo nos DPIs pedidos, sem interromper o lote numa falha."""
    inicio = time.perf_counter()
    if not pasta_nativo.is_dir():
        raise FileNotFoundError(f"Pasta de PDFs nativos não encontrada: {pasta_nativo}")

    nativos = sorted(pasta_nativo.glob("*.pdf"), key=lambda caminho: caminho.name)
    falhas: list[str] = []
    gerados = 0
    reaproveitados = 0
    for origem in nativos:
        for dpi in dpis:
            destino = pasta_entrada / f"pdf-{dpi}-dpi" / origem.name
            if ao_iniciar:
                ao_iniciar(origem.name, dpi)
            item = _processar_um(origem, destino, dpi, pasta_nativo, forcar)
            if ao_concluir:
                ao_concluir(item)
            if item.status == "gerado":
                gerados += 1
            elif item.status == "reaproveitado":
                reaproveitados += 1
            else:
                falhas.append(f"{origem.name} @ {dpi} DPI: {item.detalhe}")
    return ResumoRaster(
        nativos=len(nativos),
        esperados=len(nativos) * len(dpis),
        gerados=gerados,
        reaproveitados=reaproveitados,
        falhas=tuple(falhas),
        duracao_s=round(time.perf_counter() - inicio, 2),
    )


def _processar_um(
    origem: Path,
    destino: Path,
    dpi: int,
    pasta_nativo: Path,
    forcar: bool,
) -> ItemRaster:
    inicio = time.perf_counter()
    try:
        if _esta_dentro(destino.resolve(), pasta_nativo.resolve()):
            raise ValueError("destino dentro da pasta nativa")
        if not forcar and destino.is_file() and _raster_aceito(origem, destino):
            return ItemRaster(
                origem.name,
                dpi,
                "reaproveitado",
                "já válido",
                round(time.perf_counter() - inicio, 2),
            )
        rasterizar_pdf(origem, destino, dpi)
        return ItemRaster(
            origem.name,
            dpi,
            "gerado",
            "ok",
            round(time.perf_counter() - inicio, 2),
        )
    except Exception as exc:  # noqa: BLE001
        return ItemRaster(
            origem.name,
            dpi,
            "falha",
            str(exc),
            round(time.perf_counter() - inicio, 2),
        )
    finally:
        _limpar_residuos(destino.parent)


def _gravar_somente_imagem(origem: Path, destino: Path, dpi: int) -> None:
    zoom = dpi / 72.0
    matriz = pymupdf.Matrix(zoom, zoom)
    original = pymupdf.open(origem)
    saida = pymupdf.open()
    try:
        for pagina in original:
            pixmap = pagina.get_pixmap(matrix=matriz, alpha=False, colorspace=pymupdf.csRGB)
            nova = saida.new_page(width=pagina.rect.width, height=pagina.rect.height)
            nova.insert_image(nova.rect, pixmap=pixmap)
            del pixmap
        saida.set_metadata(
            {
                "producer": f"extrato_pdf rasterizador sintetico {dpi} dpi",
                "creator": "extrato_pdf",
                "title": "",
                "author": "",
                "subject": f"digitalizacao sintetica {dpi} dpi",
                "keywords": "",
            }
        )
        saida.save(destino, garbage=4, deflate=True)
    finally:
        saida.close()
        original.close()


def _validar_pagina(
    nome: str,
    indice: int,
    original: pymupdf.Page,
    gerada: pymupdf.Page,
) -> None:
    if abs(gerada.rect.width - original.rect.width) > TOLERANCIA_PONTO:
        raise RasterInvalidoError(f"{nome} página {indice}: largura diferente")
    if abs(gerada.rect.height - original.rect.height) > TOLERANCIA_PONTO:
        raise RasterInvalidoError(f"{nome} página {indice}: altura diferente")
    if gerada.get_text("text").strip():
        raise RasterInvalidoError(f"{nome} página {indice}: ainda há texto extraível")
    if not gerada.get_images():
        raise RasterInvalidoError(f"{nome} página {indice}: não contém imagem")


def _raster_aceito(origem: Path, destino: Path) -> bool:
    try:
        validar_raster(origem, destino)
    except Exception:
        return False
    return True


def _esta_dentro(caminho: Path, pasta: Path) -> bool:
    try:
        caminho.relative_to(pasta)
    except ValueError:
        return False
    return True


def _limpar_residuos(pasta: Path) -> None:
    if not pasta.is_dir():
        return
    for residuo in pasta.iterdir():
        if residuo.name.startswith(".raster-") and residuo.is_dir():
            shutil.rmtree(residuo, ignore_errors=True)
