"""Coleta em lotes pequenos, sequenciais e retomáveis.

Um lote trata poucas publicações, uma de cada vez, com pausa entre elas, e grava o
desfecho de cada item no banco assim que ele termina. Interromper o programa a qualquer
momento não perde nada: o que foi baixado permanece verificado e o restante continua
pendente para o lote seguinte.

Salvaguardas:
- a carga histórica só é liberada depois de um lote piloto aprovado em CADA fonte oficial;
- o lote para sozinho diante de sinais de recusa da fonte (403, 429, página de verificação
  no lugar do PDF) ou de falhas seguidas — nunca insiste nem tenta contornar a proteção;
- nenhuma requisição é feita em paralelo.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace

from ..nucleo import banco as B
from ..nucleo import rede
from ..nucleo.acervo import Acervo
from . import coletor

PILOTO, HISTORICO = "piloto", "historico"
SUCESSOS = {"NOVO", "DUPLICADO", "IGUAL", "ALTERADO"}
MINIMO_PILOTO = 3  # edições de datas diferentes exigidas para aprovar um piloto


@dataclass(frozen=True)
class Parametros:
    tamanho: int = 10            # publicações por lote
    pausa: float = 8.0           # segundos entre downloads
    max_falhas_seguidas: int = 3 # encerra o lote ao atingir
    max_tentativas: int = 5      # por publicação, somando todos os lotes


PARAMETROS_PILOTO = Parametros(tamanho=5, pausa=10.0, max_falhas_seguidas=2)


def selecionar_piloto(banco: B.Banco, fonte: str, parametros: Parametros) -> list:
    """Até `tamanho` edições normais, de datas diferentes, espalhadas pelo período descoberto."""
    por_data: dict[str, object] = {}
    for linha in banco.pendentes(fonte, parametros.max_tentativas):
        if linha["tipo"] == "normal" and linha["ordem"] == 0:
            por_data.setdefault(linha["data_publicacao"], linha)
    datas = sorted(por_data)
    if len(datas) <= parametros.tamanho:
        return [por_data[d] for d in datas]
    passo = (len(datas) - 1) / (parametros.tamanho - 1)
    return [por_data[datas[round(i * passo)]] for i in range(parametros.tamanho)]


def selecionar_historico(banco: B.Banco, fonte: str, parametros: Parametros, mes: str | None = None) -> list:
    """As pendências mais antigas, sem misturar meses: o lote fica dentro do primeiro mês com pendência."""
    pendentes = banco.pendentes(fonte, parametros.max_tentativas, mes)
    if not pendentes:
        return []
    primeiro_mes = pendentes[0]["data_publicacao"][:7]
    return [p for p in pendentes if p["data_publicacao"][:7] == primeiro_mes][: parametros.tamanho]


def fontes_sem_piloto(banco: B.Banco, siglas) -> list[str]:
    return [s for s in siglas if not banco.piloto_aprovado(s)]


def _sinal_de_recusa(desfecho: coletor.Desfecho) -> str | None:
    erro = desfecho.erro or ""
    if erro.startswith(("HTTP_403", "HTTP_429")):
        return "INTERROMPIDO_RECUSA_DA_FONTE"
    if "RECEBIDO_HTML_EM_VEZ_DE_PDF" in erro:
        return "INTERROMPIDO_PROTECAO_DA_FONTE"
    return None


def executar_lote(fonte, banco: B.Banco, acervo: Acervo, tipo: str, parametros: Parametros | None = None,
                  politica: rede.Politica | None = None, mes: str | None = None, fontes_exigidas=None,
                  respeitar_robots: bool = True, dormir=time.sleep) -> dict:
    """Executa um lote e devolve o resumo. Nunca levanta exceção por falha de rede."""
    parametros = parametros or (PARAMETROS_PILOTO if tipo == PILOTO else Parametros())
    banco.encerrar_lotes_abandonados()
    if tipo == HISTORICO:
        faltam = fontes_sem_piloto(banco, fontes_exigidas if fontes_exigidas is not None else [fonte.sigla])
        if faltam:
            return {"executado": False, "motivo": "PILOTO_NAO_APROVADO", "fontes_sem_piloto": faltam}
    p = replace(coletor.politica_da(fonte, politica), pausa=min((politica or rede.Politica(frozenset())).pausa, 1.0))
    if respeitar_robots:
        endereco = fonte.url_mes(2026, 1)
        situacao, regras = rede.consultar_robots(endereco, p)
        if regras is not None and not regras.can_fetch(p.agente, endereco):
            return {"executado": False, "motivo": "ROBOTS_RESTRINGE_A_COLETA"}
    itens = (selecionar_piloto(banco, fonte.sigla, parametros) if tipo == PILOTO
             else selecionar_historico(banco, fonte.sigla, parametros, mes))
    if not itens:
        return {"executado": False, "motivo": "NADA_PENDENTE"}

    lote_id = banco.abrir_lote(fonte.sigla, tipo, asdict(parametros))
    contagem: dict[str, int] = {}
    estado, seguidas, feitos = "CONCLUIDO", 0, 0
    try:
        for indice, linha in enumerate(itens):
            if indice:
                dormir(parametros.pausa)
            inicio = time.monotonic()
            d = coletor.baixar_publicacao(fonte, banco, acervo, p, linha)
            banco.registrar_item_lote(lote_id, linha["id"], d.resultado, d.sha256, d.tamanho,
                                      round(time.monotonic() - inicio, 2), d.erro)
            contagem[d.resultado] = contagem.get(d.resultado, 0) + 1
            feitos += 1
            if d.resultado in SUCESSOS:
                seguidas = 0
                continue
            seguidas += 1
            recusa = _sinal_de_recusa(d)
            if recusa:
                estado = recusa
                break
            if seguidas >= parametros.max_falhas_seguidas:
                estado = "INTERROMPIDO_POR_FALHAS"
                break
    except KeyboardInterrupt:
        estado = "INTERROMPIDO_PELO_OPERADOR"

    sucessos = sum(contagem.get(k, 0) for k in SUCESSOS)
    aprovado = None
    if tipo == PILOTO:
        aprovado = estado == "CONCLUIDO" and sucessos == len(itens) and sucessos >= MINIMO_PILOTO
    observacao = None if feitos == len(itens) else f"{len(itens) - feitos} item(ns) não tentado(s) continuam pendentes"
    banco.concluir_lote(lote_id, estado, aprovado, observacao)
    return {"executado": True, "lote": lote_id, "fonte": fonte.sigla, "tipo": tipo, "estado": estado,
            "aprovado": aprovado, "selecionados": len(itens), "tentados": feitos, "resultados": contagem,
            "mes": itens[0]["data_publicacao"][:7] if tipo == HISTORICO else None}


def executar_sequencia(fonte, banco: B.Banco, acervo: Acervo, quantidade: int, pausa_entre_lotes: float,
                       dormir=time.sleep, **opcoes) -> list[dict]:
    """Vários lotes históricos em sequência. Para no primeiro que não concluir normalmente."""
    resumos = []
    for indice in range(quantidade):
        if indice:
            dormir(pausa_entre_lotes)
        resumo = executar_lote(fonte, banco, acervo, HISTORICO, dormir=dormir, **opcoes)
        resumos.append(resumo)
        if not resumo["executado"] or resumo["estado"] != "CONCLUIDO":
            break
    return resumos
