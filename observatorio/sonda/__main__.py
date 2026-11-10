"""Painel de Publicações DOE-PB GEDIV — sonda de acesso às fontes oficiais do DOE/PB.

Uso:  python -m observatorio.sonda [--saida relatorio.json]

Precisa apenas do Python (nenhuma biblioteca adicional). Não grava PDFs,
não lê conteúdo de publicações e faz poucas requisições pequenas.

Objetivo: descobrir EM QUE CAMADA o acesso falha, em vez de presumir a causa.
Cada servidor é testado separadamente em:
  1. DNS            — o nome resolve? para quais endereços IPv4 e IPv6?
  2. TCP            — cada endereço aceita conexão nas portas 443 e 80?
  3. TLS            — o certificado é aceito? qual versão do protocolo?
  4. HTTP           — o servidor responde? com qual status, para identificações diferentes?
  5. robots.txt     — o site declara restrições à coleta automatizada?
  6. PDF            — os primeiros bytes de um documento conhecido chegam com a assinatura %PDF?
Servidores de controle (um do mesmo governo, um externo) indicam se a falha é
geral da rede do executor ou específica das fontes.
"""
from __future__ import annotations

import argparse
import http.client
import json
import platform
import socket
import ssl
import sys
import time
import urllib.parse
from datetime import datetime, timezone

TEMPO = 12
NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
ROBO = "ObservatorioGEDIV/0.1 (+https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE)"

ALVOS = [
    {"servidor": "auniao.pb.gov.br", "papel": "fonte principal",
     "paginas": ["/servicos/doe/2026", "/servicos/doe/2026/novembro"],
     "pdf": "/servicos/doe/2026/outubro/diario-oficial-15-10-2026-portal.pdf"},
    {"servidor": "www.auniao.pb.gov.br", "papel": "fonte principal (www)",
     "paginas": ["/servicos/doe/2026"], "pdf": None},
    {"servidor": "cge.pb.gov.br", "papel": "fonte complementar",
     "paginas": ["/gati/sap/sap26.asp?a=2026&m=11"], "pdf": None},
    {"servidor": "paraiba.pb.gov.br", "papel": "controle: mesmo governo", "paginas": ["/"], "pdf": None},
    {"servidor": "www.gov.br", "papel": "controle: governo federal", "paginas": ["/"], "pdf": None},
    {"servidor": "github.com", "papel": "controle: externo", "paginas": ["/"], "pdf": None},
]


def cronometrar(funcao):
    inicio = time.monotonic()
    try:
        valor, erro = funcao(), None
    except Exception as e:  # o objetivo é justamente classificar qualquer falha
        valor, erro = None, f"{type(e).__name__}: {e}"[:200]
    return valor, erro, round(time.monotonic() - inicio, 2)


def dns(servidor):
    enderecos = {"ipv4": [], "ipv6": []}
    for info in socket.getaddrinfo(servidor, 443, type=socket.SOCK_STREAM):
        chave = "ipv6" if info[0] == socket.AF_INET6 else "ipv4"
        if info[4][0] not in enderecos[chave]:
            enderecos[chave].append(info[4][0])
    return enderecos


def tcp(endereco, porta):
    with socket.create_connection((endereco, porta), timeout=TEMPO):
        return "CONECTOU"


def tls(endereco, servidor):
    contexto = ssl.create_default_context()
    with socket.create_connection((endereco, 443), timeout=TEMPO) as bruto:
        with contexto.wrap_socket(bruto, server_hostname=servidor) as seguro:
            certificado = seguro.getpeercert()
            return {"protocolo": seguro.version(), "valido_ate": certificado.get("notAfter"),
                    "emissor": dict(x[0] for x in certificado.get("issuer", ())).get("organizationName")}


def http_get(servidor, caminho, agente, faixa=None, seguro=True):
    classe = http.client.HTTPSConnection if seguro else http.client.HTTPConnection
    conexao = classe(servidor, timeout=TEMPO)
    try:
        cabecalhos = {"User-Agent": agente, "Accept": "*/*"}
        if faixa:
            cabecalhos["Range"] = faixa
        conexao.request("GET", caminho, headers=cabecalhos)
        r = conexao.getresponse()
        corpo = r.read(4096)
        return {"status": r.status, "desafio_javascript": desafio(corpo), "tipo": r.getheader("Content-Type"), "servidor_web": r.getheader("Server"),
                "destino": r.getheader("Location"), "tamanho_declarado": r.getheader("Content-Length"),
                "bytes_lidos": len(corpo), "assinatura_pdf": corpo[:5] == b"%PDF-",
                "parece_html": corpo[:200].lstrip().lower().startswith((b"<!doctype", b"<html"))}
    finally:
        conexao.close()


def desafio(corpo: bytes) -> bool:
    """Indica página de verificação anti-robô (exige navegador com JavaScript) no lugar do conteúdo."""
    return any(marca in corpo for marca in (b"/TSPD/", b"enable JavaScript", b"cf-challenge", b"captcha"))


