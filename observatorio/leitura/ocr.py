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


# ---------------------------------------------------------------------------------------------------------------
# Etapa 05.3.4 — limites por PÁGINA e por ARQUIVO. O limite por chamada não basta: uma página com dezenas de trechos
# ilegíveis faz dezenas de chamadas, cada uma dentro do seu tempo, e o arquivo pode levar horas. Estourado o limite, a
# próxima chamada levanta OcrEsgotado: a página fica com o texto nativo e vira pendência (nova tentativa com
# `--refazer-pendentes`); nada é aceito sem leitura e o robô segue adiante.
# ---------------------------------------------------------------------------------------------------------------
TEMPO_PAGINA_PADRAO = 300      # segundos de OCR por página
TEMPO_ARQUIVO_PADRAO = 1800    # segundos de OCR por arquivo
CHAMADAS_PAGINA_PADRAO = 80    # chamadas ao Tesseract por página (trechos, colunas de tabela, palavras, linhas)
_uso = {"pagina": 0.0, "arquivo": 0.0, "chamadas": 0}


def _limite(variavel: str, padrao: float) -> float:
    try:
        valor = float(os.environ.get(variavel, padrao))
    except ValueError:
        return padrao
    return valor if valor > 0 else padrao


def iniciar_arquivo() -> None:
    _uso.update(pagina=0.0, arquivo=0.0, chamadas=0)


def iniciar_pagina() -> None:
    _uso.update(pagina=0.0, chamadas=0)


def uso() -> dict:
    return dict(_uso)


def _folga() -> float:
    """Segundos que a próxima chamada ainda pode usar; levanta OcrEsgotado se algum limite já foi atingido."""
    pagina = _limite("GEDIV_OCR_TEMPO_PAGINA", TEMPO_PAGINA_PADRAO) - _uso["pagina"]
    arquivo = _limite("GEDIV_OCR_TEMPO_ARQUIVO", TEMPO_ARQUIVO_PADRAO) - _uso["arquivo"]
    if _uso["chamadas"] >= _limite("GEDIV_OCR_CHAMADAS_PAGINA", CHAMADAS_PAGINA_PADRAO):
        raise OcrEsgotado("limite de chamadas de OCR por página atingido")
    if pagina <= 0:
        raise OcrEsgotado("limite de tempo de OCR por página atingido")
    if arquivo <= 0:
        raise OcrEsgotado("limite de tempo de OCR por arquivo atingido")
    return min(tempo_maximo(), pagina, arquivo)


def _chamar(funcao, imagem, **k):
    import time
    folga = _folga()
    inicio = time.monotonic()
    try:
        return _executar(funcao, imagem, folga, **k)
    finally:
        gasto = time.monotonic() - inicio
        _uso["pagina"] += gasto
        _uso["arquivo"] += gasto
        _uso["chamadas"] += 1


def _executar(funcao, imagem, folga, **k):
    try:
        return funcao(imagem, timeout=folga, **k)
    except RuntimeError as e:
        # pytesseract sinaliza o estouro com RuntimeError("Tesseract process timeout")
        if "timeout" in str(e).lower():
            raise OcrEsgotado(f"OCR excedeu {folga:g} s") from e
        raise


def dados(imagem, config: str = ""):
    import pytesseract
    return _chamar(pytesseract.image_to_data, imagem, lang="por", config=config, output_type=pytesseract.Output.DICT)


def texto(imagem, config: str = "") -> str:
    import pytesseract
    return _chamar(pytesseract.image_to_string, imagem, lang="por", config=config)
