"""Fluxo completo sobre PDFs já obtidos: importar → ler (texto/OCR) → classificar GEDIV.

A obtenção automática nas fontes oficiais é feita por `observatorio.coleta` (lotes). Este fluxo
serve tanto para PDFs baixados quanto para PDFs fornecidos manualmente — o caminho é o mesmo.

Resultado (Etapa 05.3.1 — antes o comando saía com 0 mesmo com leitura em ERRO): o retorno traz
`resultado = {codigo, situacao, motivos, retomada}`, com os códigos de `saida.py`:
- FALHA (1): importação recusada, leitura em ERRO (nesta execução OU de execuções anteriores ainda não refeitas),
  arquivo que a classificação não conseguiu processar;
- CONCLUIDO_COM_PENDENCIAS (3): leitura com páginas pendentes nesta execução, arquivos ainda na fila;
- NAO_EXECUTADO (4): a origem informada não existe ou não tem PDF;
- SUCESSO (0): nada disso.
Tudo o que foi gravado continua gravado: a retomada (`--refazer-pendentes`) relê os arquivos em ERRO ou com
páginas pendentes, e a fila de classificação é retomada sozinha na próxima execução.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..coleta import coletor
from ..coleta.fontes import data_do_nome
from ..gerencias.gediv import processo
from ..leitura import leitor
from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from . import saida

RETOMADA = "python -m observatorio.operacao executar --refazer-pendentes"


def resultado(codigo: int, motivos: list[str], retomada: dict | None = None) -> dict:
    return {"codigo": codigo, "situacao": saida.NOMES[codigo], "motivos": motivos, "retomada": retomada or {}}


def avaliar(importacao: list[dict], leitura: dict, classificacao: dict, erros_de_leitura_na_base: int,
            fila_de_classificacao: int, pendencias_na_base: int = 0, conflitos_abertos: int = 0,
            releituras_pendentes: int = 0) -> dict:
    falhas, pendencias = [], []
    recusados = [i for i in importacao if not i.get("aceito")]
    if recusados:
        falhas.append(f"{len(recusados)} arquivo(s) recusado(s) na importação")
    if leitura.get("ERRO"):
        falhas.append(f"{leitura['ERRO']} arquivo(s) com erro de leitura nesta execução")
    anteriores = erros_de_leitura_na_base - leitura.get("ERRO", 0)
    if anteriores > 0:
        falhas.append(f"{anteriores} arquivo(s) com erro de leitura de execuções anteriores, ainda não refeitos")
    if classificacao.get("com_erro"):
        falhas.append(f"{classificacao['com_erro']} arquivo(s) que a classificação não conseguiu processar")
    if leitura.get("RELEITURA_RECUSADA"):
        pendencias.append(f"{leitura['RELEITURA_RECUSADA']} releitura(s) recusada(s) por perda de conteúdo; a leitura válida "
                          "anterior foi mantida")
    if classificacao.get("conflitos"):
        pendencias.append(f"{classificacao['conflitos']} conflito(s) entre a nova extração e dados revisados, para a gerência")
    if leitura.get("LIDA_COM_PENDENCIAS"):
        pendencias.append(f"{leitura['LIDA_COM_PENDENCIAS']} arquivo(s) lido(s) com páginas pendentes")
    if leitura.get("na_fila"):
        pendencias.append(f"{leitura['na_fila']} arquivo(s) ainda na fila de leitura")
    if fila_de_classificacao:
        pendencias.append(f"{fila_de_classificacao} arquivo(s) ainda na fila de classificação")
    if pendencias_na_base:
        pendencias.append(f"{pendencias_na_base} leitura(s) com pendências persistidas na base")
    if conflitos_abertos:
        pendencias.append(f"{conflitos_abertos} conflito(s) ainda aberto(s) para revisão")
    if releituras_pendentes:
        pendencias.append(f"{releituras_pendentes} releitura(s) com falha ou recusa ainda não resolvida")
    retomada = {"leituras_com_erro": erros_de_leitura_na_base, "fila_de_classificacao": fila_de_classificacao,
                "leituras_com_pendencias": pendencias_na_base, "conflitos_abertos": conflitos_abertos,
                "releituras_pendentes": releituras_pendentes}
    if erros_de_leitura_na_base or pendencias_na_base or releituras_pendentes or leitura.get("LIDA_COM_PENDENCIAS") or leitura.get("RELEITURA_RECUSADA"):
        retomada["comando"] = RETOMADA
    if falhas:
        return resultado(saida.FALHA, falhas + pendencias, retomada)
    if pendencias:
        return resultado(saida.CONCLUIDO_COM_PENDENCIAS, pendencias, retomada)
    return resultado(saida.SUCESSO, [], retomada)


def executar(pasta_dados: str | Path, origem: str | Path | None = None, data: date | None = None, url: str | None = None,
             refazer_pendentes: bool = False) -> dict:
    arquivos: list[Path] = []
    if origem is not None:
        origem = Path(origem)
        if not origem.exists():
            return {"importacao": [], "resultado": resultado(saida.NAO_EXECUTADO, [f"origem não encontrada: {origem.name}"])}
        arquivos = sorted(origem.glob("*.pdf")) if origem.is_dir() else [origem]
        if not arquivos:
            return {"importacao": [], "resultado": resultado(saida.NAO_EXECUTADO, [f"nenhum PDF em {origem.name}"])}
    pasta = Path(pasta_dados)
    banco, acervo = Banco(pasta / "observatorio.sqlite3"), Acervo(pasta / "acervo")
    try:
        importados = []
        for arquivo in arquivos:
            quando = data or data_do_nome(arquivo.name)
            if quando is None:
                importados.append({"arquivo": arquivo.name, "aceito": False, "motivo": "DATA_NAO_INFORMADA_NEM_NO_NOME"})
                continue
            importados.append({"arquivo": arquivo.name, "data": quando.isoformat(),
                               **coletor.importar_manual(banco, acervo, arquivo.read_bytes(), quando,
                                                         url or f"manual:{arquivo.name}", arquivo.name)})
        leitura = leitor.processar(banco, acervo, refazer_pendentes=refazer_pendentes)
        classificacao = processo.classificar_pendentes(banco)
        situacao = processo.situacao(banco)
        erros = banco.con.execute("SELECT COUNT(*) FROM leitura WHERE situacao = 'ERRO'").fetchone()[0]
        pendencias = banco.con.execute(
            "SELECT COUNT(*) FROM leitura WHERE situacao <> 'ERRO' AND (situacao = 'LIDA_COM_PENDENCIAS' "
            "OR paginas_com_pendencia > 0 OR (inconsistencias IS NOT NULL AND inconsistencias NOT IN ('', '[]')))"
        ).fetchone()[0]
        releituras = banco.con.execute("SELECT COUNT(*) FROM leitura WHERE situacao <> 'ERRO' AND erro IS NOT NULL").fetchone()[0]
        conflitos = banco.con.execute("SELECT COUNT(*) FROM conflito WHERE estado = 'ABERTO'").fetchone()[0]
        fontes = [dict(l) for l in banco.con.execute(
            "SELECT fonte, MIN(data_publicacao) AS inicio, MAX(data_publicacao) AS fim, COUNT(*) AS publicacoes "
            "FROM publicacao GROUP BY fonte ORDER BY fonte")]
        return {"importacao": importados, "leitura": leitura, "classificacao": classificacao, "situacao": situacao,
                "escopo": {"fontes_e_periodos_da_base": fontes},
                "resultado": avaliar(importados, leitura, classificacao, erros, situacao["na_fila"],
                                     pendencias, conflitos, releituras)}
    finally:
        banco.fechar()
