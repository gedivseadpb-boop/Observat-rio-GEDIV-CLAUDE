"""Aquisição de PDFs oficiais: sonda real de download, coleta por dia/intervalo e cobertura.

A sonda usa a MESMA implementação de rede, descoberta e verificação do coletor e trabalha
num diretório temporário vazio: nada vem de cache, fixture, Drive ou acervo anterior.
O relatório não contém dados pessoais nem identificação da máquina (só sistema operacional,
versão do Python e se a execução ocorreu num executor de CI).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import tempfile
import time
import tracemalloc
from datetime import date, datetime, timezone
from pathlib import Path

from ..coleta import coletor, inventario
from ..coleta.fontes import FONTES
from ..coleta.transporte import Direto, ManifestoContingencia
from ..nucleo import pdf, rede
from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco


def ambiente() -> dict:
    return {
        "sistema": platform.system(), "versao_sistema": platform.release(), "python": platform.python_version(),
        "ci": "github-actions" if os.environ.get("GITHUB_ACTIONS") == "true" else ("ci" if os.environ.get("CI") else None),
        "executor_os": os.environ.get("RUNNER_OS"),
    }


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sonda(sigla: str = "auniao", hashes_conhecidos: dict[str, str] | None = None, politica: rede.Politica | None = None,
          fonte=None, guardar_em: str | None = None) -> dict:
    """Descobre a edição mais recente pela página oficial, baixa o PDF e verifica a integridade.

    Situações: DOWNLOAD_INTEGRO, PDF_EM_QUARENTENA, PDF_REPROVADO, LISTAGEM_INACESSIVEL,
    SEM_EDICAO_NA_LISTAGEM, DOWNLOAD_INACESSIVEL.
    """
    fonte = fonte or FONTES[sigla]()
    p = coletor.politica_da(fonte, politica or rede.Politica(servidores=frozenset(), tentativas=2, tempo_limite=40))
    relatorio = {"fonte": fonte.sigla, "inicio_utc": _agora(), "ambiente": ambiente(), "versao_coletor": coletor.VERSAO_COLETOR,
                 "listagem": None, "edicao": None, "tentativas": [], "situacao": None}
    if not hasattr(fonte, "url_recentes"):
        relatorio["situacao"] = "FONTE_SEM_LISTAGEM_RECENTE"
        return relatorio
    relogio = time.monotonic()
    try:
        resposta = rede.obter(fonte.url_recentes(), p)
    except rede.ErroRede as e:
        relatorio.update(listagem={"url": fonte.url_recentes(), "erro": e.categoria, "detalhe": str(e)[:300]},
                         situacao="LISTAGEM_INACESSIVEL")
        return relatorio
    itens, paginas = fonte.extrair(rede.texto(resposta), resposta.url_final)
    relatorio["listagem"] = {"url": fonte.url_recentes(), "url_final": resposta.url_final, "status": resposta.status,
                             "tipo_conteudo": resposta.tipo_conteudo, "bytes": len(resposta.corpo), "itens": len(itens),
                             "paginas_seguintes": len(paginas), "segundos": round(time.monotonic() - relogio, 3)}
    datados = sorted((i for i in itens if i.data), key=lambda i: (i.data, i.ordem), reverse=True)
    if not datados:
        relatorio["situacao"] = "SEM_EDICAO_NA_LISTAGEM"
        return relatorio
    item = datados[0]
    relatorio["edicao"] = {"url_oficial": item.url, "data": item.data.isoformat(), "tipo": item.tipo, "ordem": item.ordem}
    with tempfile.TemporaryDirectory(prefix="sonda-gediv-") as vazio:
        assert not os.listdir(vazio)  # prova de que nada estava presente antes do download
        for endereco in fonte.enderecos_download(item.url):
            tentativa = {"url": endereco, "inicio_utc": _agora()}
            relogio = time.monotonic()
            tracemalloc.start()
            try:
                r = rede.obter(endereco, p)
            except rede.ErroRede as e:
                tracemalloc.stop()
                tentativa.update(erro=e.categoria, detalhe=str(e)[:300], segundos=round(time.monotonic() - relogio, 3))
                relatorio["tentativas"].append(tentativa)
                if e.recusa:
                    break
                continue
            pico = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            laudo = pdf.verificar(r.corpo, r.content_length)
            tentativa.update(url_final=r.url_final, redirecionamentos=r.redirecionamentos, status=r.status,
                             tipo_conteudo=r.tipo_conteudo, content_length=r.content_length, bytes=laudo.tamanho,
                             sha256=laudo.sha256, paginas=laudo.paginas, integridade=laudo.integridade,
                             motivo=laudo.motivo, alertas=list(laudo.alertas), segundos=round(time.monotonic() - relogio, 3),
                             pico_memoria_mb=round(pico / 2**20, 1), tentativas_rede=r.tentativas)
            relatorio["tentativas"].append(tentativa)
            if laudo.valido:
                destino = Path(vazio) / f"{laudo.sha256}.pdf"
                destino.write_bytes(r.corpo)
                conferido = hashlib.sha256(destino.read_bytes()).hexdigest() == laudo.sha256
                conhecido = (hashes_conhecidos or {}).get(item.url)
                relatorio["edicao"].update(sha256=laudo.sha256, bytes=laudo.tamanho, paginas=laudo.paginas,
                                           gravado_e_reconferido=conferido,
                                           hash_historico=("IGUAL" if conhecido == laudo.sha256 else
                                                           "DIFERENTE" if conhecido else "SEM_HISTORICO"))
                if guardar_em:
                    Path(guardar_em).mkdir(parents=True, exist_ok=True)
                    (Path(guardar_em) / destino.name).write_bytes(r.corpo)
                relatorio["situacao"] = "DOWNLOAD_INTEGRO"
                break
            relatorio["situacao"] = "PDF_EM_QUARENTENA" if laudo.quarentena else "PDF_REPROVADO"
            if laudo.motivo == "RECEBIDO_HTML_EM_VEZ_DE_PDF":
                continue  # o endereço /view devolve HTML legitimamente
    relatorio["situacao"] = relatorio["situacao"] or "DOWNLOAD_INACESSIVEL"
    relatorio["fim_utc"] = _agora()
    return relatorio


def abrir(dados: str) -> tuple[Banco, Acervo]:
    pasta = Path(dados)
    return Banco(pasta / "observatorio.sqlite3"), Acervo(pasta / "acervo")


def coletar(dados: str, siglas: list[str], inicio: date, fim: date, limite: int | None, simular: bool,
            reverificar: bool, contingencia: str | None = None, permitir_longo: bool = False) -> dict:
    banco, acervo = abrir(dados)
    transporte = ManifestoContingencia(contingencia) if contingencia else Direto()
    relogio = time.monotonic()
    tracemalloc.start()
    try:
        resumo = coletor.coletar_intervalo([FONTES[s]() for s in siglas], banco, acervo, inicio, fim, limite=limite,
                                           simular=simular, reverificar=reverificar, transporte=transporte,
                                           permitir_longo=permitir_longo)
    finally:
        pico = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        banco.fechar()
    resumo["desempenho"] = {"segundos": round(time.monotonic() - relogio, 2), "pico_memoria_python_mb": round(pico / 2**20, 1)}
    resumo["pendencias"] = coletor.houve_pendencia(resumo)
    return resumo


def fonte_bloqueada(parte: dict) -> bool:
    """Nenhuma listagem da fonte pôde ser lida (recentes e meses): a coleta não alcançou a fonte."""
    recentes_falhou = bool((parte.get("recentes") or {}).get("erro"))
    meses_falharam = bool(parte["varreduras"]) and all("erro" in v for v in parte["varreduras"])
    return parte.get("robots") == "INACESSIVEL" and recentes_falhou and meses_falharam


def cobertura(dados: str, siglas: list[str], inicio: date, fim: date) -> dict:
    banco, acervo = abrir(dados)
    try:
        return inventario.manifesto(banco, inicio, fim, siglas, acervo)
    finally:
        banco.fechar()


def reabrir(dados: str, sigla: str, inicio: date, fim: date, autor: str, justificativa: str) -> dict:
    banco, _ = abrir(dados)
    try:
        return coletor.reabrir_esgotadas(banco, sigla, inicio, fim, autor, justificativa)
    finally:
        banco.fechar()


def liberar_fonte(dados: str, sigla: str, autor: str, justificativa: str) -> dict:
    banco, _ = abrir(dados)
    try:
        vigente = banco.suspensao_vigente(sigla)
        return {"fonte": sigla, "suspensao": vigente, "liberada": banco.liberar_fonte(sigla, autor, justificativa)}
    finally:
        banco.fechar()


def gravar(relatorio: dict, saida: str | None) -> None:
    if saida:
        Path(saida).write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    json.dump(relatorio, sys.stdout, ensure_ascii=False, indent=2)
    print()
