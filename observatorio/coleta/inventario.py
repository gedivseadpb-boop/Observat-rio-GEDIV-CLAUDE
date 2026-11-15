"""Inventário da cobertura: o que foi listado, baixado e o que falta, dia a dia.

Um dia só recebe COMPLETO ou SEM_PUBLICACAO_LISTADA com EVIDÊNCIA suficiente e atual (Etapa 05.3.2):

- a listagem do mês foi lida com sucesso em TODAS as fontes consideradas: todas as páginas percorridas, o conteúdo
  reconhecido como listagem (não manutenção, bloqueio, erro ou formato desconhecido) e toda edição com data;
- essa leitura aconteceu DEPOIS do dia e passada a janela de suplementos (``JANELA_SUPLEMENTOS`` dias): uma varredura
  do mês corrente não certifica os dias posteriores a ela, nem os recentes que ainda podem receber suplemento ou
  edição extra. Dias assim ficam NAO_VERIFICADO (sem edição listada) ou BAIXADO_SEM_VARREDURA_COMPLETA, com motivo;
- para COMPLETO, cada edição listada do dia está BAIXADA, com arquivo registrado, verificação estrutural aceita e o
  arquivo PRESENTE no acervo com o tamanho e o SHA-256 registrados.

Estados de um dia:
- COMPLETO; SEM_PUBLICACAO_LISTADA (dia sem edição, comprovado);
- PENDENTE: há edição listada, nenhuma baixada (``motivo`` TENTATIVAS_ESGOTADAS quando for o caso);
- PARCIAL: parte das edições do dia baixada (principal sem suplemento, por exemplo);
- QUARENTENA: algum arquivo do dia foi retido por estrutura não confirmada;
- INTEGRIDADE_NAO_CONFIRMADA: tudo baixado, mas falta prova de algum arquivo (ausente do acervo, sem verificação);
- NAO_VERIFICADO: não se sabe se houve edição; ``motivo`` diz por quê;
- BAIXADO_SEM_VARREDURA_COMPLETA: há arquivo íntegro, mas sem a varredura que permitiria afirmar que não falta outro.

Motivos de evidência insuficiente: NUNCA_LIDA, FONTE_INDISPONIVEL, LISTAGEM_PARCIAL, LISTAGEM_INVALIDA,
DATA_NAO_IDENTIFICADA, FONTE_SUSPENSA, VARREDURA_ANTERIOR_AO_DIA, AGUARDANDO_JANELA_DE_SUPLEMENTOS.

A cobertura vale para as fontes CONSIDERADAS, que todo relatório declara; cobertura de uma fonte não é geral.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from ..nucleo import banco as B
from ..nucleo.acervo import Acervo
from .fontes import CONFIGURADAS

JANELA_SUPLEMENTOS = 3   # dias após a data em que ainda pode surgir suplemento ou edição extra


def acervo_da_base(banco: B.Banco) -> Acervo | None:
    """O acervo fica, por convenção, na pasta ``acervo`` ao lado do banco (mesma regra de todos os comandos)."""
    if str(banco.caminho) == ":memory:":
        return None
    pasta = Path(banco.caminho).parent / "acervo"
    return Acervo(pasta) if pasta.is_dir() else None


def _motivo_do_erro(erro: str) -> str:
    for prefixo in ("LISTAGEM_PARCIAL", "LISTAGEM_INVALIDA", "DATA_NAO_IDENTIFICADA", "FONTE_SUSPENSA"):
        if erro.startswith(prefixo):
            return prefixo
    return "FONTE_INDISPONIVEL"


def evidencia_da_fonte(varredura, dia: date, janela: int = JANELA_SUPLEMENTOS) -> str | None:
    """None quando a varredura da fonte certifica o dia; senão, o motivo."""
    if varredura is None:
        return "NUNCA_LIDA"
    if varredura["erro"] is not None:
        return _motivo_do_erro(varredura["erro"])
    lida_em = date.fromisoformat(varredura["realizada_em"][:10])
    if lida_em <= dia:
        return "VARREDURA_ANTERIOR_AO_DIA"
    if lida_em < dia + timedelta(days=janela):
        return "AGUARDANDO_JANELA_DE_SUPLEMENTOS"
    return None


def cobertura(banco: B.Banco, inicio: date, fim: date, fontes: list[str], acervo: Acervo | None = None,
              janela: int = JANELA_SUPLEMENTOS) -> list[dict]:
    fontes = list(fontes)
    acervo = acervo or acervo_da_base(banco)
    varreduras = {(v["fonte"], v["ano"], v["mes"]): v for v in banco.varreduras()}
    arquivos = {a["sha256"]: a for a in banco.arquivos()}
    verificacoes = {v["sha256"]: v["integridade"] for v in banco.con.execute("SELECT sha256, integridade FROM verificacao_arquivo")}
    presenca: dict[str, str | None] = {}

    def prova(p) -> str | None:
        """None se a edição BAIXADA tem prova completa; senão, o que falta."""
        sha = p["sha256"]
        if not sha or sha not in arquivos:
            return "ARQUIVO_SEM_REGISTRO"
        if verificacoes.get(sha) not in B.INTEGRIDADES_ACEITAS:
            return "SEM_VERIFICACAO_ESTRUTURAL"
        if sha not in presenca:
            caminho = acervo.caminho(sha) if acervo else None
            try:
                if acervo is None:
                    presenca[sha] = "ACERVO_NAO_LOCALIZADO"
                elif not caminho.is_file() or caminho.stat().st_size != arquivos[sha]["tamanho"]:
                    presenca[sha] = "ARQUIVO_AUSENTE_NO_ACERVO"
                else:
                    presenca[sha] = None if acervo.conferir(sha) else "SHA_DIVERGENTE"
            except OSError:
                presenca[sha] = "ACERVO_NAO_PODE_SER_VERIFICADO"
        return presenca[sha]

    por_dia: dict[str, list] = {}
    for p in banco.publicacoes():
        if p["data_publicacao"]:
            por_dia.setdefault(p["data_publicacao"], []).append(p)
    linhas, dia = [], inicio
    while dia <= fim:
        pubs = por_dia.get(dia.isoformat(), [])
        baixadas = [p for p in pubs if p["estado"] == B.BAIXADA]
        esgotadas = [p for p in pubs if p["estado"] in B.PENDENTES and p["tentativas"] >= B.MAX_TENTATIVAS]
        evidencias = {f: evidencia_da_fonte(varreduras.get((f, dia.year, dia.month)), dia, janela) for f in fontes}
        verificado = bool(fontes) and all(e is None for e in evidencias.values())
        sem_evidencia = next((e for e in evidencias.values() if e), None) if fontes else "NENHUMA_FONTE_CONSIDERADA"
        faltas = [m for m in (prova(p) for p in baixadas) if m]
        motivo = None
        if not pubs:
            situacao = "SEM_PUBLICACAO_LISTADA" if verificado else "NAO_VERIFICADO"
            motivo = None if verificado else sem_evidencia
        elif any(p["estado"] == B.QUARENTENA for p in pubs):
            situacao = "QUARENTENA"
        elif len(baixadas) == len(pubs):
            if faltas:
                situacao, motivo = "INTEGRIDADE_NAO_CONFIRMADA", faltas[0]
            elif verificado:
                situacao = "COMPLETO"
            else:
                situacao, motivo = "BAIXADO_SEM_VARREDURA_COMPLETA", sem_evidencia
        else:
            situacao = "PARCIAL" if baixadas else "PENDENTE"
            motivo = "TENTATIVAS_ESGOTADAS" if esgotadas else None
        fontes_do_dia = sorted({p["fonte"] for p in pubs})
        linhas.append({
            "data": dia.isoformat(),
            "dia_util": dia.weekday() < 5,
            "situacao": situacao,
            "motivo": motivo,
            "listadas": len(pubs),
            "baixadas": len(baixadas),
            "esgotadas": len(esgotadas),
            "arquivos_distintos": len({p["sha256"] for p in baixadas}),
            "suplementos_ou_extras": sum(p["tipo"] != "normal" or p["ordem"] > 0 for p in pubs),
            "fontes": fontes_do_dia,
            "fontes_verificadas": sorted(f for f, e in evidencias.items() if e is None),
            "fontes_sem_evidencia": {f: e for f, e in evidencias.items() if e},
            "so_em_uma_fonte": verificado and len(fontes) > 1 and len(fontes_do_dia) == 1 and fontes_do_dia[0] in fontes,
        })
        dia += timedelta(days=1)
    return linhas


def escopo(fontes: list[str], janela: int = JANELA_SUPLEMENTOS) -> dict:
    consideradas = sorted(set(fontes))
    return {"fontes_consideradas": consideradas, "fontes_configuradas": list(CONFIGURADAS),
            "todas_as_fontes": set(CONFIGURADAS) <= set(consideradas),
            "fontes_nao_consideradas": sorted(set(CONFIGURADAS) - set(consideradas)),
            "janela_de_suplementos_dias": janela,
            "aviso": None if set(CONFIGURADAS) <= set(consideradas) else
            "cobertura medida apenas nas fontes consideradas; não é a cobertura de todas as fontes configuradas"}


def totais(linhas: list[dict]) -> dict:
    resultado: dict[str, int] = {}
    for linha in linhas:
        resultado[linha["situacao"]] = resultado.get(linha["situacao"], 0) + 1
    resultado["dias"] = len(linhas)
    resultado["divergencias_entre_fontes"] = sum(linha["so_em_uma_fonte"] for linha in linhas)
    return resultado


def parecer(linhas: list[dict], fontes: dict[str, dict]) -> dict:
    """Parecer sobre a cobertura. Nunca declara o acervo completo: no máximo, sem lacunas conhecidas."""
    t = totais(linhas)
    lacunas = {k: t.get(k, 0) for k in ("NAO_VERIFICADO", "PENDENTE", "PARCIAL", "QUARENTENA",
                                        "BAIXADO_SEM_VARREDURA_COMPLETA", "INTEGRIDADE_NAO_CONFIRMADA")}
    nao_validadas = sorted(s for s, f in fontes.items() if f["situacao"] != "VALIDADA")
    if not any(f["situacao"] == "VALIDADA" for f in fontes.values()) and not (t.get("COMPLETO") or t.get("BAIXADO_SEM_VARREDURA_COMPLETA")):
        situacao = "SEM_COBERTURA_AUTOMATICA"
    elif nao_validadas or any(lacunas.values()):
        situacao = "PARCIAL"
    else:
        situacao = "SEM_LACUNAS_CONHECIDAS"
    return {
        "situacao": situacao,
        "fontes_validadas": sorted(s for s, f in fontes.items() if f["situacao"] == "VALIDADA"),
        "fontes_nao_validadas": {s: fontes[s]["situacao"] for s in nao_validadas},
        "dias_com_lacuna": lacunas,
        "dias_so_em_uma_fonte": t["divergencias_entre_fontes"],
        "observacao": "A conferência entre fontes só é possível nos dias cobertos por mais de uma fonte validada."
        if nao_validadas else None,
    }


def manifesto(banco: B.Banco, inicio: date, fim: date, fontes: list[str], acervo: Acervo | None = None) -> dict:
    """Manifesto de cobertura do período: situação dia a dia, lacunas explícitas e procedência de cada arquivo.

    Não contém dados pessoais: só endereços oficiais, datas, tamanhos, hashes e estados.
    """
    linhas = cobertura(banco, inicio, fim, fontes, acervo)
    arquivos = {a["sha256"]: a for a in banco.arquivos()}
    por_sha: dict[str, list[int]] = {}
    for p in banco.publicacoes():
        if p["sha256"]:
            por_sha.setdefault(p["sha256"], []).append(p["id"])
    verificacoes = {v["sha256"]: v for v in banco.con.execute("SELECT * FROM verificacao_arquivo")}
    edicoes = []
    for p in banco.publicacoes():
        if not p["data_publicacao"] or not inicio.isoformat() <= p["data_publicacao"] <= fim.isoformat():
            continue
        ultimo = (banco.downloads(p["id"]) or [None])[-1]
        arquivo = arquivos.get(p["sha256"]) if p["sha256"] else None
        verificacao = verificacoes.get(p["sha256"]) if p["sha256"] else None
        edicoes.append({
            "fonte": p["fonte"], "url_oficial": p["url"], "data": p["data_publicacao"], "tipo": p["tipo"], "ordem": p["ordem"],
            "estado": p["estado"], "sha256": p["sha256"], "bytes": arquivo["tamanho"] if arquivo else None,
            "paginas": verificacao["paginas"] if verificacao else None,
            "integridade": verificacao["integridade"] if verificacao else ("NAO_VERIFICADA" if arquivo else None),
            "versoes": len(banco.versoes(p["id"])), "tentativas": p["tentativas"], "ultimo_erro": p["ultimo_erro"],
            "esgotada": p["estado"] in B.PENDENTES and p["tentativas"] >= B.MAX_TENTATIVAS,
            "ultima_tentativa_em": p["atualizada_em"],
            # Substituída (o endereço passou a oferecer outro PDF) ≠ mesmo conteúdo em outra URL ≠ documento distinto.
            "relacao": ("SUBSTITUIDO_NO_MESMO_ENDERECO" if len(banco.versoes(p["id"])) > 1 else
                        "MESMO_CONTEUDO_DE_OUTRA_URL" if p["sha256"] and len(por_sha.get(p["sha256"], [])) > 1 else
                        "DOCUMENTO_DISTINTO"),
            "coletado_em": ultimo["iniciado_em"] if ultimo else None, "transporte": ultimo["transporte"] if ultimo else None,
            "versao_coletor": ultimo["versao_coletor"] if ultimo else None,
        })
    sem_data = [{"fonte": p["fonte"], "url_oficial": p["url"], "estado": p["estado"], "descoberta_em": p["descoberta_em"]}
                for p in banco.publicacoes() if not p["data_publicacao"]]
    return {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "fontes": fontes, "escopo": escopo(fontes),
            "sem_data_identificada": sem_data, "totais": totais(linhas),
            "lacunas": [l for l in linhas if l["situacao"] not in ("COMPLETO", "SEM_PUBLICACAO_LISTADA")],
            "dias": linhas, "edicoes": edicoes}
