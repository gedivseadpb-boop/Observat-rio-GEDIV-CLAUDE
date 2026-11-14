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

from datetime import datetime, timedelta, timezone

from ..nucleo import banco as B
from ..nucleo import pdf, rede
from ..nucleo.acervo import Acervo, ErroAcervo
from . import fontes as F
from .transporte import Direto

MAX_PAGINAS = 30
VERSAO_COLETOR = "coletor-etapa05.3.2-2026.11.14"
MAX_DIAS_INTERVALO = 31  # amostras controladas; a carga histórica completa é da Etapa 06
ESPERA_APOS_429 = 3600        # s: sem Retry-After, uma limitação temporária suspende a fonte por 1 h
ESPERA_APOS_RECUSA = 24 * 3600  # s: 403, robots.txt ou bloqueio reconhecido; antes disso, só liberação auditada


class Guarda:
    """Política de suspensão de UMA fonte, comum a todos os caminhos de coleta (dia, intervalo, lote, descoberta).

    Diante de recusa (HTTP 403/429), proibição ou recusa do robots.txt ou página de bloqueio reconhecida, nenhuma nova
    requisição é feita à fonte nesta execução; a suspensão é registrada na trilha de auditoria com prazo (Retry-After
    quando informado) e vale também para as execuções seguintes até vencer ou ser liberada por uma pessoa
    (`operacao liberar-fonte`). Nada é contornado: sem troca de identidade, proxies ou endereços alternativos.
    """

    def __init__(self, banco: B.Banco, sigla: str):
        self.banco, self.sigla = banco, sigla
        self.requisicoes_evitadas = 0
        vigente = banco.suspensao_vigente(sigla)
        self.motivo = f"{vigente['categoria']} (suspensa desde {vigente['desde']} até {vigente['ate']})" if vigente else None

    @property
    def suspensa(self) -> bool:
        return self.motivo is not None

    def antes_de_requisitar(self) -> None:
        if self.suspensa:
            self.requisicoes_evitadas += 1
            raise rede.ErroRede("FONTE_SUSPENSA", self.motivo)

    def suspender(self, categoria: str, detalhe: str, retry_after: float | None = None) -> None:
        if self.suspensa:
            return
        espera = (max(retry_after or 0.0, ESPERA_APOS_429 if retry_after is None else 0.0) if categoria == "HTTP_429"
                  else max(retry_after or 0.0, ESPERA_APOS_RECUSA))
        ate = (datetime.now(timezone.utc) + timedelta(seconds=espera)).isoformat(timespec="seconds")
        self.banco.suspender_fonte(self.sigla, categoria, detalhe, ate)
        self.motivo = f"{categoria} (suspensa até {ate})"

    def observar(self, erro: rede.ErroRede) -> None:
        if erro.recusa:
            self.suspender(erro.categoria, str(erro), erro.retry_after)

    def obter(self, url: str, politica: rede.Politica) -> rede.Resposta:
        self.antes_de_requisitar()
        try:
            return rede.obter(url, politica)
        except rede.ErroRede as e:
            self.observar(e)
            raise

    def robots(self, url: str, politica: rede.Politica) -> tuple[str, object]:
        """Consulta o robots.txt pela guarda. Proibição ou recusa (4xx exceto 404/410) suspendem a fonte."""
        if self.suspensa:
            self.requisicoes_evitadas += 1
            return "FONTE_SUSPENSA", None
        situacao, regras = rede.consultar_robots(url, politica)
        if situacao == "RECUSADO":
            self.suspender("ROBOTS_RECUSADO", f"consulta ao robots.txt recusada pela fonte ({url})")
        elif regras is not None and not regras.can_fetch(politica.agente, url):
            situacao = "RESTRINGE_A_COLETA"
            self.suspender("ROBOTS_RESTRINGE", f"robots.txt não permite {url}")
        return situacao, regras


def meses(inicio: date, fim: date):
    ano, mes = inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        yield ano, mes
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def politica_da(fonte, base: rede.Politica | None = None) -> rede.Politica:
    base = base or rede.Politica(servidores=frozenset())
    return replace(base, servidores=frozenset(fonte.servidores) | base.servidores)


