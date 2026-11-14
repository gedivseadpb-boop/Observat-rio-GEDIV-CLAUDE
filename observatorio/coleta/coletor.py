"""Orquestração da coleta: descobrir, baixar, verificar, guardar e registrar.

Princípios:
- nada é presumido: uma listagem que não pôde ser lida é registrada como
  falha de varredura, nunca como "não houve publicação";
- reexecutar não duplica: o que já foi baixado e conferido é pulado;
- o PDF só entra no acervo depois de passar pela verificação estrutural;
- se um endereço passar a oferecer outro conteúdo, a versão anterior é mantida.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from dataclasses import dataclass, replace
from datetime import date

from ..nucleo import banco as B
from ..nucleo import pdf, rede
from ..nucleo.acervo import Acervo
from .transporte import Direto

MAX_PAGINAS = 30
VERSAO_COLETOR = "coletor-etapa05-2026.11.14"
MAX_DIAS_INTERVALO = 31  # amostras controladas; a carga histórica completa é da Etapa 06


def meses(inicio: date, fim: date):
    ano, mes = inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        yield ano, mes
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def politica_da(fonte, base: rede.Politica | None = None) -> rede.Politica:
    base = base or rede.Politica(servidores=frozenset())
    return replace(base, servidores=frozenset(fonte.servidores) | base.servidores)


def descobrir_mes(fonte, banco: B.Banco, politica: rede.Politica, ano: int, mes: int,
                  inicio: date | None = None, fim: date | None = None) -> dict:
    """Lê a listagem mensal (com paginação) e registra as publicações encontradas."""
    fila, vistas, itens = [fonte.url_mes(ano, mes)], set(), {}
    try:
        while fila and len(vistas) < MAX_PAGINAS:
            pagina = fila.pop(0)
            if pagina in vistas:
                continue
            vistas.add(pagina)
            resposta = rede.obter(pagina, politica)
            achados, proximas = fonte.extrair(rede.texto(resposta), resposta.url_final)
            for item in achados:
                itens.setdefault(item.url, item)
            fila += [p for p in proximas if p not in vistas]
            time.sleep(politica.pausa)
    except rede.ErroRede as e:
        banco.registrar_varredura(fonte.sigla, ano, mes, None, str(e))
        return {"fonte": fonte.sigla, "ano": ano, "mes": mes, "erro": str(e)}
    parcial = bool([p for p in fila if p not in vistas])
    novas = sem_data = 0
    for item in itens.values():
        if item.data is None:
            sem_data += 1
        elif (inicio and item.data < inicio) or (fim and item.data > fim):
            continue
        novas += banco.registrar_descoberta(item.fonte, item.url, item.data.isoformat() if item.data else None,
                                            item.tipo, item.ordem, item.rotulo)
    if parcial:
        # Restaram páginas da listagem além do limite: o mês NÃO é dado como varrido e será relido.
        erro = f"LISTAGEM_PARCIAL: limite de {MAX_PAGINAS} páginas atingido com páginas ainda por ler"
        banco.registrar_varredura(fonte.sigla, ano, mes, len(itens), erro)
        return {"fonte": fonte.sigla, "ano": ano, "mes": mes, "listadas": len(itens), "novas": novas, "sem_data": sem_data,
                "erro": erro}
    banco.registrar_varredura(fonte.sigla, ano, mes, len(itens), None)
    return {"fonte": fonte.sigla, "ano": ano, "mes": mes, "listadas": len(itens), "novas": novas, "sem_data": sem_data}


@dataclass(frozen=True)
class Desfecho:
    """Resultado de uma tentativa de obter uma publicação.

    resultado: NOVO, DUPLICADO (conteúdo já existente no acervo por outra publicação),
    IGUAL, ALTERADO, FALHA_DOWNLOAD ou INVALIDA.
    """
    resultado: str
    sha256: str | None = None
    tamanho: int | None = None
    erro: str | None = None

    @property
    def verificado(self) -> bool:
        return self.sha256 is not None


def descobrir(fonte, banco: B.Banco, politica: rede.Politica, inicio: date, fim: date, refazer: bool = False) -> list[dict]:
    """Varre mês a mês. Meses já lidos com sucesso são pulados, exceto os dois últimos do
    período, que podem ter recebido novas edições. Meses com falha são sempre refeitos."""
    lidos = {(v["ano"], v["mes"]) for v in banco.varreduras() if v["fonte"] == fonte.sigla and v["erro"] is None}
    periodo = list(meses(inicio, fim))
    resultados = []
    for ano, mes in periodo:
        if not refazer and (ano, mes) in lidos and (ano, mes) not in periodo[-2:]:
            resultados.append({"fonte": fonte.sigla, "ano": ano, "mes": mes, "pulado": "já varrido"})
            continue
        resultados.append(descobrir_mes(fonte, banco, politica, ano, mes, inicio, fim))
    return resultados


def _registrar(banco: B.Banco, linha, endereco: str, transporte, inicio: str, resposta=None, laudo=None,
               resultado: str = "", erro: str | None = None, segundos: float | None = None) -> None:
    banco.registrar_download(
        linha["id"], url_pedida=endereco, transporte=transporte.nome, resultado=resultado, erro=erro,
        url_final=resposta.url_final if resposta else None,
        redirecionamentos=json.dumps(resposta.redirecionamentos) if resposta and resposta.redirecionamentos else None,
        status_http=resposta.status if resposta else None, tipo_conteudo=resposta.tipo_conteudo if resposta else None,
        content_length=resposta.content_length if resposta else None,
        bytes=laudo.tamanho if laudo else None, sha256=laudo.sha256 if laudo else None,
        paginas=laudo.paginas if laudo else None, integridade=laudo.integridade if laudo else None,
        alertas=json.dumps(list(laudo.alertas)) if laudo and laudo.alertas else None,
        versao_coletor=VERSAO_COLETOR, iniciado_em=inicio, segundos=segundos,
        tentativas_rede=resposta.tentativas if resposta else None)


def baixar_publicacao(fonte, banco: B.Banco, acervo: Acervo, politica: rede.Politica, linha, transporte=None) -> Desfecho:
    """Tenta os endereços de download da publicação, verifica a estrutura do PDF e registra cada tentativa no manifesto.

    Prioridade do desfecho quando nenhum endereço dá certo: QUARENTENA > INVALIDA > FALHA_DOWNLOAD.
    """
    transporte = transporte or Direto()
    erro, estado = "sem endereço de download", B.FALHA_DOWNLOAD
    for endereco in fonte.enderecos_download(linha["url"]):
        inicio, relogio = B.agora(), time.monotonic()
        try:
            resposta = transporte.obter(endereco, politica)
        except rede.ErroRede as e:
            _registrar(banco, linha, endereco, transporte, inicio, resultado="ERRO_REDE", erro=str(e),
                       segundos=round(time.monotonic() - relogio, 3))
            if erro == "sem endereço de download":
                # Só o primeiro erro de rede é guardado: um 404 no endereço alternativo não apaga a evidência
                # anterior (truncamento, resposta inválida, quarentena), que é a mais informativa.
                erro = str(e)
            if e.recusa:
                # 403/429: parar na primeira recusa. Nenhum endereço alternativo é tentado, e o motivo
                # registrado é o da recusa, para que o lote se encerre e a fonte fique suspensa.
                erro, estado = str(e), B.FALHA_DOWNLOAD
                break
            continue
        finally:
            time.sleep(politica.pausa)
        laudo = pdf.verificar(resposta.corpo, resposta.content_length)
        segundos = round(time.monotonic() - relogio, 3)
        if not laudo.valido:
            if laudo.quarentena:
                acervo.guardar_quarentena(resposta.corpo)
                _registrar(banco, linha, endereco, transporte, inicio, resposta, laudo, B.QUARENTENA, laudo.motivo, segundos)
                erro, estado = f"{laudo.motivo} em {endereco} ({laudo.tamanho} bytes)", B.QUARENTENA
            else:
                _registrar(banco, linha, endereco, transporte, inicio, resposta, laudo, "REPROVADO", laudo.motivo, segundos)
                if estado not in (B.QUARENTENA, B.INVALIDA) or (estado == B.INVALIDA and laudo.truncado):
                    erro = f"{laudo.motivo} em {endereco} ({laudo.tamanho} bytes)"
                    estado = B.FALHA_DOWNLOAD if laudo.truncado else B.INVALIDA
            continue        # o endereço "/view" devolve HTML legitimamente; o de download é tentado em seguida
        sha, gravou = acervo.guardar(resposta.corpo)
        resultado = banco.registrar_arquivo(linha["id"], sha, laudo.tamanho, acervo.caminho_relativo(sha))
        banco.registrar_verificacao(sha, laudo.paginas, laudo.integridade)
        if resultado == "NOVO" and not gravou:
            resultado = "DUPLICADO"
        _registrar(banco, linha, endereco, transporte, inicio, resposta, laudo, resultado, None, segundos)
        return Desfecho(resultado, sha, laudo.tamanho)
    banco.registrar_falha(linha["id"], estado, erro)
    return Desfecho(estado, erro=erro)


def baixar_pendentes(fonte, banco: B.Banco, acervo: Acervo, politica: rede.Politica, limite: int | None = None,
                     max_tentativas: int = 5, reverificar: bool = False, inicio: date | None = None,
                     fim: date | None = None, simular: bool = False, transporte=None) -> dict:
    """Baixa o que está pendente. Com ``simular=True`` apenas lista o que seria baixado, sem acessar a rede.

    Publicações já BAIXADAS só são consultadas de novo com ``reverificar=True`` (verificação deliberada de mudança).
    QUARENTENA também só volta com ``reverificar``: o arquivo retido precisa de diagnóstico, não de insistência.
    """
    estados = (B.DESCOBERTA, B.FALHA_DOWNLOAD, B.INVALIDA) + ((B.BAIXADA, B.QUARENTENA) if reverificar else ())
    contagem: dict[str, int] = {}
    previstas: list[dict] = []
    feitas = 0
    for linha in banco.publicacoes(fonte.sigla, estados):
        data_pub = linha["data_publicacao"]
        if (inicio or fim) and (data_pub is None or (inicio and data_pub < inicio.isoformat())
                                or (fim and data_pub > fim.isoformat())):
            continue
        if linha["estado"] not in (B.BAIXADA, B.QUARENTENA) and linha["tentativas"] >= max_tentativas:
            contagem["ESGOTADA"] = contagem.get("ESGOTADA", 0) + 1
            continue
        if limite is not None and feitas >= limite:
            contagem["ADIADA"] = contagem.get("ADIADA", 0) + 1
            continue
        feitas += 1
        if simular:
            previstas.append({"url": linha["url"], "data": data_pub, "estado": linha["estado"]})
            contagem["SIMULADA"] = contagem.get("SIMULADA", 0) + 1
            continue
        resultado = baixar_publicacao(fonte, banco, acervo, politica, linha, transporte).resultado
        contagem[resultado] = contagem.get(resultado, 0) + 1
    if simular:
        contagem["previstas"] = previstas
    return contagem


def descobrir_recentes(fonte, banco: B.Banco, politica: rede.Politica, max_paginas: int = 2,
                       inicio: date | None = None, fim: date | None = None) -> dict:
    """Lê a listagem "Edições recentes" (quando a fonte a oferece) e registra as publicações do período.

    Não marca nenhum mês como varrido: a listagem recente mostra só as últimas edições e não prova ausência.
    """
    if not hasattr(fonte, "url_recentes"):
        return {"fonte": fonte.sigla, "recentes": "NAO_OFERECIDA"}
    fila, vistas, itens = [fonte.url_recentes()], [], {}
    try:
        while fila and len(vistas) < max_paginas:
            pagina = fila.pop(0)
            if pagina in vistas:
                continue
            vistas.append(pagina)
            resposta = rede.obter(pagina, politica)
            achados, proximas = fonte.extrair(rede.texto(resposta), resposta.url_final)
            for item in achados:
                itens.setdefault(item.url, item)
            # a paginação segue em ordem crescente de deslocamento (b_start)
            fila += sorted((p for p in proximas if p not in vistas and p not in fila), key=_deslocamento)
            time.sleep(politica.pausa)
    except rede.ErroRede as e:
        return {"fonte": fonte.sigla, "paginas_lidas": len(vistas), "erro": str(e)}
    novas = fora = 0
    for item in itens.values():
        if item.data is None or (inicio and item.data < inicio) or (fim and item.data > fim):
            fora += 1
            continue
        novas += banco.registrar_descoberta(item.fonte, item.url, item.data.isoformat(), item.tipo, item.ordem, item.rotulo)
    return {"fonte": fonte.sigla, "paginas_lidas": len(vistas), "listadas": len(itens), "novas": novas, "fora_do_periodo": fora}


def _deslocamento(url: str) -> int:
    achado = re.search(r"b_start(?::int)?=(\d+)", urllib.parse.unquote(url))
    return int(achado.group(1)) if achado else 0


class IntervaloInvalido(ValueError):
    pass


def validar_intervalo(inicio: date, fim: date, permitir_longo: bool = False, hoje: date | None = None) -> None:
    hoje = hoje or date.today()
    if inicio > fim:
        raise IntervaloInvalido(f"início {inicio} depois do fim {fim}")
    if fim > hoje:
        raise IntervaloInvalido(f"fim {fim} está no futuro")
    if inicio.year < 2025:
        raise IntervaloInvalido("período anterior a 2025 fora do escopo do Painel")
    if not permitir_longo and (fim - inicio).days + 1 > MAX_DIAS_INTERVALO:
        raise IntervaloInvalido(f"intervalo de {(fim - inicio).days + 1} dias excede {MAX_DIAS_INTERVALO}; "
                                "a carga histórica completa é da Etapa 06")


def coletar_intervalo(fontes, banco: B.Banco, acervo: Acervo, inicio: date, fim: date, politica: rede.Politica | None = None,
                      limite: int | None = None, simular: bool = False, usar_recentes: bool = True,
                      respeitar_robots: bool = True, reverificar: bool = False, transporte=None,
                      permitir_longo: bool = False, hoje: date | None = None) -> dict:
    """Descobre (listagens mensais + edições recentes) e baixa as publicações de um dia ou de um intervalo curto."""
    validar_intervalo(inicio, fim, permitir_longo, hoje)
    execucao = banco.iniciar_execucao(f"coletar-intervalo {inicio} {fim}{' simulado' if simular else ''}")
    resumo = {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "simulado": simular, "versao_coletor": VERSAO_COLETOR,
              "transporte": (transporte or Direto()).nome, "fontes": {}}
    for fonte in fontes:
        p = politica_da(fonte, politica)
        parte = {"robots": None, "recentes": None, "varreduras": [], "downloads": {}}
        resumo["fontes"][fonte.sigla] = parte
        situacao, regras = rede.consultar_robots(fonte.url_mes(inicio.year, inicio.month), p)
        parte["robots"] = situacao
        if regras is not None and not regras.can_fetch(p.agente, fonte.url_mes(inicio.year, inicio.month)):
            parte["robots"] = "RESTRINGE_A_COLETA"
            if respeitar_robots:
                continue
        if usar_recentes:
            parte["recentes"] = descobrir_recentes(fonte, banco, p, inicio=inicio, fim=fim)
        for ano, mes in meses(inicio, fim):
            parte["varreduras"].append(descobrir_mes(fonte, banco, p, ano, mes, inicio, fim))
        parte["downloads"] = baixar_pendentes(fonte, banco, acervo, p, limite, reverificar=reverificar,
                                              inicio=inicio, fim=fim, simular=simular, transporte=transporte)
    banco.concluir_execucao(execucao, resumo)
    return resumo


def coletar(fontes, banco: B.Banco, acervo: Acervo, inicio: date, fim: date, politica: rede.Politica | None = None,
            limite: int | None = None, respeitar_robots: bool = True, reverificar: bool = False) -> dict:
    execucao = banco.iniciar_execucao(f"coletar {inicio} {fim}")
    resumo = {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "fontes": {}}
    for fonte in fontes:
        p = politica_da(fonte, politica)
        parte = {"robots": None, "varreduras": [], "downloads": {}}
        resumo["fontes"][fonte.sigla] = parte
        situacao, regras = rede.consultar_robots(fonte.url_mes(inicio.year, inicio.month), p)
        parte["robots"] = situacao
        if regras is not None and not regras.can_fetch(p.agente, fonte.url_mes(inicio.year, inicio.month)):
            parte["robots"] = "RESTRINGE_A_COLETA"
            if respeitar_robots:
                continue
        for ano, mes in meses(inicio, fim):
            parte["varreduras"].append(descobrir_mes(fonte, banco, p, ano, mes, inicio, fim))
        parte["downloads"] = baixar_pendentes(fonte, banco, acervo, p, limite, reverificar=reverificar)
    banco.concluir_execucao(execucao, resumo)
    return resumo


def importar_manual(banco: B.Banco, acervo: Acervo, dados: bytes, data: date, url: str, rotulo: str) -> dict:
    """Registra um PDF obtido manualmente, com a mesma verificação da coleta automática."""
    laudo = pdf.examinar(dados)
    if not laudo.valido:
        return {"aceito": False, "motivo": laudo.motivo, "sha256": laudo.sha256}
    sha, gravou = acervo.guardar(dados)
    banco.registrar_descoberta("manual", url, data.isoformat(), "normal", 0, rotulo)
    resultado = banco.registrar_arquivo(banco.publicacao("manual", url)["id"], sha, laudo.tamanho, acervo.caminho_relativo(sha))
    return {"aceito": True, "sha256": sha, "arquivo_novo": gravou, "resultado": resultado}


def houve_pendencia(resumo: dict) -> bool:
    for parte in resumo["fontes"].values():
        if parte["robots"] in ("RESTRINGE_A_COLETA", "INACESSIVEL"):
            return True
        if any("erro" in v for v in parte["varreduras"]):
            return True
        if parte.get("recentes") and "erro" in parte["recentes"]:
            return True
        if any(parte["downloads"].get(k) for k in (B.FALHA_DOWNLOAD, B.INVALIDA, B.QUARENTENA, "ESGOTADA", "ADIADA")):
            return True
    return False
