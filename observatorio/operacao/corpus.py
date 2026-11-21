"""Corpus de PDFs difíceis: precisão POR CAMPO contra um esperado conferido visualmente.

    python -m observatorio.operacao corpus --pdfs PASTA_PDFS --esperado-privado ARQUIVO.json [--saida relatorio.json]

- O manifesto público (`docs/validacao/corpus_pdfs_dificeis.json`) traz identidade dos arquivos, páginas e o
  esperado sem dados pessoais. Os valores por campo (processo, matrícula, nome, cargo) ficam num arquivo PRIVADO,
  fora do repositório, no formato {"desenvolvimento"|"validacao_cega": {"DD-MM|NNN/AAAA": [linhas]}}.
- Cada edição roda em processo próprio (validar-real) e base temporária. O relatório traz apenas contagens e
  percentuais por campo e por conjunto — nunca valores.

Contrato (Etapa 05.3.1 — antes, casos ausentes eram pulados em silêncio e um corpus vazio "passava"):

- APROVADO só quando TODOS os casos do manifesto foram avaliados e cada um CONFERE: toda linha esperada pareada
  um a um pela matrícula, nenhuma ausente, extra, duplicada ou ambígua, e todos os campos iguais. Caso cujo esperado
  é um EVENTO público (`esperado_publico.evento`) é avaliado pelo evento extraído na página, sem arquivo privado.
- REPROVADO quando algum caso avaliado diverge ou a execução de algum caso falhou.
- PARCIAL quando algo do contrato não pôde ser avaliado (PDF ausente, caso sem esperado, esperado vazio, esperado
  para caso que o manifesto não tem) — nunca é aprovação.
- INDISPONIVEL quando nada pôde ser avaliado (sem esperado privado, pasta sem os PDFs, esperado vazio).
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
from collections import Counter
from pathlib import Path

from . import saida

MANIFESTO = Path(__file__).resolve().parents[2] / "docs" / "validacao" / "corpus_pdfs_dificeis.json"
CAMPOS = ("processo", "matricula", "servidor", "cargo", "evolucao_anterior", "evolucao_posterior")

APROVADO, REPROVADO, PARCIAL, INDISPONIVEL = "APROVADO", "REPROVADO", "PARCIAL", "INDISPONIVEL"
CODIGO_DE_SAIDA = {APROVADO: saida.SUCESSO, REPROVADO: saida.FALHA, PARCIAL: saida.FALHA, INDISPONIVEL: saida.NAO_EXECUTADO}

# situação de cada caso
CONFERE, DIVERGENTE = "CONFERE", "DIVERGENTE"
PDF_AUSENTE, ESPERADO_AUSENTE, ESPERADO_VAZIO, CASO_NAO_CONTRATADO, FALHA_EXECUCAO = (
    "PDF_AUSENTE", "ESPERADO_AUSENTE", "ESPERADO_VAZIO", "CASO_NAO_CONTRATADO", "FALHA_EXECUCAO")
NAO_AVALIADOS = (PDF_AUSENTE, ESPERADO_AUSENTE, ESPERADO_VAZIO, CASO_NAO_CONTRATADO)


def _norm(valor) -> str:
    valor = "".join(c for c in unicodedata.normalize("NFKD", str(valor or "")) if not unicodedata.combining(c)).upper()
    return re.sub(r"\s+", " ", valor).strip()


class FalhaDeExecucao(RuntimeError):
    pass


def _linhas_extraidas(banco: Path, resenha: str) -> list[dict]:
    if not banco.is_file():
        raise FalhaDeExecucao("a leitura não produziu banco")
    # Somente leitura: sqlite3.connect criaria um banco VAZIO no lugar do ausente, e o caso "passaria" com 0 linhas.
    con = sqlite3.connect(f"{banco.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        saida_ = []
        for d in con.execute("SELECT d.* FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE a.numero = ? ORDER BY d.rowid",
                             (resenha,)):
            det = json.loads(d["detalhe"] or "{}")
            saida_.append({"processo": d["processo"], "matricula": d["matricula"], "servidor": d["servidor"], "cargo": d["cargo"],
                           "evolucao_anterior": det.get("classe_anterior") or det.get("nivel_anterior"),
                           "evolucao_posterior": det.get("classe_posterior") or det.get("nivel_atual")})
        return saida_
    except sqlite3.Error as e:
        raise FalhaDeExecucao(f"banco da leitura ilegível: {type(e).__name__}") from e
    finally:
        con.close()


def _eventos_extraidos(banco: Path, pagina: int) -> list[dict]:
    if not banco.is_file():
        raise FalhaDeExecucao("a leitura não produziu banco")
    con = sqlite3.connect(f"{banco.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [{"evento": e["tipo"], "subcategoria": e["subcategoria"],
                 "publicacoes_citadas": json.loads(e["publicacoes_citadas"] or "[]"),
                 "resenhas_citadas": json.loads(e["resenhas_citadas"] or "[]")}
                for e in con.execute("SELECT e.tipo, e.publicacoes_citadas, e.resenhas_citadas, a.subcategoria FROM evento e "
                                     "LEFT JOIN ato a ON a.id = e.ato_id WHERE e.pagina = ?", (pagina,))]
    except sqlite3.Error as e:
        raise FalhaDeExecucao(f"banco da leitura ilegível: {type(e).__name__}") from e
    finally:
        con.close()


def comparar_evento(esperado: dict, obtidos: list[dict]) -> dict:
    """Caso cujo esperado é um EVENTO (público, sem dados pessoais): exatamente um evento do tipo esperado na página,
    com os mesmos campos."""
    do_tipo = [o for o in obtidos if o["evento"] == esperado["evento"]]
    campos = [c for c in esperado if c != "evento"]
    divergentes = [c for c in campos if len(do_tipo) == 1 and do_tipo[0].get(c) != esperado[c]]
    confere = len(do_tipo) == 1 and not divergentes
    return {"situacao": CONFERE if confere else DIVERGENTE, "tipo_de_caso": "evento", "eventos_do_tipo_na_pagina": len(do_tipo),
            "campos_avaliados": len(campos), "campos_divergentes": len(divergentes) if len(do_tipo) == 1 else len(campos)}


def comparar(esperadas: list[dict], obtidas: list[dict]) -> dict:
    """Pareamento UM A UM pela matrícula (identificador da linha). Sem reserva por posição: uma linha esperada sem
    matrícula, ou com matrícula repetida no esperado, é AMBÍGUA; matrícula repetida no extraído é DUPLICADA."""
    chave = lambda linha: _norm(linha.get("matricula"))
    contagem_esperada = Counter(chave(e) for e in esperadas)
    por_chave: dict[str, list[dict]] = {}
    for o in obtidas:
        por_chave.setdefault(chave(o), []).append(o)
    acertos = {c: [0, 0] for c in CAMPOS}
    pareadas = encontradas = inteiras = ausentes = ambiguas = 0
    duplicadas = sum(len(v) - 1 for k, v in por_chave.items() if k and len(v) > 1)
    usadas: set[str] = set()
    for e in esperadas:
        k = chave(e)
        for campo in CAMPOS:
            if e.get(campo) is not None:
                acertos[campo][1] += 1
        if not k or contagem_esperada[k] > 1:
            ambiguas += 1
            continue
        candidatas = por_chave.get(k, [])
        if not candidatas:
            ausentes += 1
            continue
        usadas.add(k)
        encontradas += 1
        if len(candidatas) > 1:            # já contada em `duplicadas`; nenhuma das cópias vale como acerto
            continue
        o = candidatas[0]
        pareadas += 1
        inteira = True
        for campo in CAMPOS:
            if e.get(campo) is None:
                continue
            certo = _norm(o.get(campo)) == _norm(e[campo])
            acertos[campo][0] += certo
            inteira &= certo
        inteiras += inteira
    # extraídas cuja matrícula o esperado não tem, mais as extraídas sem matrícula (não pareáveis)
    extras = sum(len(v) for k, v in por_chave.items() if k and k not in contagem_esperada) + len(por_chave.get("", []))
    divergentes = sum(t - a for a, t in acertos.values())
    confere = bool(esperadas) and pareadas == len(esperadas) == inteiras and not (ausentes or extras or duplicadas or ambiguas)
    return {"situacao": CONFERE if confere else DIVERGENTE,
            "linhas_esperadas": len(esperadas), "linhas_obtidas": len(obtidas), "linhas_encontradas": encontradas,
            "linhas_pareadas": pareadas,
            "linhas_inteiramente_corretas": inteiras, "ausentes": ausentes, "extras": extras, "duplicadas": duplicadas,
            "ambiguas": ambiguas, "campos_divergentes": divergentes,
            "por_campo": {c: {"acertos": a, "total": t} for c, (a, t) in acertos.items()}}


_CONTAGENS = ("linhas_esperadas", "linhas_obtidas", "linhas_encontradas", "linhas_pareadas", "linhas_inteiramente_corretas", "ausentes", "extras",
              "duplicadas", "ambiguas", "campos_divergentes")


def _somar(partes: list[dict]) -> dict:
    total = {k: 0 for k in _CONTAGENS} | {"por_campo": {c: {"acertos": 0, "total": 0} for c in CAMPOS}}
    for p in partes:
        for k in _CONTAGENS:
            total[k] += p[k]
        for c in CAMPOS:
            for k in ("acertos", "total"):
                total["por_campo"][c][k] += p["por_campo"][c][k]
    acertos = sum(v["acertos"] for v in total["por_campo"].values())
    campos = sum(v["total"] for v in total["por_campo"].values())
    total["precisao_todos_os_campos"] = round(100 * acertos / campos, 1) if campos else None
    return total


def _rodar_validar_real(arquivo: Path, caso: dict, dados: Path) -> int:
    raiz = Path(__file__).resolve().parents[2]
    return subprocess.run([sys.executable, "-m", "observatorio.operacao", "validar-real", str(arquivo), "--data", caso["data"],
                           "--url", caso["url"], "--dados", str(dados)], capture_output=True, cwd=raiz).returncode


def _resultado(situacao: str, motivo: str | None, conjuntos: dict) -> dict:
    return {"situacao": situacao, "aprovado": situacao == APROVADO, "codigo_de_saida": CODIGO_DE_SAIDA[situacao],
            "motivo": motivo, "conjuntos": conjuntos}


def executar(pasta_pdfs: str | Path, esperado_privado: str | Path | None, manifesto: str | Path = MANIFESTO,
             rodar=_rodar_validar_real) -> dict:
    casos = json.loads(Path(manifesto).read_text(encoding="utf-8"))["casos"]
    if not casos:
        return _resultado(INDISPONIVEL, "o manifesto não tem casos", {})
    try:
        privado = json.loads(Path(esperado_privado).read_text(encoding="utf-8")) if esperado_privado else None
    except (OSError, ValueError) as e:
        return _resultado(INDISPONIVEL, f"esperado privado ilegível ou ausente ({type(e).__name__})", {})
    if not isinstance(privado, dict):
        return _resultado(INDISPONIVEL, "esperado privado não informado", {})
    pasta = Path(pasta_pdfs) if pasta_pdfs else None
    if pasta is None or not pasta.is_dir():
        return _resultado(INDISPONIVEL, "pasta dos PDFs oficiais ausente", {})
    por_sha = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in pasta.glob("*.pdf")}

    itens: dict[str, list] = {}
    contratados: set[tuple[str, str]] = set()
    with tempfile.TemporaryDirectory(prefix="corpus-") as temporaria:
        execucoes: dict[str, int] = {}
        for caso in casos:
            chave = f"{caso['data'][8:10]}-{caso['data'][5:7]}|{caso['resenha']}"
            contratados.add((caso["conjunto"], chave))
            rotulo = {"caso": f"{caso['data']} {caso['resenha']}"}
            esperado = privado.get(caso["conjunto"], {})
            esperadas = esperado.get(chave) if isinstance(esperado, dict) else None
            evento = (caso.get("esperado_publico") or {}) if (caso.get("esperado_publico") or {}).get("evento") else None
            if esperadas is None and evento is None:
                itens.setdefault(caso["conjunto"], []).append({**rotulo, "situacao": ESPERADO_AUSENTE})
                continue
            if esperadas is not None and not esperadas:
                itens.setdefault(caso["conjunto"], []).append({**rotulo, "situacao": ESPERADO_VAZIO})
                continue
            arquivo = por_sha.get(caso["sha256"])
            if arquivo is None:
                itens.setdefault(caso["conjunto"], []).append({**rotulo, "situacao": PDF_AUSENTE})
                continue
            dados = Path(temporaria) / caso["sha256"][:12]
            if caso["sha256"] not in execucoes:
                try:
                    execucoes[caso["sha256"]] = rodar(arquivo, caso, dados)
                except (OSError, subprocess.SubprocessError):
                    execucoes[caso["sha256"]] = -1
            codigo = execucoes[caso["sha256"]]
            try:
                if codigo not in (saida.SUCESSO, saida.CONCLUIDO_COM_PENDENCIAS):
                    raise FalhaDeExecucao(f"validar-real terminou com código {codigo}")
                if evento is not None:
                    parcial = comparar_evento(evento, _eventos_extraidos(dados / "observatorio.sqlite3", caso["pagina_pdf"]))
                    if esperadas is not None:        # o caso também tem linhas esperadas: as duas partes precisam conferir
                        linhas = comparar(esperadas, _linhas_extraidas(dados / "observatorio.sqlite3", caso["resenha"]))
                        parcial = {**linhas, "evento": parcial,
                                   "situacao": CONFERE if parcial["situacao"] == linhas["situacao"] == CONFERE else DIVERGENTE}
                else:
                    parcial = comparar(esperadas, _linhas_extraidas(dados / "observatorio.sqlite3", caso["resenha"]))
            except FalhaDeExecucao as e:
                itens.setdefault(caso["conjunto"], []).append({**rotulo, "situacao": FALHA_EXECUCAO, "motivo": str(e)})
                continue
            itens.setdefault(caso["conjunto"], []).append({**rotulo, **parcial})
        # Esperado privado para caso que o manifesto público não contrata: o contrato está inconsistente.
        for conjunto, linhas in privado.items():
            if isinstance(linhas, dict):
                for chave in linhas:
                    if (conjunto, chave) not in contratados:
                        itens.setdefault(conjunto, []).append({"caso": chave.split("|")[-1], "situacao": CASO_NAO_CONTRATADO})

    conjuntos = {c: {"casos": lista, "total": _somar([i for i in lista if "por_campo" in i]),
                     "por_situacao": dict(Counter(i["situacao"] for i in lista))} for c, lista in itens.items()}
    todas = [i["situacao"] for lista in itens.values() for i in lista]
    avaliados = [s for s in todas if s not in NAO_AVALIADOS]
    if not avaliados:
        return _resultado(INDISPONIVEL, "nenhum caso pôde ser avaliado", conjuntos)
    if any(s in (DIVERGENTE, FALHA_EXECUCAO) for s in avaliados):
        return _resultado(REPROVADO, "há casos divergentes ou com falha de execução", conjuntos)
    if len(avaliados) < len(todas):
        return _resultado(PARCIAL, "parte do contrato não pôde ser avaliada", conjuntos)
    return _resultado(APROVADO, None, conjuntos)