def descobrir_mes(fonte, banco: B.Banco, politica: rede.Politica, ano: int, mes: int,
                  inicio: date | None = None, fim: date | None = None, guarda: Guarda | None = None) -> dict:
    """Lê a listagem mensal (com paginação), valida o CONTEÚDO de cada página e registra as publicações encontradas.

    O mês só é gravado como varrido (o que permite à cobertura afirmar "sem publicação") se todas as páginas foram
    lidas, reconhecidas como listagem e todas as edições tiveram data identificada. Página de manutenção, bloqueio,
    erro, formato desconhecido ou sem itens sem mensagem explícita de pasta vazia: falha de descoberta registrada."""
    guarda = guarda or Guarda(banco, fonte.sigla)
    fila, vistas, itens = [fonte.url_mes(ano, mes)], set(), {}
    try:
        while fila and len(vistas) < MAX_PAGINAS:
            pagina = fila.pop(0)
            if pagina in vistas:
                continue
            vistas.add(pagina)
            resposta = guarda.obter(pagina, politica)
            html = rede.texto(resposta)
            achados, proximas = fonte.extrair(html, resposta.url_final)
            conteudo = F.classificar_listagem(html, achados)
            if conteudo == F.BLOQUEIO:
                guarda.suspender("BLOQUEIO_RECONHECIDO", f"página de bloqueio no lugar da listagem {pagina}")
            # Página sem itens só é aceita com mensagem EXPLÍCITA de pasta vazia (VAZIA_COMPROVADA), inclusive numa
            # página seguinte da paginação: ausência de links nunca é tomada como ausência de publicação.
            if conteudo not in (F.VALIDA, F.VAZIA_COMPROVADA):
                raise rede.ErroRede("LISTAGEM_INVALIDA", f"{conteudo} em {pagina}")
            for item in achados:
                itens.setdefault(item.url, item)
            fila += [p for p in proximas if p not in vistas]
            time.sleep(politica.pausa)
    except rede.ErroRede as e:
        banco.registrar_varredura(fonte.sigla, ano, mes, None, str(e))
        return {"fonte": fonte.sigla, "ano": ano, "mes": mes, "erro": str(e)}
    parcial = bool([p for p in fila if p not in vistas])
    novas = sem_data = 0
    # Todas as edições DO MÊS lido são registradas, mesmo fora do período pedido: a varredura do mês é gravada como
    # completa, e a cobertura só pode afirmar "sem publicação" num dia se tudo o que a listagem mostrou para o mês
    # estiver no banco (achado real de 14/11/2026: após coletar-dia 07/11, os dias 04–06/11 apareciam como
    # SEM_PUBLICACAO_LISTADA). O período restringe os DOWNLOADS (baixar_pendentes). Edições de OUTROS meses que
    # apareçam na listagem continuam fora, salvo se estiverem no período pedido.
    for item in itens.values():
        if item.data is None:
            sem_data += 1
        elif (item.data.year, item.data.month) != (ano, mes) and ((inicio and item.data < inicio) or (fim and item.data > fim)):
            continue
        novas += banco.registrar_descoberta(item.fonte, item.url, item.data.isoformat() if item.data else None,
                                            item.tipo, item.ordem, item.rotulo)
    if parcial:
        # Restaram páginas da listagem além do limite: o mês NÃO é dado como varrido e será relido.
        erro = f"LISTAGEM_PARCIAL: limite de {MAX_PAGINAS} páginas atingido com páginas ainda por ler"
        banco.registrar_varredura(fonte.sigla, ano, mes, len(itens), erro)
        return {"fonte": fonte.sigla, "ano": ano, "mes": mes, "listadas": len(itens), "novas": novas, "sem_data": sem_data,
                "erro": erro}
    if sem_data:
        # Edição listada sem data identificável: fica registrada (rastreável, sem data inventada) e o mês não pode
        # ser certificado — ela pode pertencer a qualquer dia.
        erro = f"DATA_NAO_IDENTIFICADA: {sem_data} edição(ões) da listagem sem data no endereço"
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


