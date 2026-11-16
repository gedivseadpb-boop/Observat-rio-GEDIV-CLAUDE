"""Worker CPU opcional. Entrada/saída privadas; nunca baixa modelos.

Descobre grades na página inteira, filtra geometria de seis colunas e cabeçalhos
de classes, e devolve somente linhas ancoradas nos candidatos documentais.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

from .paddle_complementar import modelos_conferidos


def _grupos(posicoes):
    grupos = []
    for p in posicoes:
        if not grupos or p > grupos[-1][-1] + 1:
            grupos.append([int(p)])
        else:
            grupos[-1].append(int(p))
    return [sum(g) / len(g) for g in grupos]


def grades(imagem):
    import cv2
    import numpy as np
    altura, largura = imagem.shape[:2]
    tinta = cv2.threshold(cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY), 100, 255, cv2.THRESH_BINARY_INV)[1]
    h = cv2.morphologyEx(tinta, cv2.MORPH_OPEN, np.ones((1, max(20, round(largura * .08))), np.uint8))
    v = cv2.morphologyEx(tinta, cv2.MORPH_OPEN, np.ones((max(15, round(altura * .012)), 1), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(cv2.bitwise_or(h, v), 8)
    encontrados = []
    for x, y, w, a, _ in stats[1:]:
        if not largura * .2 <= w <= largura * .8 or a < 40:
            continue
        xs = _grupos(np.flatnonzero((v[y:y+a, x:x+w] > 0).mean(0) > .8))
        ys = _grupos(np.flatnonzero((h[y:y+a, x:x+w] > 0).mean(1) > .8))
        if len(xs) != 7 or not 3 <= len(ys) <= 102:
            continue
        # Classes têm duas células finais estreitas; evita tabelas administrativas
        # de seis colunas com lotação/período. Sem coordenadas ou identidade fixas.
        if not all(.03 <= (xs[i+1]-xs[i])/w <= .15 for i in (4, 5)):
            continue
        encontrados.append(([int(x), int(y), int(w), int(a)], xs, ys))
    return encontrados


def montar(textos, poligonos, scores, xs, ys):
    linhas = [[[] for _ in range(6)] for _ in range(len(ys)-1)]
    inseguras = set()
    for texto, pol, confianca in zip(textos, poligonos, scores):
        x0, y0 = min(p[0] for p in pol), min(p[1] for p in pol)
        x1, y1 = max(p[0] for p in pol), max(p[1] for p in pol)
        area = max(1, (x1-x0)*(y1-y0))
        melhor = (0, 0, 0)
        for r in range(len(linhas)):
            for c in range(6):
                cobertura = max(0, min(x1, xs[c+1])-max(x0, xs[c])) * max(0, min(y1, ys[r+1])-max(y0, ys[r])) / area
                if cobertura > melhor[0]:
                    melhor = (cobertura, r, c)
        if melhor[0] < .9:
            for r in range(len(linhas)):
                if y0 < ys[r+1] and y1 > ys[r]:
                    inseguras.add(r)
            continue
        linhas[melhor[1]][melhor[2]].append((float(y0), float(x0), str(texto), float(confianca)))
    return [[(" ".join(t[2] for t in sorted(c)), min((t[3] for t in c), default=0)) for c in linha]
            for linha in linhas], inseguras


def rodar(pedido):
    from importlib.metadata import version
    for pacote, esperado in (("paddleocr", "3.7.0"), ("paddlex", "3.7.2"), ("paddlepaddle", "3.2.0")):
        if version(pacote) != esperado:
            return {"erro": "PADDLE_VERSAO_INCOMPATIVEL"}
    modelos_conferidos(pedido["modelos"])
    import fitz
    import numpy as np
    import cv2
    from paddleocr import PaddleOCR
    from .catalogo import normalizar
    from .classificador import PAT_PROCESSO
    ocr = None
    candidatos, regioes = [], 0
    with fitz.open(pedido["pdf"]) as documento:
        for numero, alvos in pedido["paginas"].items():
            pagina = documento[int(numero)-1]
            # Limite anterior à alocação do bitmap de uma página maliciosa/enorme.
            if pagina.rect.width * pagina.rect.height * (400/72)**2 > 25_000_000:
                return {"erro": "PADDLE_LIMITE_PIXELS"}
            pix = pagina.get_pixmap(dpi=400, alpha=False)
            imagem = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
            processos = {re.sub(r"\s+", "", a["processo"] or "") for a in alvos}
            for (x, y, w, altura), xs, ys in grades(imagem):
                bbox = [x*72/400, y*72/400, (x+w)*72/400, (y+altura)*72/400]
                nativos = {re.sub(r"\s+", "", m.group()) for m in PAT_PROCESSO.finditer(
                    normalizar(pagina.get_textbox(fitz.Rect(bbox))))}
                if nativos and not nativos.intersection(processos):
                    continue
                if regioes >= pedido["max_regioes"]:
                    return {"erro": "PADDLE_LIMITE_REGIOES"}
                regioes += 1
                margem = round(400 * 2 / 72)
                x0, y0 = max(0, x-margem), max(0, y-margem)
                recorte = imagem[y0:min(pix.height, y+altura+margem), x0:min(pix.width, x+w+margem)]
                if ocr is None:
                    raiz = Path(pedido["modelos"])
                    ocr = PaddleOCR(text_detection_model_name="PP-OCRv6_medium_det",
                                    text_recognition_model_name="PP-OCRv6_medium_rec",
                                    text_detection_model_dir=str(raiz/"PP-OCRv6_medium_det"),
                                    text_recognition_model_dir=str(raiz/"PP-OCRv6_medium_rec"),
                                    use_doc_orientation_classify=False, use_doc_unwarping=False,
                                    use_textline_orientation=False, device="cpu", cpu_threads=2,
                                    enable_mkldnn=True, enable_hpi=False,
                                    text_det_limit_side_len=2000, text_det_limit_type="max",
                                    text_recognition_batch_size=16)
                resultado = list(ocr.predict(cv2.cvtColor(recorte, cv2.COLOR_RGB2BGR)))[0]
                linhas, inseguras = montar(resultado["rec_texts"], resultado["rec_polys"], resultado["rec_scores"],
                                           [a+x-x0 for a in xs], [a+y-y0 for a in ys])
                cab = [normalizar(c[0]) for c in linhas[0]]
                if not ("PROCESSO" in cab[0] and "MATRICULA" in cab[1] and "NOME" in cab[2]
                        and "CARGO" in cab[3] and "CLASSE" in cab[4] and "CLASSE" in cab[5]):
                    continue
                for r, linha in enumerate(linhas[1:], 1):
                    valores = [c[0].strip() for c in linha]
                    processo = re.sub(r"\s+", "", valores[0]).upper()
                    if processo not in processos:
                        continue
                    candidatos.append({"pagina": int(numero), "processo": processo, "matricula": valores[1],
                                       "nome": valores[2], "cargo": valores[3],
                                       "classe_anterior": valores[4], "classe_posterior": valores[5],
                                       "confiancas": [linha[c][1] for c in (0, 1, 4, 5)],
                                       "geometria_segura": r not in inseguras,
                                       "bbox_pdf": [bbox[0], (y+ys[r])*72/400, bbox[2], (y+ys[r+1])*72/400]})
    return {"candidatos": candidatos, "regioes": regioes}


if __name__ == "__main__":
    try:
        resposta = rodar(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except Exception:
        # Bibliotecas podem colocar nomes/transcrições na mensagem da exceção.
        resposta = {"erro": "PADDLE_FALHA_EXECUCAO"}
    Path(sys.argv[2]).write_text(json.dumps(resposta, ensure_ascii=False), encoding="utf-8")
