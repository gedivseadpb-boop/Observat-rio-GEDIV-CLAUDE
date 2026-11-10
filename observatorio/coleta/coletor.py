"""Orquestração da coleta: descobrir, baixar, verificar, guardar e registrar.

Princípios:
- nada é presumido: uma listagem que não pôde ser lida é registrada como
  falha de varredura, nunca como "não houve publicação";
- reexecutar não duplica: o que já foi baixado e conferido é pulado;
- o PDF só entra no acervo depois de passar pela verificação estrutural;
- se um endereço passar a oferecer outro conteúdo, a versão anterior é mantida.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import date

from ..nucleo import banco as B
from ..nucleo import pdf, rede
from ..nucleo.acervo import Acervo

MAX_PAGINAS = 30


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
    novas = sem_data = 0
    for item in itens.values():
        if item.data is None:
            sem_data += 1
        elif (inicio and item.data < inicio) or (fim and item.data > fim):
            continue
        novas += banco.registrar_descoberta(item.fonte, item.url, item.data.isoformat() if item.data else None,
                                            item.tipo, item.ordem, item.rotulo)
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


def baixar_publicacao(fonte, banco: B.Banco, acervo: Acervo, politica: rede.Politica, linha) -> Desfecho:
    """Tenta os endereços de download da publicação e registra o desfecho."""
    erro, estado = "sem endereço de download", B.FALHA_DOWNLOAD
    for endereco in fonte.enderecos_download(linha["url"]):
        try:
            resposta = rede.obter(endereco, politica)
        except rede.ErroRede as e:
            if estado != B.INVALIDA:  # uma resposta inválida já recebida é a evidência mais informativa
                erro = str(e)
            continue
        finally:
            time.sleep(politica.pausa)
        laudo = pdf.examinar(resposta.corpo)
        if not laudo.valido:
            erro, estado = f"{laudo.motivo} em {endereco} ({laudo.tamanho} bytes)", B.INVALIDA
            continue
        sha, gravou = acervo.guardar(resposta.corpo)
        resultado = banco.registrar_arquivo(linha["id"], sha, laudo.tamanho, acervo.caminho_relativo(sha))
        if resultado == "NOVO" and not gravou:
            resultado = "DUPLICADO"
        return Desfecho(resultado, sha, laudo.tamanho)
    banco.registrar_falha(linha["id"], estado, erro)
    return Desfecho(estado, erro=erro)


def baixar_pendentes(fonte, banco: B.Banco, acervo: Acervo, politica: rede.Politica, limite: int | None = None,
                     max_tentativas: int = 5, reverificar: bool = False) -> dict:
    estados = (B.DESCOBERTA, B.FALHA_DOWNLOAD, B.INVALIDA) + ((B.BAIXADA,) if reverificar else ())
    contagem: dict[str, int] = {}
    feitas = 0
    for linha in banco.publicacoes(fonte.sigla, estados):
        if linha["estado"] != B.BAIXADA and linha["tentativas"] >= max_tentativas:
            contagem["ESGOTADA"] = contagem.get("ESGOTADA", 0) + 1
            continue
        if limite is not None and feitas >= limite:
            contagem["ADIADA"] = contagem.get("ADIADA", 0) + 1
            continue
        resultado = baixar_publicacao(fonte, banco, acervo, politica, linha).resultado
        contagem[resultado] = contagem.get(resultado, 0) + 1
        feitas += 1
    return contagem


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
        if any(parte["downloads"].get(k) for k in (B.FALHA_DOWNLOAD, B.INVALIDA, "ESGOTADA", "ADIADA")):
            return True
    return False