def descobrir(fonte, banco: B.Banco, politica: rede.Politica, inicio: date, fim: date, refazer: bool = False,
              guarda: Guarda | None = None) -> list[dict]:
    """Varre mês a mês. Meses já lidos com sucesso são pulados, exceto os dois últimos do
    período, que podem ter recebido novas edições. Meses com falha são sempre refeitos."""
    guarda = guarda or Guarda(banco, fonte.sigla)
    lidos = {(v["ano"], v["mes"]) for v in banco.varreduras() if v["fonte"] == fonte.sigla and v["erro"] is None}
    periodo = list(meses(inicio, fim))
    resultados = []
    for ano, mes in periodo:
        if not refazer and (ano, mes) in lidos and (ano, mes) not in periodo[-2:]:
            resultados.append({"fonte": fonte.sigla, "ano": ano, "mes": mes, "pulado": "já varrido"})
            continue
        if guarda.suspensa:
            resultados.append({"fonte": fonte.sigla, "ano": ano, "mes": mes, "erro": f"FONTE_SUSPENSA: {guarda.motivo}"})
            continue
        resultados.append(descobrir_mes(fonte, banco, politica, ano, mes, inicio, fim, guarda))
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


def _campos_download(endereco: str, transporte, inicio: str, resposta, laudo, segundos) -> dict:
    return dict(url_pedida=endereco, transporte=transporte.nome, url_final=resposta.url_final,
                redirecionamentos=json.dumps(resposta.redirecionamentos) if resposta.redirecionamentos else None,
                status_http=resposta.status, tipo_conteudo=resposta.tipo_conteudo, content_length=resposta.content_length,
                alertas=json.dumps(list(laudo.alertas)) if laudo.alertas else None, versao_coletor=VERSAO_COLETOR,
                iniciado_em=inicio, segundos=segundos, tentativas_rede=resposta.tentativas)


def baixar_publicacao(fonte, banco: B.Banco, acervo: Acervo, politica: rede.Politica, linha, transporte=None,
                      guarda: Guarda | None = None) -> Desfecho:
    """Tenta os endereços de download da publicação, verifica a estrutura do PDF e registra cada tentativa no manifesto.

    Ordem segura: bytes recebidos → verificação estrutural completa → gravação atômica no acervo (arquivo temporário +
    substituição) → UMA transação no banco com arquivo, versão, verificação, manifesto e estado BAIXADA. Uma queda
    em qualquer ponto deixa a publicação pendente (nunca falsamente baixada) e um arquivo válido nunca é apagado.

    Prioridade do desfecho quando nenhum endereço dá certo: QUARENTENA > INVALIDA > FALHA_DOWNLOAD.
    """
    transporte = transporte or Direto()
    guarda = guarda or Guarda(banco, fonte.sigla)
    erro, estado = "sem endereço de download", B.FALHA_DOWNLOAD
    for endereco in fonte.enderecos_download(linha["url"]):
        inicio, relogio = B.agora(), time.monotonic()
        try:
            guarda.antes_de_requisitar()
            resposta = transporte.obter(endereco, politica)
        except rede.ErroRede as e:
            if e.categoria == "FONTE_SUSPENSA":
                # Nenhuma requisição foi feita: não conta como tentativa da publicação.
                return Desfecho("SUSPENSA", erro=str(e))
            guarda.observar(e)
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
            if laudo.motivo == "RECEBIDO_HTML_EM_VEZ_DE_PDF" and F.e_pagina_de_bloqueio(resposta.corpo):
                guarda.suspender("BLOQUEIO_RECONHECIDO", f"página de bloqueio no lugar do PDF em {endereco}")
            if laudo.quarentena:
                acervo.guardar_quarentena(resposta.corpo)
                _registrar(banco, linha, endereco, transporte, inicio, resposta, laudo, B.QUARENTENA, laudo.motivo, segundos)
                erro, estado = f"{laudo.motivo} em {endereco} ({laudo.tamanho} bytes)", B.QUARENTENA
            else:
                _registrar(banco, linha, endereco, transporte, inicio, resposta, laudo, "REPROVADO", laudo.motivo, segundos)
                if estado not in (B.QUARENTENA, B.INVALIDA) or (estado == B.INVALIDA and laudo.truncado):
                    erro = f"{laudo.motivo} em {endereco} ({laudo.tamanho} bytes)"
                    estado = B.FALHA_DOWNLOAD if laudo.truncado else B.INVALIDA
            if guarda.suspensa:
                break
            continue        # o endereço "/view" devolve HTML legitimamente; o de download é tentado em seguida
        try:
            sha, _ = acervo.guardar(resposta.corpo)
        except (ErroAcervo, OSError) as e:
            # Falha ao gravar no acervo (disco, permissão, arquivo existente corrompido): registrada, nunca escondida.
            _registrar(banco, linha, endereco, transporte, inicio, resposta, laudo, "FALHA_ACERVO", type(e).__name__, segundos)
            erro, estado = f"FALHA_ACERVO: {type(e).__name__}", B.FALHA_DOWNLOAD
            break
        resultado = banco.registrar_obtencao(linha["id"], sha, laudo.tamanho, acervo.caminho_relativo(sha), laudo.paginas,
                                             laudo.integridade, **_campos_download(endereco, transporte, inicio, resposta,
                                                                                   laudo, segundos))
        return Desfecho(resultado, sha, laudo.tamanho)
    banco.registrar_falha(linha["id"], estado, erro)
    return Desfecho(estado, erro=erro)


