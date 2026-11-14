"""Leitura dos arquivos do acervo e gravação do texto por página no banco.

Para cada página:
1. tenta o texto nativo do PDF, reconstruído por colunas;
   1a. se um trecho usa fonte sem mapeamento de caracteres (o texto sai como "(cid:12)(cid:7)…"), só esse
       trecho é lido por OCR e recolocado no lugar — método TEXTO+OCR (visto no DOE de 02/10/2026, p. 5);
2. se não houver texto, aplica OCR em português (Tesseract) e reconstrói por colunas
   a partir da posição das palavras reconhecidas;
3. atribui uma qualidade, para que nada duvidoso siga adiante como se fosse confiável.

Qualidade da página:
    OK                 texto nativo íntegro, ou OCR com boa confiança;
    BAIXA_CONFIANCA    OCR com confiança média abaixo de 75;
    ILEGIVEL           OCR com confiança abaixo de 50, ou sem palavras reconhecidas em página com conteúdo gráfico;
    INCONSISTENTE      texto nativo com caracteres corrompidos em proporção relevante, sem OCR para recuperá-los;
    OCR_INDISPONIVEL   a página exige OCR e o Tesseract (com idioma português) não está instalado;
    TEXTO_PARCIAL      página MISTA: há texto nativo, mas também uma imagem grande cujo conteúdo não pôde ser lido
                       (sem OCR disponível); o texto nativo é guardado e a página fica pendente;
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
from . import ocr, tabela_ocr
from .pagina import Palavra, identificar_edicao, ler_pagina

VERSAO = "0.6"           # 0.4: cache liberado por página; 0.5: OCR de tabela pela grade vetorial;
                         # 0.6: tolerância proporcional ao corpo da letra; leitura de caracteres sobrepostos
MIN_CARACTERES = 20       # abaixo disso a página é tratada como sem texto nativo
RESOLUCAO_OCR = 300       # pontos por polegada
RESOLUCAO_OCR_TRECHO = 400  # trechos com fonte ilegível costumam ser tabelas em corpo 4: mais resolução
MIN_SINAIS_ILEGIVEIS = 10   # sinais "(cid:N)" num bloco para justificar o OCR do trecho (uma linha inteira costuma vir como uma só "palavra")
CONFIANCA_BOA, CONFIANCA_MINIMA = 75.0, 50.0
FRACAO_IMAGEM_MISTA = 0.25  # imagens cobrindo esta fração da página, junto com texto nativo, indicam página mista
_CORROMPIDO = re.compile(r"\(cid:\d+\)|�")
# Distância horizontal máxima entre letras de uma mesma palavra, PROPORCIONAL ao corpo da letra. Uma tolerância
# fixa em pontos não serve às tabelas do DOE, que usam corpos de 4 a 8 pt: com 3 pt (padrão do pdfplumber) colava
# "LICENÇAPARATRATAR" (04/11/2026); com 1,5 pt ainda colava nomes em tabelas de corpo 4,3 pt (vão de 0,87 pt entre
# palavras, 05/11/2026). Medido em 513 páginas de 12 edições oficiais (12/11/2026): com 0,15 do corpo, 17 páginas
# ficam mais próximas da leitura independente (pypdfium2) que com 1,5 pt, e nenhuma piora.
TOLERANCIA_X_PROPORCIONAL = 0.15
# Caracteres de fontes diferentes desenhados no MESMO lugar (correção impressa por cima do texto original, DOE
# 05/11/2026, resenha 564: camada de texto "A", impresso visível "D" em fonte sem mapeamento). A palavra é relida por
# OCR do próprio recorte, que devolve o que está visível na publicação.
SOBREPOSICAO_MAX_PT = 0.6
RESOLUCAO_OCR_PALAVRA = 400


@functools.lru_cache(maxsize=1)
def ocr_disponivel() -> tuple[bool, str]:
    try:
        import pytesseract
        if "por" not in pytesseract.get_languages(config=""):
            return False, "idioma português (por) não instalado no Tesseract"
        return True, f"Tesseract {pytesseract.get_tesseract_version()}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:200]


def _ocr(pagina, resolucao: int = RESOLUCAO_OCR, origem: tuple[float, float] = (0.0, 0.0)) -> tuple[list[Palavra], float | None]:
    palavras, confiancas = _ocr_bruto(pagina, resolucao, origem)
    return palavras, (round(sum(confiancas) / len(confiancas), 1) if confiancas else None)


def _ocr_bruto(pagina, resolucao: int, origem: tuple[float, float]) -> tuple[list[Palavra], list[float]]:
    imagem = pagina.to_image(resolution=resolucao).original
    dados = ocr.dados(imagem)
    escala = 72.0 / resolucao
    palavras, confiancas = [], []
    for texto, conf, x, y, w, h in zip(dados["text"], dados["conf"], dados["left"], dados["top"], dados["width"],
                                       dados["height"]):
        if texto.strip() and float(conf) >= 0:
            # No OCR a caixa acompanha cada desenho de letra (um hífen é mais baixo que uma palavra);
            # usa-se o centro vertical para que sinais pequenos fiquem na mesma linha do texto.
            palavras.append(Palavra(origem[0] + x * escala, origem[0] + (x + w) * escala, origem[1] + (y + h / 2) * escala, texto.strip()))
            confiancas.append(float(conf))
    return palavras, confiancas


def _blocos_ilegiveis(brutas: list[dict], largura: float, altura: float) -> list[tuple[float, float, float, float]]:
    """Retângulos (x0, topo, x1, base) que envolvem as palavras em fonte sem mapeamento de caracteres.
    Palavras vizinhas na vertical e na mesma faixa horizontal formam um bloco; as linhas "normais" que ficam
    dentro dele (linhas de tabela na mesma fonte, que saem como letras trocadas) são relidas junto."""
    ruins = sorted((w for w in brutas if _CORROMPIDO.search(w["text"])), key=lambda w: w["top"])
    blocos: list[list[float]] = []
    contagem: list[int] = []
    for w in ruins:
        for i, b in enumerate(blocos):
            if w["top"] - b[3] <= 30 and w["x0"] <= b[2] + 20 and w["x1"] >= b[0] - 20:
                b[0], b[1], b[2], b[3] = min(b[0], w["x0"]), min(b[1], w["top"]), max(b[2], w["x1"]), max(b[3], w["bottom"])
                contagem[i] += len(_CORROMPIDO.findall(w["text"]))
                break
        else:
            blocos.append([w["x0"], w["top"], w["x1"], w["bottom"]])
            contagem.append(len(_CORROMPIDO.findall(w["text"])))
    fundiu = True
    while fundiu:                      # blocos que se tocam viram um só, para nenhum trecho ser lido duas vezes
        fundiu = False
        for i in range(len(blocos)):
            for j in range(i + 1, len(blocos)):
                a, b = blocos[i], blocos[j]
                if a[0] <= b[2] + 8 and b[0] <= a[2] + 8 and a[1] <= b[3] + 8 and b[1] <= a[3] + 8:
                    blocos[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    contagem[i] += contagem[j]
                    del blocos[j], contagem[j]
                    fundiu = True
                    break
            if fundiu:
                break
    return [(max(0.0, b[0] - 4), max(0.0, b[1] - 4), min(largura, b[2] + 4), min(altura, b[3] + 4))
            for b, n in zip(blocos, contagem) if n >= MIN_SINAIS_ILEGIVEIS]


def _reler_trechos_ilegiveis(numero: int, pagina, brutas: list[dict]) -> dict | None:
    """Substitui por OCR somente os trechos em fonte ilegível. None quando não há o que reler."""
    largura, altura = float(pagina.width), float(pagina.height)
    blocos = _blocos_ilegiveis(brutas, largura, altura)
    if not blocos:
        return None
    dentro = lambda w, b: b[0] <= (w["x0"] + w["x1"]) / 2 <= b[2] and b[1] <= (w["top"] + w["bottom"]) / 2 <= b[3]
    lidas_por_bloco, confiancas, areas = [], [], []
    for b in blocos:
        centro = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        if any(a[0] <= centro[0] <= a[2] and a[1] <= centro[1] <= a[3] for a in areas):
            continue                                     # trecho já relido junto com a tabela a que pertence
        # Tabela com grade vetorial: OCR coluna a coluna, célula por célula (tabela_ocr). Sem grade: o bloco inteiro.
        tabela = tabela_ocr.ler_tabela(pagina, b, brutas, lambda t: bool(_CORROMPIDO.search(t)))
        if tabela:
            lidas, conf, area = tabela
        else:
            (lidas, conf), area = _ocr_bruto(pagina.crop(b), RESOLUCAO_OCR_TRECHO, (b[0], b[1])), b
        lidas_por_bloco += lidas
        confiancas += conf
        areas.append(area)
    palavras = [Palavra(float(w["x0"]), float(w["x1"]), float(w["top"]), w["text"]) for w in brutas
                if not any(dentro(w, a) for a in areas) and not _CORROMPIDO.search(w["text"])]
    palavras += lidas_por_bloco
    if not confiancas:
        return None
    confianca = round(sum(confiancas) / len(confiancas), 1)
    texto, colunas = ler_pagina(palavras, largura)
    return {"numero": numero, "metodo": "TEXTO+OCR", "colunas": colunas, "texto": texto, "palavras": len(palavras),
            "qualidade": "OK" if confianca >= CONFIANCA_BOA else "BAIXA_CONFIANCA", "confianca": confianca}


def _fracao_coberta_por_imagens(pagina) -> float:
    largura, altura = float(pagina.width), float(pagina.height)
    area = 0.0
    for imagem in pagina.images:
        x0, x1 = max(0.0, float(imagem["x0"])), min(largura, float(imagem["x1"]))
        topo, base = max(0.0, float(imagem["top"])), min(altura, float(imagem["bottom"]))
        area += max(0.0, x1 - x0) * max(0.0, base - topo)
    return min(1.0, area / (largura * altura)) if largura and altura else 0.0


def _classificar_ocr(numero, palavras, confianca, largura) -> dict:
    texto, colunas = ler_pagina(palavras, largura)
    if not palavras or confianca < CONFIANCA_MINIMA:
        qualidade = "ILEGIVEL"
    elif confianca < CONFIANCA_BOA:
        qualidade = "BAIXA_CONFIANCA"
    else:
        qualidade = "OK"
    return {"numero": numero, "metodo": "OCR", "colunas": colunas if palavras else 0, "texto": texto,
            "palavras": len(palavras), "qualidade": qualidade, "confianca": confianca}


def _ler_sobreposicoes(pagina, brutas: list[dict]) -> int:
    """Relê por OCR as palavras em que dois caracteres diferentes ocupam a mesma posição e um deles está em fonte
    sem mapeamento. Altera `brutas` no lugar; devolve quantas palavras foram relidas."""
    relidas = 0
    for w in brutas:
        if not _CORROMPIDO.search(w["text"]):
            continue
        caracteres = sorted((c for c in pagina.chars if w["x0"] - 0.5 <= c["x0"] <= w["x1"] and w["top"] - 2 <= c["top"] <= w["bottom"]),
                            key=lambda c: c["x0"])
        if not any(b["x0"] - a["x0"] < SOBREPOSICAO_MAX_PT and a["text"] != b["text"] and a["fontname"] != b["fontname"]
                   for a, b in zip(caracteres, caracteres[1:])):
            continue
        caixa = (max(0.0, w["x0"] - 1.5), max(0.0, w["top"] - 1.5), min(float(pagina.width), w["x1"] + 1.5),
                 min(float(pagina.height), w["bottom"] + 1.5))
        imagem = pagina.crop(caixa).to_image(resolution=RESOLUCAO_OCR_PALAVRA).original
        lido = ocr.texto(imagem, config=f"--psm {10 if len(_CORROMPIDO.sub('x', w['text'])) <= 2 else 7}").strip()
        if lido and not _CORROMPIDO.search(lido):
            w["text"] = lido
            relidas += 1
    return relidas


def _ler_uma_pagina(numero: int, pagina) -> dict:
    largura = float(pagina.width)
    brutas = pagina.extract_words(x_tolerance_ratio=TOLERANCIA_X_PROPORCIONAL)
    sobrepostas = _ler_sobreposicoes(pagina, brutas) if ocr_disponivel()[0] else 0
    palavras = [Palavra(float(w["x0"]), float(w["x1"]), float(w["top"]), w["text"]) for w in brutas]
    texto, colunas = ler_pagina(palavras, largura)
    base = {"numero": numero, "confianca": None}
    if len(re.sub(r"\s", "", texto)) >= MIN_CARACTERES:
        corrompidos = len(_CORROMPIDO.findall(texto))
        qualidade = "INCONSISTENTE" if corrompidos > max(3, 0.02 * len(palavras)) or corrompidos >= MIN_SINAIS_ILEGIVEIS else "OK"
        nativo = {**base, "metodo": "TEXTO+OCR" if sobrepostas else "TEXTO", "colunas": colunas, "texto": texto,
                  "palavras": len(palavras), "qualidade": qualidade}
        if corrompidos and ocr_disponivel()[0]:
            relida = _reler_trechos_ilegiveis(numero, pagina, brutas)
            if relida:
                return relida
        if _fracao_coberta_por_imagens(pagina) < FRACAO_IMAGEM_MISTA:
            return nativo
        # Página mista: cabeçalho em texto e corpo digitalizado, por exemplo. O texto nativo sozinho pode ser só uma parte.
        if not ocr_disponivel()[0]:
            return {**nativo, "qualidade": "TEXTO_PARCIAL" if qualidade == "OK" else qualidade}
        palavras_ocr, confianca = _ocr(pagina)
        if len(palavras_ocr) > 1.3 * len(palavras) + 15:      # a imagem tinha texto que o PDF não trazia: vale a página inteira por OCR
            return _classificar_ocr(numero, palavras_ocr, confianca, largura)
        return nativo
    tem_conteudo = bool(pagina.images or pagina.rects or pagina.curves or pagina.lines)
    if not tem_conteudo:
        return {**base, "metodo": "NENHUM", "colunas": 0, "texto": "", "palavras": 0, "qualidade": "VAZIA"}
    if not ocr_disponivel()[0]:
        return {**base, "metodo": "NENHUM", "colunas": 0, "texto": "", "palavras": 0, "qualidade": "OCR_INDISPONIVEL"}
    palavras, confianca = _ocr(pagina)
    return _classificar_ocr(numero, palavras, confianca, largura)


def _pagina_com_ocr_esgotado(numero: int, pagina) -> dict:
    """O OCR não respondeu a tempo: fica o texto nativo que houver, e a página vira pendência para nova tentativa
    (`processar(..., refazer_pendentes=True)`). O robô segue para a página seguinte em vez de travar."""
    brutas = pagina.extract_words(x_tolerance_ratio=TOLERANCIA_X_PROPORCIONAL)
    palavras = [Palavra(float(w["x0"]), float(w["x1"]), float(w["top"]), w["text"]) for w in brutas]
    texto, colunas = ler_pagina(palavras, float(pagina.width)) if palavras else ("", 0)
    return {"numero": numero, "metodo": "TEXTO" if palavras else "NENHUM", "colunas": colunas, "texto": texto,
            "palavras": len(palavras), "qualidade": "OCR_ESGOTADO", "confianca": None}


def ler_arquivo(caminho: str | Path) -> dict:
    import pdfplumber  # importado aqui para que a coleta funcione sem esta biblioteca

    paginas = []
    with pdfplumber.open(str(caminho)) as documento:
        for numero, pagina in enumerate(documento.pages, start=1):
            try:
                try:
                    paginas.append(_ler_uma_pagina(numero, pagina))
                except ocr.OcrEsgotado:
                    paginas.append(_pagina_com_ocr_esgotado(numero, pagina))
            finally:
                # Sem isto o pdfplumber guarda caracteres, objetos e o mapa de texto de TODAS as páginas lidas
                # até o fim do arquivo (pico de 0,8–1,2 GB por edição medido em 12/11/2026).
                pagina.close()
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
