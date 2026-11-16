"""Snapshot estático público: agregados mensais, sem registros individualizados.

As fontes SQLite são abertas somente para leitura. Contagens positivas são
publicadas por intervalos de cinco; células com menos de cinco decisões não são
publicadas, nem é publicada a relação das dimensões suprimidas. Os intervalos
não são valores arredondados a interpretar como quantidades exatas.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..gerencias.gediv import catalogo as C

LIMIAR = 5
ESQUEMA = 1
_OBSERVACAO = (
    "Cobertura parcial do Diário Oficial; ausência de dados não confirma ausência de atos. "
    "A publicação usa agregados mensais em faixas e omite recortes pequenos. "
    "Dados provisórios não passaram por revisão humana e não são resultados oficiais."
)


def metrica(quantidade: int) -> dict:
    """Zero conhecido é explícito; qualquer positivo fica em uma faixa, nunca exato."""
    if quantidade < 0:
        raise ValueError("Contagem negativa")
    if quantidade == 0:
        return {"valor": 0, "minimo": 0, "maximo": 0, "rotulo": "0", "protegido": False}
    minimo = quantidade // LIMIAR * LIMIAR
    return {"valor": None, "minimo": minimo, "maximo": minimo + LIMIAR - 1,
            "rotulo": f"{minimo}–{minimo + LIMIAR - 1}", "protegido": True}


def _cobertura_informada(cobertura) -> dict:
    if cobertura is None:
        return {}
    if isinstance(cobertura, dict):
        return cobertura
    caminho = Path(cobertura)
    if caminho.suffix.lower() == ".csv":
        with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
            linhas = list(csv.DictReader(arquivo, delimiter=";"))
        return {
            "ausencia_tecnica_edicoes": sum(x.get("estado_tecnico_proposto") == "SEM_ATOS_GEDIV_CONFIRMADO" for x in linhas),
            "inconclusivas": sum(x.get("estado_tecnico_proposto") == "NAO_VERIFICADO" for x in linhas),
        }
    with caminho.open(encoding="utf-8-sig") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados, dict):
        raise ValueError("Cobertura deve ser um objeto ou matriz CSV")
    return dados


def _ler(caminho: Path) -> list[dict]:
    if not caminho.is_file():
        raise ValueError("Banco de origem indisponível")
    # Não usar Banco(): seu construtor aplica migrações, desnecessárias nesta leitura.
    with sqlite3.connect(caminho.resolve().as_uri() + "?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        if con.execute("PRAGMA user_version").fetchone()[0] > 8:
            raise ValueError("Esquema posterior ao contrato suportado")
        edicoes = []
        for leitura in con.execute("SELECT * FROM leitura ORDER BY data_edicao, numero_edicao, sha256"):
            l = dict(leitura)
            if l["situacao"] == "ERRO":
                continue
            classificacao = con.execute(
                "SELECT versao_regras, revisao_leitura FROM classificacao WHERE sha256=? AND gerencia='GEDIV'",
                (l["sha256"],)).fetchone()
            vigente = bool(classificacao and classificacao["versao_regras"] == C.VERSAO_REGRAS
                           and (l.get("revisao") is None or classificacao["revisao_leitura"] == l["revisao"]))
            atos = [dict(x) for x in con.execute(
                "SELECT id, chave_logica, eixo, modalidade, grupo, subcategoria, natureza, data_publicacao "
                "FROM ato WHERE sha256=? AND gerencia='GEDIV'", (l["sha256"],))] if vigente else []
            decisoes = [dict(x) for x in con.execute(
                "SELECT d.id, d.ato_id, d.chave_logica, d.validacao, d.matricula, "
                "EXISTS (SELECT 1 FROM conflito c WHERE c.estado='ABERTO' AND "
                "((c.alvo_tipo='decisao' AND c.alvo_id=d.id) OR (c.alvo_tipo='ato' AND c.alvo_id=d.ato_id))) AS conflito "
                "FROM decisao d JOIN ato a ON a.id=d.ato_id "
                "WHERE d.sha256=? AND a.gerencia='GEDIV' AND d.vigente=1", (l["sha256"],))] if vigente else []
            # Preferir revisão humana quando duas bases contêm a mesma edição;
            # a ordem dos bancos só desempata fontes sem revisão ou equivalentes.
            revisadas = sum(d["validacao"] == "CONFERIDO" for d in decisoes)
            edicoes.append({"leitura": l, "atos": atos, "decisoes": decisoes, "revisadas": revisadas})
        return edicoes


def projetar(bancos, cobertura=None) -> dict:
    """Gera somente um contrato allowlist; `bancos` é uma sequência em ordem de preferência.

    Para uma mesma edição, o banco com mais decisões conferidas prevalece; em
    empate, o último prevalece (ex.: cópia corrigida PR10.1 após o acervo PR10).
    Nenhum texto, identificador, resultado individual ou caminho sai desta função.
    """
    escolhidas = {}
    for banco in bancos:
        for edicao in _ler(Path(banco)):
            l = edicao["leitura"]
            chave = (l.get("numero_edicao"), l.get("data_edicao"))
            if not all(chave):
                # Sem identidade documental não é seguro juntar edições.
                continue
            anterior = escolhidas.get(chave)
            if anterior is None or edicao["revisadas"] >= anterior["revisadas"]:
                escolhidas[chave] = edicao
    celulas = defaultdict(lambda: {"atos": set(), "decisoes": set(), "pessoas": set()})
    conferidos, provisorios, atos_total, pendentes = set(), set(), set(), set()
    eixos = {eixo: {"conferidos": set(), "provisorios": set(), "atos": set(),
                    "publicacoes_pendentes": set(), "pessoas": set()} for eixo in C.EIXOS}
    datas = []
    paginas = 0
    for chave_edicao, edicao in escolhidas.items():
        l = edicao["leitura"]
        datas.append(l["data_edicao"])
        paginas += int(l.get("paginas") or 0)
        atos = {a["id"]: a for a in edicao["atos"] if a["eixo"] in C.EIXOS}
        for a in atos.values():
            atos_total.add((chave_edicao, a["chave_logica"] or a["id"]))
            eixos[a["eixo"]]["atos"].add((chave_edicao, a["chave_logica"] or a["id"]))
        com_conferidas = set()
        for d in edicao["decisoes"]:
            a = atos.get(d["ato_id"])
            if not a or a["natureza"] != C.ORIGINAL or d["validacao"] not in ("CONFERIDO", "PENDENTE") or d["conflito"]:
                continue
            data = a["data_publicacao"]
            if not data or len(data) != 10 or data < "2026-01-01":
                continue
            try:
                datetime.strptime(data, "%Y-%m-%d")
            except ValueError:
                continue
            situacao = "conferido" if d["validacao"] == "CONFERIDO" else "provisorio"
            identidade = (chave_edicao, d["id"])
            (conferidos if situacao == "conferido" else provisorios).add(identidade)
            eixos[a["eixo"]]["conferidos" if situacao == "conferido" else "provisorios"].add(identidade)
            ato_chave = (chave_edicao, a["chave_logica"] or a["id"])
            if situacao == "provisorio":
                pendentes.add(ato_chave)
                eixos[a["eixo"]]["publicacoes_pendentes"].add(ato_chave)
            else:
                com_conferidas.add(ato_chave)
            prog = a["eixo"] == C.PROGRESSAO
            modalidade = a["modalidade"] if prog and a["modalidade"] in C.MODALIDADES else None
            grupo = a["grupo"] if prog and a["grupo"] in C.GRUPO_POR_CODIGO else None
            sub = a["subcategoria"] if not prog and a["subcategoria"] in C.SUBCATEGORIA_POR_CODIGO else None
            chave = (data[:7], a["eixo"], modalidade, grupo, sub, situacao)
            celulas[chave]["atos"].add(ato_chave)
            celulas[chave]["decisoes"].add(identidade)
            matricula = re.sub(r"\D", "", str(d.get("matricula") or ""))
            if 6 <= len(matricula) <= 9 and len(set(matricula)) > 1:
                celulas[chave]["pessoas"].add(matricula)
                eixos[a["eixo"]]["pessoas"].add(matricula)
        # Atos sem decisões conferidas (incluindo modificadores pendentes) não
        # viram homologados porque não aparecem em um gráfico de decisões.
        for a in atos.values():
            ato_chave = (chave_edicao, a["chave_logica"] or a["id"])
            if ato_chave not in com_conferidas:
                pendentes.add(ato_chave)
                eixos[a["eixo"]]["publicacoes_pendentes"].add(ato_chave)
    publicadas = []
    for chave, dados in sorted(celulas.items(), key=lambda x: tuple(str(k or "") for k in x[0])):
        if len(dados["decisoes"]) < LIMIAR or len(dados["pessoas"]) < LIMIAR:
            continue
        periodo, eixo, modalidade, grupo, subcategoria, situacao = chave
        publicadas.append({"periodo": periodo, "eixo": eixo, "modalidade": modalidade, "grupo": grupo,
                           "subcategoria": subcategoria, "situacao": situacao,
                           "atos": metrica(len(dados["atos"])), "decisoes": metrica(len(dados["decisoes"]))})
    cobertura_dados = _cobertura_informada(cobertura)
    # Não repassar observações livres nem objetos arbitrários da matriz privada.
    cobertura_publica = {
        "inicio_historico": "2026-01-01", "primeira_publicacao": min(datas, default=None),
        "ultima_publicacao": max(datas, default=None), "edicoes": len(escolhidas), "paginas": paginas,
        "ausencia_tecnica_edicoes": int(cobertura_dados.get("ausencia_tecnica_edicoes") or 0),
        "inconclusivas": int(cobertura_dados.get("inconclusivas") or 0),
        "historico_completo": False, "observacao": _OBSERVACAO,
    }
    return {
        "schema_version": ESQUEMA, "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "origem": "dados_reais", "experimental": True, "versao_regras": C.VERSAO_REGRAS,
        "catalogo": {"grupos": [{"codigo": g.codigo, "nome": g.nome} for g in C.GRUPOS],
                     "subcategorias": [{"codigo": s.codigo, "nome": s.nome} for s in C.SUBCATEGORIAS]},
        "cobertura": cobertura_publica,
        "privacidade": {"limiar": LIMIAR, "faixa": LIMIAR, "cobertura_parcial": True,
                         "observacao": "Recortes sem pelo menos cinco matrículas distintas reconhecidas não são divulgados. Faixas não são contagens exatas; somas filtradas incluem somente agregados publicáveis."},
        "resumo": {"conferidos": metrica(len(conferidos)), "provisorios": metrica(len(provisorios)),
                   "atos": metrica(len(atos_total)), "publicacoes_pendentes": metrica(len(pendentes))},
        "resumo_eixos": {eixo: {campo: metrica(len(dados[campo]))
                                for campo in ("conferidos", "provisorios", "atos", "publicacoes_pendentes")}
                         for eixo, dados in eixos.items() if len(dados["pessoas"]) >= LIMIAR},
        "celulas": publicadas,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gera snapshot público agregado sem modificar as bases.")
    parser.add_argument("--banco", action="append", default=[], type=Path, help="Banco SQLite privado; pode repetir. Último desempata fontes equivalentes.")
    parser.add_argument("--cobertura", type=Path, help="Matriz CSV ou resumo JSON de cobertura, somente metadados autorizados.")
    parser.add_argument("--saida", required=True, type=Path, help="JSON público de saída.")
    args = parser.parse_args(argv)
    if args.saida.resolve() in {x.resolve() for x in args.banco} or args.saida.suffix.lower() != ".json":
        parser.error("A saída deve ser JSON separado dos bancos de origem")
    dados = projetar(args.banco, args.cobertura)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix=".snapshot-", suffix=".json", dir=args.saida.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
        os.replace(temporario, args.saida)
    finally:
        if os.path.exists(temporario):
            os.unlink(temporario)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