def baixar_pendentes(fonte, banco: B.Banco, acervo: Acervo, politica: rede.Politica, limite: int | None = None,
                     max_tentativas: int = B.MAX_TENTATIVAS, reverificar: bool = False, inicio: date | None = None,
                     fim: date | None = None, simular: bool = False, transporte=None, guarda: Guarda | None = None) -> dict:
    """Baixa o que está pendente. Com ``simular=True`` apenas lista o que seria baixado, sem acessar a rede.

    Publicações já BAIXADAS só são consultadas de novo com ``reverificar=True`` (verificação deliberada de mudança).
    QUARENTENA também só volta com ``reverificar``: o arquivo retido precisa de diagnóstico, não de insistência.
    """
    guarda = guarda or Guarda(banco, fonte.sigla)
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
            # Não some: fica contada aqui, visível na cobertura (TENTATIVAS_ESGOTADAS) e volta por reabertura auditada.
            contagem["ESGOTADA"] = contagem.get("ESGOTADA", 0) + 1
            continue
        if guarda.suspensa and not simular:
            contagem["SUSPENSA"] = contagem.get("SUSPENSA", 0) + 1
            continue
        if limite is not None and feitas >= limite:
            contagem["ADIADA"] = contagem.get("ADIADA", 0) + 1
            continue
        feitas += 1
        if simular:
            previstas.append({"url": linha["url"], "data": data_pub, "estado": linha["estado"]})
            contagem["SIMULADA"] = contagem.get("SIMULADA", 0) + 1
            continue
        resultado = baixar_publicacao(fonte, banco, acervo, politica, linha, transporte, guarda).resultado
        contagem[resultado] = contagem.get(resultado, 0) + 1
    if simular:
        contagem["previstas"] = previstas
    return contagem


