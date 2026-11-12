"""Validação com um PDF OFICIAL: executa o fluxo real e produz um relatório SEM dados pessoais.

    python -m observatorio.operacao validar-real ARQUIVO.pdf --data 2026-10-02 --url URL_OFICIAL \\
           --dados dados --saida validacao-real.json [--amostra amostra-privada.txt]

O relatório (`--saida`) pode ser versionado: traz identidade do arquivo, método e qualidade de cada
página, resenhas encontradas (número, página, classificação, quantidade de decisões) e contagens de
campos preenchidos. Não traz nomes, matrículas, números de processo nem trechos.

A amostra (`--amostra`) é PRIVADA: lista, por resenha, as linhas extraídas com a página, para a
conferência humana contra o PDF aberto ao lado. Não deve ser versionada nem publicada.

Nada é marcado como conferido: todos os registros continuam PENDENTES de revisão humana.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from .. import NOME, __version__
from ..gerencias.gediv import catalogo as C
from ..leitura import leitor, validacao
from ..nucleo import pdf
from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from ..painel import indicadores
from . import fluxo

REFERENCIAS = Path(__file__).resolve().parents[2] / "docs" / "validacao" / "referencias.json"


def executar(arquivo: str | Path, data: date, url: str | None, pasta_dados: str | Path, amostra: str | Path | None = None) -> dict:
    arquivo = Path(arquivo)
    dados = arquivo.read_bytes()
    laudo = pdf.examinar(dados)
    relatorio = {
        "sistema": NOME, "versao": __version__, "versao_leitor": leitor.VERSAO, "versao_regras": C.VERSAO_REGRAS,
        "executado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arquivo": {"nome": arquivo.name, "sha256": laudo.sha256, "bytes": laudo.tamanho, "data_informada": data.isoformat(),
                    "url_oficial_informada": url, "verificacao_estrutural": "OK" if laudo.valido else laudo.motivo},
        "ocr": dict(zip(("disponivel", "detalhe"), leitor.ocr_disponivel())),
    }
    referencia = next((r for r in validacao.carregar_referencias(REFERENCIAS) if r.get("data") == data.isoformat()), None)
    if referencia:
        relatorio["comparacao_com_referencia"] = {
            "origem_da_referencia": referencia.get("fonte_da_referencia"),
            "sha256_igual": referencia.get("sha256") == laudo.sha256, "bytes_iguais": referencia.get("bytes") == laudo.tamanho,
            "paginas_esperadas": referencia.get("paginas")}
    if not laudo.valido:
        relatorio["resultado"] = "ARQUIVO_RECUSADO"
        return relatorio

    relatorio["fluxo"] = fluxo.executar(pasta_dados, arquivo, data, url)
    banco = Banco(Path(pasta_dados) / "observatorio.sqlite3")
    try:
        sha = laudo.sha256
        leitura = banco.con.execute("SELECT * FROM leitura WHERE sha256 = ?", (sha,)).fetchone()
        paginas = banco.paginas(sha)
        relatorio["leitura"] = {
            "situacao": leitura["situacao"] if leitura else "NAO_LIDA", "erro": leitura["erro"] if leitura else None,
            "numero_da_edicao_lido": leitura["numero_edicao"] if leitura else None,
            "data_da_edicao_lida": leitura["data_edicao"] if leitura else None,
            "inconsistencias": json.loads(leitura["inconsistencias"] or "[]") if leitura else [],
            "paginas": len(paginas),
            "por_metodo": _contar(p["metodo"] for p in paginas), "por_qualidade": _contar(p["qualidade"] for p in paginas),
            "por_colunas": _contar(str(p["colunas"]) for p in paginas),
            "pagina_a_pagina": [{"pagina": p["numero"], "metodo": p["metodo"], "colunas": p["colunas"], "palavras": p["palavras"],
                                 "qualidade": p["qualidade"], "confianca_ocr": p["confianca"]} for p in paginas],
        }
        if referencia and "comparacao_com_referencia" in relatorio:
            relatorio["comparacao_com_referencia"]["paginas_iguais"] = referencia.get("paginas") == len(paginas)
        try:
            independente = validacao.cobertura_independente(Acervo(Path(pasta_dados) / "acervo").caminho(sha), paginas)
        except Exception as e:  # a conferência independente é um complemento; sua falha não invalida o relatório
            independente = {"erro": f"{type(e).__name__}: {e}"[:200]}
        relatorio["cobertura_frente_a_leitura_independente"] = independente

        atos = banco.con.execute("SELECT * FROM ato WHERE sha256 = ? ORDER BY pagina, rowid", (sha,)).fetchall()
        decisoes = banco.con.execute("SELECT * FROM decisao WHERE sha256 = ? ORDER BY rowid", (sha,)).fetchall()
        por_ato: dict[str, list] = {}
        for d in decisoes:
            por_ato.setdefault(d["ato_id"], []).append(d)
        classificacao = banco.con.execute("SELECT * FROM classificacao WHERE sha256 = ? AND gerencia = 'GEDIV'", (sha,)).fetchone()
        relatorio["gediv"] = {
            "atos_encontrados": len(atos), "decisoes_extraidas": len(decisoes),
            "atos_de_outras_unidades_descartados": classificacao["descartados"] if classificacao else None,
            "pendencias_do_arquivo": json.loads(classificacao["pendencias"] or "[]") if classificacao else [],
            "atos": [{
                "tipo": a["tipo"], "numero": a["numero"], "pagina": a["pagina"], "pagina_final": a["pagina_final"],
                "data_expediente": a["data_expediente"], "vinculo_gediv": a["vinculo"], "natureza": a["natureza"],
                "eixo": a["eixo"], "modalidade": a["modalidade"], "condicao": a["condicao"], "grupo": a["grupo"],
                "grupo_expressao": a["grupo_expressao"], "subcategoria": a["subcategoria"], "resultado": a["resultado"],
                "decisoes": len(por_ato.get(a["id"], [])), "pendencias": json.loads(a["pendencias"] or "[]")} for a in atos],
            "campos_preenchidos": {campo: sum(bool(d[campo]) for d in decisoes) for campo in ("processo", "servidor", "matricula", "lotacao", "cargo")}
            | {"classe_nivel_ou_dias": sum(bool(set(json.loads(d["detalhe"] or "{}")) - {"linha_quebrada"}) for d in decisoes),
               "linha_quebrada_sinalizada": sum("linha_quebrada" in json.loads(d["detalhe"] or "{}") for d in decisoes)},
            "processos_repetidos_no_mesmo_arquivo": len(decisoes) - len({(d["ato_id"], d["processo"]) for d in decisoes}),
            "eventos_de_alteracao": [{"tipo": e["tipo"], "subtipo": e["subtipo"], "pagina": e["pagina"], "modificador": e["modificador"],
                                      "estado": e["estado"], "resenhas_citadas": json.loads(e["resenhas_citadas"] or "[]")}
                                     for e in banco.con.execute("SELECT * FROM evento WHERE sha256 = ? ORDER BY pagina", (sha,))],
            "outras_publicacoes": [{"tipo": o["tipo"], "pagina": o["pagina"]}
                                   for o in banco.con.execute("SELECT * FROM outra_publicacao WHERE sha256 = ? ORDER BY pagina", (sha,))],
            "fora_escopo": [{"tipo": f["tipo"], "numero": f["numero"], "pagina": f["pagina"], "motivo": f["motivo"]}
                            for f in banco.con.execute("SELECT * FROM fora_escopo WHERE sha256 = ? ORDER BY pagina, numero", (sha,))],
            "por_validacao": _contar(d["validacao"] for d in decisoes),
        }
        pendente = indicadores.painel(banco, {"escopo": "pendente", "inicio": data.isoformat(), "fim": data.isoformat()}, indicadores.GERENCIA_PERFIL)
        conferido = indicadores.painel(banco, {"inicio": data.isoformat(), "fim": data.isoformat()}, indicadores.PUBLICO)
        relatorio["painel"] = {"indicadores_em_conferencia_preliminares": pendente["indicadores"],
                               "indicadores_conferidos": conferido["indicadores"],
                               "observacao": "Nenhum registro foi conferido automaticamente; os indicadores oficiais só mudam após revisão humana."}
        relatorio["resultado"] = "FLUXO_EXECUTADO"
        relatorio["conferencia_humana"] = "PENDENTE — comparar a amostra privada com o PDF e registrar o resultado"
        if amostra:
            _gravar_amostra(Path(amostra), arquivo.name, atos, por_ato, banco, sha)
    finally:
        banco.fechar()
    return relatorio


def _contar(valores) -> dict:
    contagem: dict = {}
    for v in valores:
        contagem[v] = contagem.get(v, 0) + 1
    return dict(sorted(contagem.items()))


def _gravar_amostra(destino: Path, nome: str, atos, por_ato, banco: Banco, sha: str) -> None:
    linhas = [f"AMOSTRA PRIVADA PARA CONFERÊNCIA HUMANA — {nome}", "Contém dados pessoais. NÃO versionar, NÃO publicar.",
              "Para cada resenha: abra o PDF na página indicada e confira cabeçalho, quantidade de linhas e três linhas ao acaso.", ""]
    for a in atos:
        linhas.append(f"== {a['tipo']} {a['numero']} · p. {a['pagina']}–{a['pagina_final']} · {a['eixo']} {a['modalidade'] or a['subcategoria'] or ''} "
                      f"· grupo {a['grupo'] or '—'} · {a['resultado']} · vínculo {a['vinculo']} · {len(por_ato.get(a['id'], []))} decisão(ões)")
        for p in json.loads(a["pendencias"] or "[]"):
            linhas.append(f"   ! {p}")
        for d in por_ato.get(a["id"], []):
            linhas.append(f"   p.{d['pagina']} | {d['processo']} | mat. {d['matricula'] or '—'} | {d['servidor'] or '—'} | {d['lotacao'] or d['cargo'] or '—'} "
                          f"| {d['detalhe']} | {d['resultado']}")
        linhas.append("")
    linhas.append("Páginas em que NENHUM ato da GEDIV foi encontrado mas há a expressão 'DIREITOS E VANTAGENS' (conferir se algo foi perdido):")
    com_ato = {p for a in atos for p in range(a["pagina"], a["pagina_final"] + 1)}
    perdidas = [str(p["numero"]) for p in banco.paginas(sha) if "DIREITOS E VANTAGENS" in C.normalizar(p["texto"]) and p["numero"] not in com_ato]
    linhas.append("   " + (", ".join(perdidas) or "nenhuma"))
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
