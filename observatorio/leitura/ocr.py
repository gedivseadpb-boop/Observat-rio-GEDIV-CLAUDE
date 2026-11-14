"""Chamadas ao Tesseract com limite de tempo e sem disputa de threads.

Achado de 14/11/2026: seis leituras simultâneas (uma por processo, 4 núcleos) ficaram 24 minutos presas numa única
chamada ao Tesseract, que por padrão abre várias threads OpenMP por processo; as mesmas seis leituras com uma thread
por chamada terminaram em 44 s. Sem limite de tempo, uma chamada travada parava o robô indefinidamente.
"""
from __future__ import annotations

import os

# O processo do Tesseract herda o ambiente. Quem já definiu a variável (operador, executor) prevalece.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

TEMPO_MAXIMO_PADRAO = 120  # segundos por chamada; uma página inteira a 300 dpi leva poucos segundos


class OcrEsgotado(RuntimeError):
    """O Tesseract não respondeu dentro do tempo máximo. A página vira pendência; nada é aceito sem leitura."""


def tempo_maximo() -> float:
    try:
        valor = float(os.environ.get("GEDIV_OCR_TEMPO_MAXIMO", TEMPO_MAXIMO_PADRAO))
    except ValueError:
        return TEMPO_MAXIMO_PADRAO
    return valor if valor > 0 else TEMPO_MAXIMO_PADRAO


def _chamar(funcao, imagem, **k):
    try:
        return funcao(imagem, timeout=tempo_maximo(), **k)
    except RuntimeError as e:
        # pytesseract sinaliza o estouro com RuntimeError("Tesseract process timeout")
        if "timeout" in str(e).lower():
            raise OcrEsgotado(f"OCR excedeu {tempo_maximo():g} s") from e
        raise


def dados(imagem, config: str = ""):
    import pytesseract
    return _chamar(pytesseract.image_to_data, imagem, lang="por", config=config, output_type=pytesseract.Output.DICT)


def texto(imagem, config: str = "") -> str:
    import pytesseract
    return _chamar(pytesseract.image_to_string, imagem, lang="por", config=config)