def descobrir_recentes(fonte, banco: B.Banco, politica: rede.Politica, max_paginas: int = 2,
                       inicio: date | None = None, fim: date | None = None, guarda: Guarda | None = None) -> dict:
    """Lê a listagem "Edições recentes" (quando a fonte a oferece) e registra as publicações do período.

    Não marca nenhum mês como varrido: a listagem recente mostra só as últimas edições e não prova ausência.
    """
    if not hasattr(fonte, "url_recentes"):
        return {"fonte": fonte.sigla, "recentes": "NAO_OFERECIDA"}
    guarda = guarda or Guarda(banco, fonte.sigla)
    fila, vistas, itens = [fonte.url_recentes()], [], {}
    try:
        while fila and len(vistas) < max_paginas:
            pagina = fila.pop(0)
            if pagina in vistas:
                continue
            vistas.append(pagina)
            resposta = guarda.obter(pagina, politica)
            html = rede.texto(resposta)
            achados, proximas = fonte.extrair(html, resposta.url_final)
            if not achados and F.classificar_listagem(html, achados) == F.BLOQUEIO:
                guarda.suspender("BLOQUEIO_RECONHECIDO", f"página de bloqueio no lugar da listagem {pagina}")
                raise rede.ErroRede("LISTAGEM_INVALIDA", f"{F.BLOQUEIO} em {pagina}")
            for item in achados:
                itens.setdefault(item.url, item)
            # a paginação segue em ordem crescente de deslocamento (b_start)
            fila += sorted((p for p in proximas if p not in vistas and p not in fila), key=_deslocamento)
            time.sleep(politica.pausa)
    except rede.ErroRede as e:
        return {"fonte": fonte.sigla, "paginas_lidas": len(vistas), "erro": str(e)}
    novas = fora = sem_data = 0
    for item in itens.values():
        if item.data is None:
            # Rastreável, sem data inventada: registrada e apontada na cobertura como pendência de resolução.
            sem_data += 1
            novas += banco.registrar_descoberta(item.fonte, item.url, None, item.tipo, item.ordem, item.rotulo)
            continue
        if (inicio and item.data < inicio) or (fim and item.data > fim):
            fora += 1
            continue
        novas += banco.registrar_descoberta(item.fonte, item.url, item.data.isoformat(), item.tipo, item.ordem, item.rotulo)
    return {"fonte": fonte.sigla, "paginas_lidas": len(vistas), "listadas": len(itens), "novas": novas, "fora_do_periodo": fora,
            "sem_data": sem_data}


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


def reconciliar(banco: B.Banco, acervo: Acervo) -> dict:
    """Recuperação após interrupção, executada no início de toda coleta (sem acesso à rede).

    - publicação BAIXADA cujo arquivo falta no acervo, tem tamanho diferente ou não tem registro: volta à fila
      (FALHA_DOWNLOAD, motivo registrado na trilha), sem perder o histórico de versões;
    - arquivo presente, mas sem verificação estrutural registrada (queda entre gravações, importação antiga): é
      verificado agora a partir do acervo; se não confirmar a estrutura, a publicação volta à fila;
    - arquivos temporários ``*.parcial`` deixados por uma queda durante a gravação são removidos (nunca são válidos);
    - arquivos do acervo sem registro no banco (queda entre a gravação e a transação) são apenas contados: o próximo
      download do mesmo conteúdo os associa, e nada é apagado.
    """
    resumo = {"reobter": 0, "verificados_agora": 0, "parciais_removidos": 0, "arquivos_sem_registro": 0}
    arquivos = {a["sha256"]: a for a in banco.arquivos()}
    verificados = {v["sha256"] for v in banco.con.execute("SELECT sha256 FROM verificacao_arquivo")}
    for p in banco.publicacoes(estados=(B.BAIXADA,)):
        sha = p["sha256"]
        caminho = acervo.caminho(sha) if sha else None
        registro = arquivos.get(sha) if sha else None
        if registro is None or caminho is None or not caminho.is_file() or caminho.stat().st_size != registro["tamanho"]:
            banco.marcar_para_reobter(p["id"], "ARQUIVO_AUSENTE_NO_ACERVO" if registro else "ARQUIVO_SEM_REGISTRO")
            resumo["reobter"] += 1
            continue
        if sha not in verificados:
            laudo = pdf.verificar(caminho.read_bytes(), registro["tamanho"])
            if laudo.valido and laudo.sha256 == sha:
                banco.registrar_verificacao(sha, laudo.paginas, laudo.integridade)
                verificados.add(sha)
                resumo["verificados_agora"] += 1
            else:
                banco.marcar_para_reobter(p["id"], f"VERIFICACAO_ESTRUTURAL_REPROVADA ({laudo.motivo or 'SHA_DIVERGENTE'})")
                resumo["reobter"] += 1
    for parcial in acervo.raiz.rglob("*.parcial"):
        parcial.unlink(missing_ok=True)
        resumo["parciais_removidos"] += 1
    resumo["arquivos_sem_registro"] = sum(1 for f in acervo.raiz.rglob("*.pdf") if f.stem not in arquivos)
    return resumo


