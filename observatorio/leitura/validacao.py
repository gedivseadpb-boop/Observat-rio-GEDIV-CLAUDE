"""Relatório de validação da leitura, para conferência com documentos oficiais.

O relatório NÃO contém texto das publicações nem dados pessoais: apenas contagens,
impressões digitais e indicadores, de modo que pode ser compartilhado para análise.

Verificações por arquivo:
- integridade: SHA-256 e tamanho recalculados do acervo;
- origem: fontes, endereços e datas que ofereceram o arquivo;
- identificação: número e data da edição lidos do cabeçalho;
- páginas: quantidade, método (texto nativo ou OCR), colunas e qualidade;
- referência: comparação com valores esperados informados em um arquivo de referências;
- leitura independente: proporção das palavras obtidas por outra biblioteca (pypdf) que
  também aparecem na nossa leitura. Mede perda de texto, não a ordem das colunas —
  a ordem só pode ser confirmada por conferência humana de páginas escolhidas.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .. import NOME
from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from . import leitor

_PALAVRA = re.compile(r"[0-9A-Za-zÀ-ÿ]{3,}")


def _vocabulario(texto: str) -> set[str]:
    return {p.lower() for p in _PALAVRA.findall(texto)}


def cobertura_independente(caminho: Path, paginas) -> dict | None:
    """Compara, página a página, com a extração feita pela biblioteca pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        outro = PdfReader(str(caminho))
        fracoes, abaixo = [], []
        for pagina, externa in zip(paginas, outro.pages):
            if pagina["metodo"] != "TEXTO":
                continue
            esperadas = _vocabulario(externa.extract_text() or "")
            if len(esperadas) < 20:
                continue
            fracao = len(esperadas & _vocabulario(pagina["texto"])) / len(esperadas)
            fracoes.append(fracao)
            if fracao < 0.95:
                abaixo.append(pagina["numero"])
        if not fracoes:
            return {"paginas_comparadas": 0}
        return {"paginas_comparadas": len(fracoes), "cobertura_media": round(sum(fracoes) / len(fracoes), 4),
                "cobertura_minima": round(min(fracoes), 4), "paginas_abaixo_de_95": abaixo}
    except Exception as e:
        return {"erro": f"{type(e).__name__}: {e}"[:200]}


def _comparar_com_referencia(item: dict, referencias: list[dict]) -> dict | None:
    datas = {o["data"] for o in item["origens"]} | {item["edicao"]["data"]}
    for ref in referencias:
        if ref.get("sha256") == item["sha256"] or ref.get("data") in datas:
            campos = {"sha256": item["sha256"], "bytes": item["bytes"], "paginas": item["paginas"]["total"],
                      "numero_edicao": item["edicao"]["numero"]}
            conferidos = {k: (campos[k] == ref[k]) for k in campos if ref.get(k) is not None}
            return {"referencia": ref.get("data"), "fonte_da_referencia": ref.get("fonte_da_referencia"),
                    "conferidos": conferidos, "tudo_confere": all(conferidos.values()) if conferidos else None}
    return None


def relatorio(banco: Banco, acervo: Acervo, referencias: list[dict] | None = None) -> dict:
    itens = []
    for leitura in banco.leituras():
        sha = leitura["sha256"]
        paginas = banco.paginas(sha)
        arquivo = banco.arquivo(sha)
        item = {
            "sha256": sha,
            "bytes": arquivo["tamanho"],
            "integridade_do_acervo": acervo.conferir(sha),
            "origens": [{"fonte": o["fonte"], "endereco": o["url"], "data": o["data_publicacao"]} for o in banco.origens(sha)],
            "situacao": leitura["situacao"],
            "versao_leitor": leitura["versao_leitor"],
            "edicao": {"numero": leitura["numero_edicao"], "data": leitura["data_edicao"]},
            "inconsistencias": json.loads(leitura["inconsistencias"] or "[]"),
            "erro": leitura["erro"],
            "paginas": {
                "total": leitura["paginas"],
                "por_metodo": dict(Counter(p["metodo"] for p in paginas)),
                "por_colunas": {str(k): v for k, v in sorted(Counter(p["colunas"] for p in paginas).items())},
                "por_qualidade": dict(Counter(p["qualidade"] for p in paginas)),
                "com_pendencia": [{"pagina": p["numero"], "qualidade": p["qualidade"], "confianca_ocr": p["confianca"]}
                                  for p in paginas if p["qualidade"] not in ("OK", "VAZIA")],
                "palavras": sum(p["palavras"] for p in paginas),
            },
            "leitura_independente": cobertura_independente(acervo.caminho(sha), paginas) if leitura["situacao"] != "ERRO" else None,
        }
        item["referencia"] = _comparar_com_referencia(item, referencias or [])
        itens.append(item)
    disponivel, detalhe = leitor.ocr_disponivel()
    return {"sistema": NOME, "versao_leitor": leitor.VERSAO, "ocr": {"disponivel": disponivel, "detalhe": detalhe},
            "arquivos_lidos": len(itens), "na_fila": len(banco.arquivos_sem_leitura(leitor.VERSAO)),
            "aviso": "Relatório sem texto das publicações. A ordem de leitura das colunas exige conferência humana.",
            "arquivos": itens}


def carregar_referencias(caminho: str | Path | None) -> list[dict]:
    if not caminho or not Path(caminho).is_file():
        return []
    return json.loads(Path(caminho).read_text(encoding="utf-8"))["documentos"]
