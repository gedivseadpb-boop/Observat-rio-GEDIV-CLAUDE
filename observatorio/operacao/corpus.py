"""Corpus de PDFs difíceis: precisão POR CAMPO contra um esperado conferido visualmente.

    python -m observatorio.operacao corpus --pdfs PASTA_PDFS --esperado-privado ARQUIVO.json [--saida relatorio.json]

- O manifesto público (`docs/validacao/corpus_pdfs_dificeis.json`) traz identidade dos arquivos, páginas e o
  esperado sem dados pessoais. Os valores por campo (processo, matrícula, nome, cargo) ficam num arquivo PRIVADO,
  fora do repositório, no formato {"desenvolvimento"|"validacao_cega": {"AAAA-MM-DD|NNN/AAAA" ou "DD-MM|NNN/AAAA":
  [linhas]}}.
- Cada edição roda em processo próprio (validar-real) e base temporária. O relatório traz apenas contagens e
  percentuais por campo e por conjunto — nunca valores.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

MANIFESTO = Path(__file__).resolve().parents[2] / "docs" / "validacao" / "corpus_pdfs_dificeis.json"
CAMPOS = ("processo", "matricula", "servidor", "cargo", "evolucao_anterior", "evolucao_posterior")


def _norm(valor) -> str:
    valor = "".join(c for c in unicodedata.normalize("NFKD", str(valor or "")) if not unicodedata.combining(c)).upper()
    return re.sub(r"\s+", " ", valor).strip()


def _linhas_extraidas(banco: Path, resenha: str) -> list[dict]:
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    try:
        saida = []
        for d in con.execute("SELECT d.* FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE a.numero = ? ORDER BY d.rowid",
                             (resenha,)):
            det = json.loads(d["detalhe"] or "{}")
            saida.append({"processo": d["processo"], "matricula": d["matricula"], "servidor": d["servidor"], "cargo": d["cargo"],
                          "evolucao_anterior": det.get("classe_anterior") or det.get("nivel_anterior"),
                          "evolucao_posterior": det.get("classe_posterior") or det.get("nivel_atual")})
        return saida
    finally:
        con.close()


def comparar(esperadas: list[dict], obtidas: list[dict]) -> dict:
    """Acertos por campo. Linhas pareadas pela matrícula (identificador da linha); sem ela, pela posição."""
    por_matricula = {_norm(o["matricula"]): o for o in obtidas if o.get("matricula")}
    contagem = {c: [0, 0] for c in CAMPOS}
    linhas_inteiras = encontradas = 0
    for i, e in enumerate(esperadas):
        o = por_matricula.get(_norm(e["matricula"])) or (obtidas[i] if i < len(obtidas) else None)
        encontradas += o is not None
        inteira = True
        for campo in CAMPOS:
            if e.get(campo) is None:
                continue
            contagem[campo][1] += 1
            certo = o is not None and _norm(o.get(campo)) == _norm(e[campo])
            contagem[campo][0] += certo
            inteira &= certo
        linhas_inteiras += inteira
    return {"linhas_esperadas": len(esperadas), "linhas_encontradas": encontradas, "linhas_inteiramente_corretas": linhas_inteiras,
            "por_campo": {c: {"acertos": a, "total": t} for c, (a, t) in contagem.items()}}


def _somar(partes: list[dict]) -> dict:
    total = {"linhas_esperadas": 0, "linhas_encontradas": 0, "linhas_inteiramente_corretas": 0,
             "por_campo": {c: {"acertos": 0, "total": 0} for c in CAMPOS}}
    for p in partes:
        for k in ("linhas_esperadas", "linhas_encontradas", "linhas_inteiramente_corretas"):
            total[k] += p[k]
        for c in CAMPOS:
            for k in ("acertos", "total"):
                total["por_campo"][c][k] += p["por_campo"][c][k]
    acertos = sum(v["acertos"] for v in total["por_campo"].values())
    campos = sum(v["total"] for v in total["por_campo"].values())
    total["precisao_todos_os_campos"] = round(100 * acertos / campos, 1) if campos else None
    return total


def executar(pasta_pdfs: str | Path, esperado_privado: str | Path, manifesto: str | Path = MANIFESTO) -> dict:
    casos = json.loads(Path(manifesto).read_text(encoding="utf-8"))["casos"]
    privado = json.loads(Path(esperado_privado).read_text(encoding="utf-8"))
    por_sha = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in Path(pasta_pdfs).glob("*.pdf")}
    raiz = Path(__file__).resolve().parents[2]
    resultados: dict[str, list] = {}
    with tempfile.TemporaryDirectory(prefix="corpus-") as pasta:
        bancos: dict[str, Path] = {}
        for caso in casos:
            chave = f"{caso['data'][8:10]}-{caso['data'][5:7]}|{caso['resenha']}"
            esperadas = privado.get(caso["conjunto"], {}).get(chave)
            if esperadas is None:
                continue
            arquivo = por_sha.get(caso["sha256"])
            if arquivo is None:
                resultados.setdefault(caso["conjunto"], []).append({"caso": caso["resenha"], "situacao": "PDF_AUSENTE"})
                continue
            if caso["sha256"] not in bancos:
                dados = Path(pasta) / caso["sha256"][:12]
                subprocess.run([sys.executable, "-m", "observatorio.operacao", "validar-real", str(arquivo), "--data", caso["data"],
                                "--url", caso["url"], "--dados", str(dados)], capture_output=True, cwd=raiz)
                bancos[caso["sha256"]] = dados / "observatorio.sqlite3"
            parcial = comparar(esperadas, _linhas_extraidas(bancos[caso["sha256"]], caso["resenha"]))
            resultados.setdefault(caso["conjunto"], []).append({"caso": f"{caso['data']} {caso['resenha']}", **parcial})
    return {conjunto: {"casos": itens, "total": _somar([i for i in itens if "por_campo" in i])}
            for conjunto, itens in resultados.items()}
