"""Leitura dos arquivos do acervo e gravação do texto por página no banco.

Cada arquivo é gravado em uma única transação: ou fica lido por inteiro, ou continua
na fila. Arquivos já lidos pela mesma versão do leitor são pulados; mudar a versão
faz todos voltarem à fila, sem apagar nada do acervo.

Páginas sem texto extraível (digitalizadas) são registradas como SEM_TEXTO. O OCR
dessas páginas é uma etapa posterior e ainda não está implementado.
"""
from __future__ import annotations

from pathlib import Path

from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from .pagina import Palavra, identificar_edicao, ler_pagina

VERSAO = "0.1"
MIN_CARACTERES = 20  # abaixo disso a página é tratada como sem texto


def ler_arquivo(caminho: str | Path) -> dict:
    import pdfplumber  # importado aqui para que a coleta funcione sem esta biblioteca

    paginas = []
    with pdfplumber.open(str(caminho)) as documento:
        for numero, pagina in enumerate(documento.pages, start=1):
            palavras = [Palavra(float(w["x0"]), float(w["x1"]), float(w["top"]), w["text"])
                        for w in pagina.extract_words()]
            texto, colunas = ler_pagina(palavras, float(pagina.width))
            if len(texto.replace(" ", "").replace("\n", "")) < MIN_CARACTERES:
                paginas.append({"numero": numero, "metodo": "SEM_TEXTO", "colunas": 0, "texto": ""})
            else:
                paginas.append({"numero": numero, "metodo": "TEXTO", "colunas": colunas, "texto": texto})
    if not paginas:
        raise ValueError("o documento não tem páginas")
    numero_edicao, data_edicao = identificar_edicao(paginas[0]["texto"])
    return {"paginas": paginas, "numero_edicao": numero_edicao, "data_edicao": data_edicao}


def processar(banco: Banco, acervo: Acervo, limite: int | None = None) -> dict:
    """Lê os arquivos do acervo ainda não lidos por esta versão do leitor."""
    contagem = {"LIDA": 0, "LIDA_COM_PAGINAS_SEM_TEXTO": 0, "ERRO": 0, "na_fila": 0}
    fila = banco.arquivos_sem_leitura(VERSAO)
    for indice, arquivo in enumerate(fila):
        if limite is not None and indice >= limite:
            contagem["na_fila"] = len(fila) - indice
            break
        sha = arquivo["sha256"]
        try:
            if not acervo.conferir(sha):
                raise ValueError("arquivo ausente ou adulterado no acervo")
            resultado = ler_arquivo(acervo.caminho(sha))
        except Exception as e:  # um arquivo problemático não pode parar a fila
            banco.registrar_leitura(sha, "ERRO", VERSAO, [], None, None, f"{type(e).__name__}: {e}"[:300])
            contagem["ERRO"] += 1
            continue
        sem_texto = any(p["metodo"] == "SEM_TEXTO" for p in resultado["paginas"])
        situacao = "LIDA_COM_PAGINAS_SEM_TEXTO" if sem_texto else "LIDA"
        banco.registrar_leitura(sha, situacao, VERSAO, resultado["paginas"], resultado["numero_edicao"],
                                resultado["data_edicao"], None)
        contagem[situacao] += 1
    return contagem
