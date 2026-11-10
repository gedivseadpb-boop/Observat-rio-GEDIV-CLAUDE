"""Leitura dos arquivos do acervo e gravação do texto por página no banco.

Para cada página:
1. tenta o texto nativo do PDF, reconstruído por colunas;
2. se não houver texto, aplica OCR em português (Tesseract) e reconstrói por colunas
   a partir da posição das palavras reconhecidas;
3. atribui uma qualidade, para que nada duvidoso siga adiante como se fosse confiável.

Qualidade da página:
    OK                 texto nativo íntegro, ou OCR com boa confiança;
    BAIXA_CONFIANCA    OCR com confiança média abaixo de 75;
    ILEGIVEL           OCR com confiança abaixo de 50, ou sem palavras reconhecidas em página com conteúdo gráfico;
    INCONSISTENTE      texto nativo com caracteres corrompidos em proporção relevante;
    OCR_INDISPONIVEL   a página exige OCR e o Tesseract (com idioma português) não está instalado;
    VAZIA              página sem texto e sem conteúdo gráfico.

Cada arquivo é gravado em uma única transação: ou fica lido por inteiro, ou continua na
fila. Arquivos já lidos pela mesma versão do leitor são pulados; mudar a versão faz todos
voltarem à fila, sem apagar nada do acervo. Não conhece regras de nenhuma gerência.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from .pagina import Palavra, identificar_edicao, ler_pagina

VERSAO = "0.2"
MIN_CARACTERES = 20       # abaixo disso a página é tratada como sem texto nativo
RESOLUCAO_OCR = 300       # pontos por polegada
CONFIANCA_BOA, CONFIANCA_MINIMA = 75.0, 50.0
_CORROMPIDO = re.compile(r"\(cid:\d+\)|�")


@functools.lru_cache(maxsize=1)
def ocr_disponivel() -> tuple[bool, str]:
    try:
        import pytesseract
        if "por" not in pytesseract.get_languages(config=""):
            return False, "idioma português (por) não instalado no Tesseract"
        return True, f"Tesseract {pytesseract.get_tesseract_version()}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:200]


def _ocr(pagina) -> tuple[list[Palavra], float | None]:
    import pytesseract
    imagem = pagina.to_image(resolution=RESOLUCAO_OCR).original
    dados = pytesseract.image_to_data(imagem, lang="por", output_type=pytesseract.Output.DICT)
    escala = 72.0 / RESOLUCAO_OCR
    palavras, confiancas = [], []
    for texto, conf, x, y, w, h in zip(dados["text"], dados["conf"], dados["left"], dados["top"], dados["width"],
                                       dados["height"]):
        if texto.strip() and float(conf) >= 0:
            # No OCR a caixa acompanha cada desenho de letra (um hífen é mais baixo que uma palavra);
            # usa-se o centro vertical para que sinais pequenos fiquem na mesma linha do texto.
            palavras.append(Palavra(x * escala, (x + w) * escala, (y + h / 2) * escala, texto.strip()))
            confiancas.append(float(conf))
    return palavras, (round(sum(confiancas) / len(confiancas), 1) if confiancas else None)


def _ler_uma_pagina(numero: int, pagina) -> dict:
    largura = float(pagina.width)
    palavras = [Palavra(float(w["x0"]), float(w["x1"]), float(w["top"]), w["text"]) for w in pagina.extract_words()]
    texto, colunas = ler_pagina(palavras, largura)
    base = {"numero": numero, "confianca": None}
    if len(re.sub(r"\s", "", texto)) >= MIN_CARACTERES:
        corrompidos = len(_CORROMPIDO.findall(texto))
        qualidade = "INCONSISTENTE" if corrompidos > max(3, 0.02 * len(palavras)) else "OK"
        return {**base, "metodo": "TEXTO", "colunas": colunas, "texto": texto, "palavras": len(palavras), "qualidade": qualidade}
    tem_conteudo = bool(pagina.images or pagina.rects or pagina.curves or pagina.lines)
    if not tem_conteudo:
        return {**base, "metodo": "NENHUM", "colunas": 0, "texto": "", "palavras": 0, "qualidade": "VAZIA"}
    if not ocr_disponivel()[0]:
        return {**base, "metodo": "NENHUM", "colunas": 0, "texto": "", "palavras": 0, "qualidade": "OCR_INDISPONIVEL"}
    palavras, confianca = _ocr(pagina)
    texto, colunas = ler_pagina(palavras, largura)
    if not palavras or confianca < CONFIANCA_MINIMA:
        qualidade = "ILEGIVEL"
    elif confianca < CONFIANCA_BOA:
        qualidade = "BAIXA_CONFIANCA"
    else:
        qualidade = "OK"
    return {"numero": numero, "metodo": "OCR", "colunas": colunas if palavras else 0, "texto": texto,
            "palavras": len(palavras), "qualidade": qualidade, "confianca": confianca}


def ler_arquivo(caminho: str | Path) -> dict:
    import pdfplumber  # importado aqui para que a coleta funcione sem esta biblioteca

    with pdfplumber.open(str(caminho)) as documento:
        paginas = [_ler_uma_pagina(numero, pagina) for numero, pagina in enumerate(documento.pages, start=1)]
    if not paginas:
        raise ValueError("o documento não tem páginas")
    numero_edicao, data_edicao = identificar_edicao(paginas[0]["texto"])
    return {"paginas": paginas, "numero_edicao": numero_edicao, "data_edicao": data_edicao}


def conferir_com_a_origem(resultado: dict, origens) -> list[str]:
    """Compara o que o documento diz de si mesmo com o que a origem informou."""
    achados = []
    if resultado["numero_edicao"] is None:
        achados.append("NUMERO_DA_EDICAO_NAO_IDENTIFICADO")
    if resultado["data_edicao"] is None:
        achados.append("DATA_DA_EDICAO_NAO_IDENTIFICADA")
    else:
        datas = sorted({o["data_publicacao"] for o in origens if o["data_publicacao"]})
        if datas and resultado["data_edicao"] not in datas:
            achados.append(f"DATA_DIVERGENTE: cabeçalho {resultado['data_edicao']}, origem {', '.join(datas)}")
    return achados


def processar(banco: Banco, acervo: Acervo, limite: int | None = None, refazer_pendentes: bool = False) -> dict:
    """Lê os arquivos do acervo ainda não lidos por esta versão do leitor (de qualquer origem).
    Com `refazer_pendentes`, tenta de novo os que terminaram em erro ou com páginas pendentes."""
    contagem = {"LIDA": 0, "LIDA_COM_PENDENCIAS": 0, "ERRO": 0, "na_fila": 0}
    fila = banco.arquivos_sem_leitura(VERSAO, refazer_pendentes)
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
        inconsistencias = conferir_com_a_origem(resultado, banco.origens(sha))
        pendencia = inconsistencias or any(p["qualidade"] not in ("OK", "VAZIA") for p in resultado["paginas"])
        situacao = "LIDA_COM_PENDENCIAS" if pendencia else "LIDA"
        banco.registrar_leitura(sha, situacao, VERSAO, resultado["paginas"], resultado["numero_edicao"],
                                resultado["data_edicao"], None, inconsistencias)
        contagem[situacao] += 1
    return contagem