def reabrir_esgotadas(banco: B.Banco, fonte: str, inicio: date, fim: date, autor: str, justificativa: str) -> dict:
    """Reabertura auditada das publicações do período com tentativas esgotadas (uma pessoa decide e justifica)."""
    alvo = [p for p in banco.esgotadas(fonte)
            if p["data_publicacao"] is None or inicio.isoformat() <= p["data_publicacao"] <= fim.isoformat()]
    reabertas = banco.reabrir_publicacoes([p["id"] for p in alvo], autor, justificativa)
    return {"fonte": fonte, "esgotadas": len(alvo), "reabertas": reabertas,
            "itens": [{"url": p["url"], "data": p["data_publicacao"], "ultimo_erro": p["ultimo_erro"],
                       "ultima_tentativa_em": p["atualizada_em"]} for p in alvo]}


def _coletar_fonte(fonte, banco: B.Banco, acervo: Acervo, inicio: date, fim: date, politica, limite, simular,
                   usar_recentes, respeitar_robots, reverificar, transporte) -> dict:
    p = politica_da(fonte, politica)
    guarda = Guarda(banco, fonte.sigla)
    parte = {"robots": None, "recentes": None, "varreduras": [], "downloads": {}, "suspensa": None}
    if guarda.suspensa:
        # Suspensão anterior ainda em vigor (Retry-After, 403, robots, bloqueio): nenhuma requisição nesta execução.
        parte["robots"] = "FONTE_SUSPENSA"
        parte["suspensa"] = guarda.motivo
        return parte
    if respeitar_robots:
        situacao, _ = guarda.robots(fonte.url_mes(inicio.year, inicio.month), p)
    else:                       # só para testes: informa a situação sem suspender a fonte
        situacao, regras = rede.consultar_robots(fonte.url_mes(inicio.year, inicio.month), p)
        if regras is not None and not regras.can_fetch(p.agente, fonte.url_mes(inicio.year, inicio.month)):
            situacao = "RESTRINGE_A_COLETA"
    parte["robots"] = situacao
    if guarda.suspensa:
        parte["suspensa"] = guarda.motivo
        return parte
    if usar_recentes:
        parte["recentes"] = descobrir_recentes(fonte, banco, p, inicio=inicio, fim=fim, guarda=guarda)
    for ano, mes in meses(inicio, fim):
        if guarda.suspensa:
            parte["varreduras"].append({"fonte": fonte.sigla, "ano": ano, "mes": mes, "erro": f"FONTE_SUSPENSA: {guarda.motivo}"})
            continue
        parte["varreduras"].append(descobrir_mes(fonte, banco, p, ano, mes, inicio, fim, guarda))
    parte["downloads"] = baixar_pendentes(fonte, banco, acervo, p, limite, reverificar=reverificar, inicio=inicio, fim=fim,
                                          simular=simular, transporte=transporte, guarda=guarda)
    parte["suspensa"] = guarda.motivo
    parte["requisicoes_evitadas_por_suspensao"] = guarda.requisicoes_evitadas
    return parte


