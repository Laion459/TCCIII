from __future__ import annotations

from dataclasses import dataclass


CORPUS_NATIVO_ID = "pdf-nativo"
DPIS_RASTER = (100, 200, 300)


class CorpusDesconhecidoError(ValueError):
    """Identificador de corpus fora do catálogo do experimento."""


@dataclass(frozen=True)
class Corpus:
    id: str
    rotulo: str
    pasta: str
    dpi: int | None
    sintetico: bool

    @property
    def descricao(self) -> str:
        if not self.sintetico:
            return "PDF com texto nativo. Base original do experimento."
        return (
            f"Digitalização sintética a {self.dpi} DPI, só com imagem. "
            "O nome do arquivo e a referência manual são os do PDF nativo."
        )


def _catalogo() -> tuple[Corpus, ...]:
    nativo = Corpus(
        id=CORPUS_NATIVO_ID,
        rotulo="PDF nativo",
        pasta="pdf nativo",
        dpi=None,
        sintetico=False,
    )
    rasters = tuple(
        Corpus(
            id=f"pdf-{dpi}-dpi",
            rotulo=f"Rasterizado {dpi} DPI",
            pasta=f"pdf-{dpi}-dpi",
            dpi=dpi,
            sintetico=True,
        )
        for dpi in DPIS_RASTER
    )
    return (nativo, *rasters)


CORPORA: tuple[Corpus, ...] = _catalogo()
_POR_ID = {corpus.id: corpus for corpus in CORPORA}


def obter_corpus(corpus_id: str | None) -> Corpus:
    if corpus_id is None or str(corpus_id).strip() == "":
        return _POR_ID[CORPUS_NATIVO_ID]
    chave = str(corpus_id).strip()
    item = _POR_ID.get(chave)
    if item is None:
        conhecidos = ", ".join(corpus.id for corpus in CORPORA)
        raise CorpusDesconhecidoError(
            f"Corpus desconhecido: {chave}. Use um destes: {conhecidos}."
        )
    return item
