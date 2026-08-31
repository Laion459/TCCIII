from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class ErroNormalizacaoMonetaria(ValueError):
    """Valor monetário em formato inválido."""


def normalizar_monetario_br(valor: str) -> Decimal:
    """Converte string no padrão BR (1.234,56) para Decimal com 2 casas."""
    if valor is None:
        raise ErroNormalizacaoMonetaria("Valor monetário ausente")
    texto = str(valor).strip()
    if not texto:
        raise ErroNormalizacaoMonetaria("Valor monetário vazio")

    texto = texto.replace("R$", "").replace("r$", "").strip()
    texto = texto.replace(" ", "").rstrip("*")
    if not texto:
        raise ErroNormalizacaoMonetaria("Valor monetário vazio após limpeza")

    negativo = False
    if texto.startswith("-"):
        negativo = True
        texto = texto[1:]
    elif texto.endswith("-"):
        negativo = True
        texto = texto[:-1]

    if "," in texto:
        parte_int, parte_dec = texto.rsplit(",", 1)
        parte_int = parte_int.replace(".", "")
        texto_norm = f"{parte_int}.{parte_dec}"
    elif texto.count(".") == 1 and len(texto.split(".")[-1]) <= 2:
        texto_norm = texto
    else:
        texto_norm = texto.replace(".", "")

    try:
        numero = Decimal(texto_norm)
    except InvalidOperation as exc:
        raise ErroNormalizacaoMonetaria(f"Formato monetário inválido: {valor!r}") from exc

    if negativo:
        numero = -numero
    return numero.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