def coletar_intervalo(fontes, banco: B.Banco, acervo: Acervo, inicio: date, fim: date, politica: rede.Politica | None = None,
                      limite: int | None = None, simular: bool = False, usar_recentes: bool = True,
                      respeitar_robots: bool = True, reverificar: bool = False, transporte=None,
                      permitir_longo: bool = False, hoje: date | None = None) -> dict:
    """Descobre (listagens mensais + edições recentes) e baixa as publicações de um dia ou de um intervalo curto."""
    validar_intervalo(inicio, fim, permitir_longo, hoje)
    execucao = banco.iniciar_execucao(f"coletar-intervalo {inicio} {fim}{' simulado' if simular else ''}")
    resumo = {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "simulado": simular, "versao_coletor": VERSAO_COLETOR,
              "transporte": (transporte or Direto()).nome, "fontes_consultadas": [f.sigla for f in fontes],
              "reconciliacao": None if simular else reconciliar(banco, acervo), "fontes": {}}
    for fonte in fontes:
        resumo["fontes"][fonte.sigla] = _coletar_fonte(fonte, banco, acervo, inicio, fim, politica, limite, simular,
                                                       usar_recentes, respeitar_robots, reverificar, transporte)
    banco.concluir_execucao(execucao, resumo)
    return resumo


def coletar(fontes, banco: B.Banco, acervo: Acervo, inicio: date, fim: date, politica: rede.Politica | None = None,
            limite: int | None = None, respeitar_robots: bool = True, reverificar: bool = False) -> dict:
    """Caminho da Etapa 1 (sem listagem de edições recentes). Mesma guarda, reconciliação e validação do intervalo."""
    execucao = banco.iniciar_execucao(f"coletar {inicio} {fim}")
    resumo = {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "fontes_consultadas": [f.sigla for f in fontes],
              "reconciliacao": reconciliar(banco, acervo), "fontes": {}}
    for fonte in fontes:
        parte = _coletar_fonte(fonte, banco, acervo, inicio, fim, politica, limite, False, False, respeitar_robots,
                               reverificar, None)
        parte.pop("recentes", None)
        resumo["fontes"][fonte.sigla] = parte
    banco.concluir_execucao(execucao, resumo)
    return resumo


def importar_manual(banco: B.Banco, acervo: Acervo, dados: bytes, data: date, url: str, rotulo: str) -> dict:
    """Registra um PDF obtido manualmente, com a MESMA verificação estrutural da coleta automática (antes: só a
    verificação mínima, que aceitava PDF sem páginas). A procedência fica registrada no manifesto como importação manual.
    Estrutura não confirmada vai para a quarentena; nada inválido entra no acervo."""
    laudo = pdf.verificar(dados, len(dados))
    if not laudo.valido:
        if laudo.quarentena:
            acervo.guardar_quarentena(dados)
        return {"aceito": False, "motivo": laudo.motivo, "sha256": laudo.sha256, "quarentena": laudo.quarentena}
    sha, gravou = acervo.guardar(dados)
    banco.registrar_descoberta("manual", url, data.isoformat(), "normal", 0, rotulo)
    inicio = B.agora()
    resultado = banco.registrar_obtencao(
        banco.publicacao("manual", url)["id"], sha, laudo.tamanho, acervo.caminho_relativo(sha), laudo.paginas,
        laudo.integridade, url_pedida=url, transporte="importacao_manual", content_length=len(dados),
        alertas=json.dumps(list(laudo.alertas)) if laudo.alertas else None, versao_coletor=VERSAO_COLETOR, iniciado_em=inicio)
    return {"aceito": True, "sha256": sha, "arquivo_novo": gravou, "resultado": resultado, "paginas": laudo.paginas}


def houve_pendencia(resumo: dict) -> bool:
    if (resumo.get("reconciliacao") or {}).get("reobter"):
        return True
    for parte in resumo["fontes"].values():
        if parte.get("suspensa") or parte["robots"] in ("RESTRINGE_A_COLETA", "INACESSIVEL", "RECUSADO", "FONTE_SUSPENSA"):
            return True
        if any("erro" in v for v in parte["varreduras"]):
            return True
        if parte.get("recentes") and ("erro" in parte["recentes"] or parte["recentes"].get("sem_data")):
            return True
        if any(parte["downloads"].get(k) for k in (B.FALHA_DOWNLOAD, B.INVALIDA, B.QUARENTENA, "ESGOTADA", "ADIADA", "SUSPENSA")):
            return True
    return False
