"""Painel Diário Oficial | GEDIV — leitura dos PDFs do acervo.

    python -m observatorio.leitura processar [--limite N]    # lê os arquivos ainda não lidos (baixados ou importados)
    python -m observatorio.leitura situacao                  # resumo do que já foi lido
    python -m observatorio.leitura validar --saida validacao.json   # relatório de validação, sem texto das publicações
    python -m observatorio.leitura pagina SHA256 NUMERO      # mostra o texto de uma página, para conferência humana

Requer: python -m pip install -r requirements.txt. O OCR requer também o programa Tesseract
com o idioma português; sem ele, páginas digitalizadas ficam marcadas como OCR_INDISPONIVEL.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from . import leitor, validacao

REFERENCIAS = Path(__file__).resolve().parents[2] / "docs" / "validacao" / "referencias.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.leitura", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["processar", "situacao", "validar", "pagina"])
    ap.add_argument("argumentos", nargs="*")
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--limite", type=int)
    ap.add_argument("--refazer", action="store_true", help="processar: tenta de novo leituras com erro ou páginas pendentes")
    ap.add_argument("--referencias", default=str(REFERENCIAS))
    ap.add_argument("--saida")
    a = ap.parse_args(argv)
    pasta = Path(a.dados)
    banco, acervo = Banco(pasta / "observatorio.sqlite3"), Acervo(pasta / "acervo")
    try:
        if a.comando == "processar":
            contagem = leitor.processar(banco, acervo, a.limite, a.refazer)
            print(json.dumps(contagem, ensure_ascii=False, indent=2))
            return 3 if contagem["ERRO"] or contagem["na_fila"] or contagem["LIDA_COM_PENDENCIAS"] else 0
        if a.comando == "validar":
            texto = json.dumps(validacao.relatorio(banco, acervo, validacao.carregar_referencias(a.referencias)),
                               ensure_ascii=False, indent=2)
            print(texto)
            if a.saida:
                Path(a.saida).write_text(texto, encoding="utf-8")
            return 0
        if a.comando == "pagina":
            if len(a.argumentos) != 2:
                ap.error("pagina exige SHA256 (ou o início dele) e NUMERO")
            achados = [l["sha256"] for l in banco.leituras() if l["sha256"].startswith(a.argumentos[0])]
            if len(achados) != 1:
                ap.error("SHA256 não encontrado ou ambíguo")
            pagina = [p for p in banco.paginas(achados[0]) if p["numero"] == int(a.argumentos[1])]
            if not pagina:
                ap.error("página não encontrada")
            p = pagina[0]
            print(f"[{p['metodo']} | {p['colunas']} coluna(s) | qualidade {p['qualidade']}]\n{p['texto']}")
            return 0
        linhas = [{k: l[k] for k in ("sha256", "situacao", "paginas", "paginas_sem_texto", "paginas_com_pendencia",
                                     "numero_edicao", "data_edicao", "inconsistencias", "erro")} for l in banco.leituras()]
        print(json.dumps({"lidos": len(linhas), "na_fila": len(banco.arquivos_sem_leitura(leitor.VERSAO)),
                          "arquivos": linhas}, ensure_ascii=False, indent=2))
        return 0
    finally:
        banco.fechar()


if __name__ == "__main__":
    sys.exit(main())
