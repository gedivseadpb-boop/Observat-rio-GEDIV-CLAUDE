"""Complemento óptico explícito de candidatos: nunca homologa nem reclassifica.

Usa somente detalhe/pendencias/conflito/auditoria do esquema 8. O leitor 0.8 e
o classificador permanecem independentes deste recurso opcional.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

from . import catalogo as C

VERSAO = "paddle-complementar-1"
MODELOS = {
    "PP-OCRv6_medium_det": {
        "inference.json": "0f1a7ec35da36173529c7a60238b7f7919e3831929c3f700ad90ad4896adecd5",
        "inference.pdiparams": "85218d2e3d98f5a21c58b4220627be923a97aee5db3cc71f39536ab31ac53960",
        "inference.yml": "7298d5ead546584af2504d03355f881ac7a7bc0eb1e282d3e159277c1d0af871",
    },
    "PP-OCRv6_medium_rec": {
        "inference.json": "0b2e25e990bd072f1bf77d59d67d508bce6c4bd44af6624e0fb27d6da2cd00e8",
        "inference.pdiparams": "1b01c79a914587933f615569e75de54f2e638ebb5d3f3b3c1b38c24ede8c7319",
        "inference.yml": "991b700facf5b50a7de193468207d5f4255b538dde0d312ae3b7c7a9b6873129",
    },
}


class Indisponivel(RuntimeError):
    """Somente códigos técnicos, nunca mensagens ou texto extraído do PDF."""


@dataclass(frozen=True)
class Config:
    modelos: Path
    python: str = sys.executable
    timeout: float = 180
    memoria_mb: int = 3584
    max_regioes: int = 8
    max_paginas: int = 4

    def __post_init__(self):
        if not 0 < self.timeout <= 600 or not 256 <= self.memoria_mb <= 4096:
            raise ValueError("limites inválidos")
        if not 1 <= self.max_regioes <= 16 or not 1 <= self.max_paginas <= 8:
            raise ValueError("limites inválidos")


def modelos_conferidos(raiz):
    for nome, arquivos in MODELOS.items():
        for arquivo, esperado in arquivos.items():
            p = Path(raiz) / nome / arquivo
            if not p.is_file():
                raise Indisponivel("PADDLE_PESOS_AUSENTES")
            h = hashlib.sha256()
            with p.open("rb") as entrada:
                for bloco in iter(lambda: entrada.read(1 << 20), b""):
                    h.update(bloco)
            if h.hexdigest() != esperado:
                raise Indisponivel("PADDLE_HASH_DIVERGENTE")


def executar(pdf, paginas, config):
    """Processo isolado, tempo/RSS limitados; sem downloads de modelos ou logs públicos."""
    modelos_conferidos(config.modelos)
    try:
        import psutil  # opcional, inclusive o monitor: ausência produz fallback
    except ImportError:
        raise Indisponivel("PADDLE_MONITOR_AUSENTE") from None
    with tempfile.TemporaryDirectory(prefix="gediv-paddle-") as pasta:
        pasta = Path(pasta)
        pedido = {"pdf": str(Path(pdf).resolve()), "paginas": paginas,
                  "modelos": str(Path(config.modelos).resolve()), "max_regioes": config.max_regioes}
        entrada, saida = pasta / "entrada.json", pasta / "saida.json"
        entrada.write_text(json.dumps(pedido), encoding="utf-8")
        env = dict(os.environ, PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="True", HF_HUB_OFFLINE="1",
                   HF_HOME=str(pasta / "hf"), PADDLE_PDX_CACHE_HOME=str(pasta / "cache"),
                   XDG_CACHE_HOME=str(pasta / "cache"), OMP_THREAD_LIMIT="2", OMP_NUM_THREADS="1", MKL_NUM_THREADS="2")
        inicio = time.monotonic()
        try:
            with (pasta / "privado.log").open("w") as log:
                proc = subprocess.Popen([config.python, "-m", "observatorio.gerencias.gediv.paddle_worker",
                                         str(entrada), str(saida)], stdout=log, stderr=log, env=env)
                try:
                    while proc.poll() is None:
                        if time.monotonic() - inicio > config.timeout:
                            raise Indisponivel("PADDLE_TIMEOUT")
                        try:
                            p = psutil.Process(proc.pid)
                            rss = sum(c.memory_info().rss for c in [p] + p.children(recursive=True))
                            if rss > config.memoria_mb * 1024 ** 2:
                                raise Indisponivel("PADDLE_LIMITE_MEMORIA")
                        except psutil.Error:
                            pass
                        time.sleep(0.1)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait()
            if proc.returncode or not saida.is_file() or saida.stat().st_size > 2_000_000:
                raise Indisponivel("PADDLE_FALHA_EXECUCAO")
            dados = json.loads(saida.read_text(encoding="utf-8"))
            if dados.get("erro"):
                raise Indisponivel(dados["erro"] if re.fullmatch(r"PADDLE_[A-Z_]+", dados["erro"])
                                   else "PADDLE_FALHA_EXECUCAO")
            return dados
        except (OSError, ValueError):
            raise Indisponivel("PADDLE_INDISPONIVEL") from None


def _matricula(valor):
    texto = str(valor or "").strip()
    return re.sub(r"[.\s-]", "", texto) if re.fullmatch(r"[\d.\s-]+", texto) else ""


def _processo(valor):
    return re.sub(r"\s+", "", str(valor or "")).upper()


def _pendente(detalhe):
    return not all(isinstance(v, str) and re.fullmatch("[A-F]", v) for v in
                   (detalhe.get("classe_anterior"), detalhe.get("classe_posterior"))) or bool(
        detalhe.get("observacao") or detalhe.get("evolucao_lida") or detalhe.get("observacoes"))


def avaliar(decisao, candidatos, revisada=False):
    """Função pura: nenhuma correção de identidade/caractere, nenhum preenchimento parcial."""
    detalhe = json.loads(decisao["detalhe"] or "{}")
    if not re.fullmatch(r"[A-Z]{2,6}-(PSE|PRC|OFI)-20\d{2}[/-]\d{3,9}", _processo(decisao["processo"])):
        return detalhe, "APENAS SINALIZADO", "PADDLE_IDENTIDADE_DIVERGENTE", []
    associados = [c for c in candidatos if c.get("pagina") == decisao["pagina"]
                  and _processo(c.get("processo")) == _processo(decisao["processo"])]
    if len(associados) != 1:
        return detalhe, "APENAS SINALIZADO", "PADDLE_ASSOCIACAO_AMBIGUA", []
    c = associados[0]
    if not _matricula(decisao["matricula"]) or _matricula(c.get("matricula")) != _matricula(decisao["matricula"]):
        return detalhe, "APENAS SINALIZADO", "PADDLE_IDENTIDADE_DIVERGENTE", []
    classes = (c.get("classe_anterior"), c.get("classe_posterior"))
    confiancas = c.get("confiancas", [])
    if (not c.get("geometria_segura") or len(confiancas) != 4 or
            any(not isinstance(n, (int, float)) or not 0.90 <= n <= 1 for n in confiancas) or
            any(not isinstance(v, str) or not re.fullmatch("[A-F]", v) for v in classes)):
        return detalhe, "APENAS SINALIZADO", "PADDLE_CANDIDATO_INSEGURO", []
    existentes = (detalhe.get("classe_anterior"), detalhe.get("classe_posterior"))
    conflitos = [(campo, velho, novo) for campo, velho, novo in zip(
        ("classe_anterior", "classe_posterior"), existentes, classes) if velho is not None and str(velho).strip() and velho != novo]
    diferencas = [campo for campo, chave in (("servidor", "nome"), ("cargo", "cargo"))
                  if C.normalizar(decisao[campo] or "") != C.normalizar(c.get(chave) or "")]
    origem = {"versao": VERSAO, "pagina": c["pagina"], "bbox_pdf": c.get("bbox_pdf"),
              "confiancas": confiancas, "classes_candidatas": list(classes), "diferencas": diferencas,
              "modelos": MODELOS, "runtime": "paddleocr=3.7.0;paddlex=3.7.2;paddlepaddle=3.2.0;cpu"}
    if revisada:
        conflitos = [(k, v, n) for k, v, n in zip(("classe_anterior", "classe_posterior"), existentes, classes) if v != n]
        status, motivo = "APENAS SINALIZADO", "PADDLE_REVISAO_PREVIA"
    elif conflitos:
        status, motivo = "APENAS SINALIZADO", "PADDLE_DIVERGENCIA_CLASSES"
    elif any(v is not None and str(v).strip() for v in existentes):
        status, motivo = "APENAS SINALIZADO", "PADDLE_PAR_EXISTENTE_OU_PARCIAL"
    elif classes[1] <= classes[0]:
        status, motivo = "APENAS SINALIZADO", "PADDLE_EVOLUCAO_INSEGURA"
    else:
        detalhe.update(classe_anterior=classes[0], classe_posterior=classes[1])
        status, motivo = "RECUPERADO", "PADDLE_CONFERENCIA_OBRIGATORIA"
    origem.update(status=status, motivo=motivo)
    # Uma execução idêntica não degrada a proveniência de uma recuperação anterior.
    anterior = detalhe.get("paddleocr", {})
    if anterior.get("status") == "RECUPERADO" and existentes == classes and not revisada:
        return detalhe, "RECUPERADO", anterior["motivo"], []
    detalhe["paddleocr"] = origem
    return detalhe, status, motivo, conflitos


def complementar(banco, acervo, config, limite=None, backend=executar):
    """Opera apenas sobre classificações vigentes; não inicia coleta, leitura ou homologação."""
    resumo = {"arquivos": 0, "regioes": 0, "recuperados": 0, "sinalizados": 0, "falhas": 0}
    shas = banco.con.execute(
        "SELECT c.sha256,c.revisao_leitura FROM classificacao c JOIN leitura l ON l.sha256=c.sha256 "
        "WHERE c.gerencia='GEDIV' AND c.versao_regras=? AND l.situacao<>'ERRO' "
        "AND c.revisao_leitura=l.revisao ORDER BY c.sha256", (C.VERSAO_REGRAS,)).fetchall()
    for item in shas[:limite] if limite is not None else shas:
        sha = item[0]
        decisoes = banco.con.execute(
            "SELECT d.* FROM decisao d JOIN ato a ON a.id=d.ato_id "
            "WHERE d.sha256=? AND a.eixo=? AND a.modalidade=? ORDER BY d.pagina,d.id",
            (sha, C.PROGRESSAO, C.VERTICAL)).fetchall()
        alvos = [d for d in decisoes if _pendente(json.loads(d["detalhe"] or "{}"))]
        if not alvos:
            continue
        numeros = sorted({d["pagina"] for d in alvos})
        paginas = {str(n): [{"processo": d["processo"], "matricula": d["matricula"]}
                            for d in decisoes if d["pagina"] == n] for n in numeros[:config.max_paginas]}
        resumo["arquivos"] += 1
        falha = None
        try:
            if not acervo.conferir(sha):
                raise Indisponivel("PADDLE_PDF_AUSENTE_OU_ADULTERADO")
            dados = backend(acervo.caminho(sha), paginas, config)
            candidatos = dados["candidatos"]
            if (not isinstance(candidatos, list) or len(candidatos) > 1000
                    or any(not isinstance(c, dict) for c in candidatos)):
                raise ValueError("resposta inválida")
            resumo["regioes"] += dados.get("regioes", 0)
        except Exception as e:
            falha = str(e) if isinstance(e, Indisponivel) and re.fullmatch(r"PADDLE_[A-Z_]+", str(e)) else "PADDLE_FALHA_EXECUCAO"
            candidatos = []
            resumo["falhas"] += 1
        with banco.con:
            if not banco.con.in_transaction:
                banco.con.execute("BEGIN IMMEDIATE")
            # Releitura concorrente invalida toda a proposta calculada sobre a revisão antiga.
            atual = banco.con.execute("SELECT c.revisao_leitura,l.revisao FROM classificacao c JOIN leitura l "
                                      "ON l.sha256=c.sha256 WHERE c.sha256=? AND c.gerencia='GEDIV'", (sha,)).fetchone()
            if not atual or atual[0] != atual[1] or atual[0] != item[1]:
                continue
            for original in decisoes:
                if original["pagina"] not in numeros:
                    continue
                d = banco.con.execute("SELECT * FROM decisao WHERE id=?", (original["id"],)).fetchone()
                if not d:
                    continue
                revisada = d["validacao"] != "PENDENTE" or d["origem"] == "MANUAL" or d["revisado_em"] is not None
                revisada |= bool(banco.correcoes("decisao", d["id"]) or banco.trilha("decisao", d["id"])
                                  or banco.correcoes("ato", d["ato_id"]))
                ato_atual = banco.con.execute("SELECT eixo,modalidade FROM ato WHERE id=?", (d["ato_id"],)).fetchone()
                contexto_alterado = not ato_atual or tuple(ato_atual) != (C.PROGRESSAO, C.VERTICAL)
                velho = json.loads(d["detalhe"] or "{}")
                if falha or contexto_alterado or str(d["pagina"]) not in paginas:
                    novo, status, motivo, conflitos = velho.copy(), "APENAS SINALIZADO", falha or ("PADDLE_CONTEXTO_ALTERADO" if contexto_alterado else "PADDLE_LIMITE_PAGINAS"), []
                else:
                    novo, status, motivo, conflitos = avaliar(d, candidatos, revisada)
                if (falha or str(d["pagina"]) not in paginas) and velho.get("paddleocr", {}).get("status") == "RECUPERADO":
                    novo["paddleocr"] = dict(velho["paddleocr"], ultimo_aviso=motivo)
                elif "paddleocr" not in novo or falha:
                    novo["paddleocr"] = {"status": status, "motivo": motivo, "versao": VERSAO}
                novo["paddleocr"]["pdf_sha256"] = sha
                novo["paddleocr"]["revisao_leitura"] = atual[0]
                if novo != velho:
                    banco.con.execute("UPDATE decisao SET detalhe=? WHERE id=?", (json.dumps(novo, ensure_ascii=False), d["id"]))
                    banco.auditar("robô (PaddleOCR complementar)", "PADDLE_COMPLEMENTO", "classificacao", sha,
                                  {"decisao_id": d["id"], "paddleocr": velho.get("paddleocr")},
                                  {"decisao_id": d["id"], "paddleocr": novo["paddleocr"]}, motivo)
                for campo, vigente, proposto in conflitos:
                    banco._conflito("decisao", d["id"], campo, vigente, proposto, "PADDLEOCR", sha)
                for tabela, coluna, chave in (("ato", "pendencias", d["ato_id"]), ("classificacao", "pendencias", sha)):
                    where = "id=?" if tabela == "ato" else "sha256=? AND gerencia='GEDIV'"
                    reg = banco.con.execute(f"SELECT {coluna} FROM {tabela} WHERE {where}", (chave,)).fetchone()
                    pendencias = json.loads(reg[0] or "[]")
                    aviso = f"{motivo}: complemento óptico candidato; conferir no PDF; não homologado"
                    if aviso not in pendencias:
                        pendencias.append(aviso)
                        banco.con.execute(f"UPDATE {tabela} SET {coluna}=? WHERE {where}",
                                          (json.dumps(pendencias, ensure_ascii=False), chave))
                if status == "RECUPERADO":
                    resumo["recuperados"] += int(not velho.get("classe_anterior") and not velho.get("classe_posterior"))
                else:
                    resumo["sinalizados"] += 1
    return resumo


def preservar_propostas(banco, resultado, sha):
    """Reclassificar a MESMA revisão não perde propostas já auditadas.

    Nova leitura/regras, identidade, texto ou campos distintos impedem reuso.
    Revisões humanas continuam sendo preservadas pelo contrato PR06 do Banco.
    Não carrega bibliotecas ópticas nem executa modelos.
    """
    vigente = banco.con.execute(
        "SELECT c.revisao_leitura FROM classificacao c JOIN leitura l ON c.sha256=l.sha256 "
        "WHERE c.sha256=? AND c.gerencia='GEDIV' AND c.versao_regras=? "
        "AND c.revisao_leitura=l.revisao AND l.situacao<>'ERRO'", (sha, C.VERSAO_REGRAS)).fetchone()
    if not vigente:
        return
    for d in resultado.decisoes:
        r = banco.con.execute("SELECT * FROM decisao WHERE id=? AND sha256=?", (d.id, sha)).fetchone()
        if not r or any(getattr(d, k) != r[k] for k in ("pagina", "processo", "matricula", "servidor", "cargo", "trecho")):
            continue
        anterior = json.loads(r["detalhe"] or "{}")
        origem = anterior.get("paddleocr", {})
        if (origem.get("versao") != VERSAO or origem.get("pdf_sha256") != sha
                or origem.get("revisao_leitura") != vigente[0]):
            continue
        if origem.get("status") == "RECUPERADO":
            par = [anterior.get("classe_anterior"), anterior.get("classe_posterior")]
            if any(d.detalhe.get(k) for k in ("classe_anterior", "classe_posterior")) or par != origem.get("classes_candidatas"):
                continue
            d.detalhe.update(classe_anterior=par[0], classe_posterior=par[1])
        d.detalhe["paddleocr"] = origem
        aviso = f"{origem['motivo']}: complemento óptico candidato; conferir no PDF; não homologado"
        ato = next((a for a in resultado.atos if a.id == d.ato_id), None)
        if ato and aviso not in ato.pendencias:
            ato.pendencias.append(aviso)
        if aviso not in resultado.pendencias:
            resultado.pendencias.append(aviso)