def robots(servidor):
    conexao = http.client.HTTPSConnection(servidor, timeout=TEMPO)
    try:
        conexao.request("GET", "/robots.txt", headers={"User-Agent": ROBO})
        r = conexao.getresponse()
        bruto = r.read(20000)
        texto = bruto.decode("utf-8", "replace")
        if texto.lstrip().startswith("<"):
            return {"status": r.status, "formato": "HTML (não é um robots.txt)", "desafio_javascript": desafio(bruto), "regras": []}
        linhas = [l.strip() for l in texto.splitlines() if l.strip() and not l.strip().startswith("#")]
        return {"status": r.status, "formato": "texto", "regras": linhas[:40] if r.status == 200 else []}
    finally:
        conexao.close()


def registrar(alvo, chave, funcao):
    valor, erro, segundos = cronometrar(funcao)
    alvo[chave] = {"resultado": valor, "erro": erro, "segundos": segundos}
    return valor


def sondar(definicao):
    servidor = definicao["servidor"]
    alvo = {"servidor": servidor, "papel": definicao["papel"]}
    enderecos = registrar(alvo, "dns", lambda: dns(servidor))
    if not enderecos:
        alvo["camada_da_falha"] = "DNS"
        return alvo
    alvo["tcp"], alvo["tls"] = {}, {}
    for endereco in (enderecos["ipv4"] + enderecos["ipv6"])[:4]:
        for porta in (443, 80):
            registrar(alvo["tcp"], f"{endereco}:{porta}", lambda: tcp(endereco, porta))
        if alvo["tcp"][f"{endereco}:443"]["resultado"]:
            registrar(alvo["tls"], endereco, lambda: tls(endereco, servidor))
    conectou = any(v["resultado"] for k, v in alvo["tcp"].items() if k.endswith(":443"))
    if not conectou:
        alvo["camada_da_falha"] = "TCP (porta 443 não aceitou conexão)"
        if any(v["resultado"] for k, v in alvo["tcp"].items() if k.endswith(":80")):
            registrar(alvo, "http_sem_tls", lambda: http_get(servidor, "/", NAVEGADOR, seguro=False))
        return alvo
    if not any(v["resultado"] for v in alvo["tls"].values()):
        alvo["camada_da_falha"] = "TLS"
        return alvo
    alvo["http"] = {}
    respostas = []
    for caminho in definicao["paginas"]:
        for nome, agente in (("navegador", NAVEGADOR), ("robo_identificado", ROBO)):
            respostas.append(registrar(alvo["http"], f"{caminho} [{nome}]", lambda: http_get(servidor, caminho, agente)))
            time.sleep(1)
    registrar(alvo, "robots", lambda: robots(servidor))
    if definicao["pdf"]:
        registrar(alvo, "pdf_inicio", lambda: http_get(servidor, definicao["pdf"], ROBO, faixa="bytes=0-4095"))
        time.sleep(1)
        registrar(alvo, "pdf_download_plone",
                  lambda: http_get(servidor, definicao["pdf"] + "/@@download/file", ROBO, faixa="bytes=0-4095"))
    if not any(respostas):
        alvo["camada_da_falha"] = "HTTP (sem resposta)"
    elif not any(r and r["status"] < 400 for r in respostas):
        alvo["camada_da_falha"] = "HTTP (respondeu com erro)"
    elif any(r and r.get("desafio_javascript") for r in respostas):
        alvo["camada_da_falha"] = "HTTP (respondeu com página de verificação anti-robô)"
    else:
        alvo["camada_da_falha"] = None
    return alvo


def origem():
    """Identifica por onde o executor sai para a internet (país e provedor)."""
    def consulta():
        conexao = http.client.HTTPSConnection("ipinfo.io", timeout=TEMPO)
        try:
            conexao.request("GET", "/json", headers={"User-Agent": ROBO})
            dados = json.loads(conexao.getresponse().read(5000))
            return {k: dados.get(k) for k in ("country", "region", "org")}
        finally:
            conexao.close()
    valor, erro, _ = cronometrar(consulta)
    return valor or {"erro": erro}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sonda de acesso às fontes do DOE/PB")
    ap.add_argument("--saida", help="arquivo JSON para gravar o relatório")
    a = ap.parse_args(argv)
    relatorio = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "executor": {"sistema": platform.platform(), "python": platform.python_version(), "saida_internet": origem()},
        "alvos": [sondar(d) for d in ALVOS],
    }
    relatorio["resumo"] = {x["servidor"]: x["camada_da_falha"] or "ACESSO OK" for x in relatorio["alvos"]}
    texto = json.dumps(relatorio, ensure_ascii=False, indent=2)
    print(texto)
    if a.saida:
        with open(a.saida, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto)
    fontes_ok = all(relatorio["resumo"][s] == "ACESSO OK" for s in ("auniao.pb.gov.br", "cge.pb.gov.br"))
    return 0 if fontes_ok else 3


if __name__ == "__main__":
    sys.exit(main())
