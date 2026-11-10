"""Exportação do recorte filtrado: Excel (.xlsx, escrito com a biblioteca padrão) e CSV.

O arquivo sai da MESMA projeção do painel, de modo que os totais da tela e do arquivo coincidem.
Células iniciadas por = + - @ recebem apóstrofo, contra injeção de fórmulas.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from ..gerencias.gediv import catalogo as C

_PERIGO = re.compile(r"^[\s\x00-\x1f]*[=+\-@\t\r]")
_INVALIDO_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def seguro(valor) -> str:
    texto = "" if valor is None else str(valor)
    return "'" + texto if _PERIGO.match(texto) else texto


def _coluna(indice: int) -> str:
    nome = ""
    while True:
        indice, resto = divmod(indice, 26)
        nome = chr(65 + resto) + nome
        if not indice:
            return nome
        indice -= 1


def _folha(linhas) -> str:
    partes = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for r, linha in enumerate(linhas, 1):
        partes.append(f'<row r="{r}">')
        for c, valor in enumerate(linha):
            ref = f"{_coluna(c)}{r}"
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                partes.append(f'<c r="{ref}"><v>{valor}</v></c>')
            else:
                texto = escape(_INVALIDO_XML.sub(" ", seguro(valor)))
                partes.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{texto}</t></is></c>')
        partes.append("</row>")
    partes.append("</sheetData></worksheet>")
    return "".join(partes)


def xlsx(abas: dict[str, list[list]]) -> bytes:
    nomes = list(abas)
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(1, len(nomes) + 1)) + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n[:31])}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(nomes, 1))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                             for i in range(1, len(nomes) + 1)) + "</Relationships>")
        for i, nome in enumerate(nomes, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _folha(abas[nome]))
    return saida.getvalue()


def csv(linhas: list[list]) -> bytes:
    texto = "\r\n".join(";".join('"' + seguro(v).replace('"', '""') + '"' for v in linha) for linha in linhas)
    return ("﻿" + texto + "\r\n").encode("utf-8")


def _nome(tabela: dict, codigo) -> str:
    return tabela.get(codigo, "") if codigo else ""


def _detalhe(d: dict) -> str:
    return "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in (d or {}).items())


CABECALHO_DECISOES = ["Data da publicação", "Resenha", "Página", "Eixo", "Modalidade", "Condição", "Grupo", "Subcategoria",
                      "Processo", "Servidor", "Matrícula", "Lotação", "Cargo", "Classe/nível e demais dados", "Resultado",
                      "Natureza", "Vínculo GEDIV", "Validação", "Revisor", "Revisado em", "Refeito", "Tornado sem efeito",
                      "Fonte oficial", "Evidência (trecho)", "ID da decisão", "ID do ato"]


def linhas_decisoes(projecao: dict) -> list[list]:
    grupos = {g.codigo: f"{g.codigo} · {g.nome}" for g in C.GRUPOS}
    subs = {s.codigo: f"{s.codigo} · {s.nome}" for s in C.SUBCATEGORIAS}
    saida = [CABECALHO_DECISOES]
    for l in projecao["linhas"]:
        saida.append([l["data"], l["resenha"], l["pagina"], _nome(C.EIXOS, l["eixo"]), _nome(C.MODALIDADES, l["modalidade"]),
                      _nome(C.CONDICOES, l["condicao"]), _nome(grupos, l["grupo"]) or ("Não informado" if l["eixo"] == C.PROGRESSAO else ""),
                      _nome(subs, l["subcategoria"]), l["processo"], l["servidor"], l["matricula"], l["lotacao"], l["cargo"],
                      _detalhe(l["detalhe"]), _nome(C.RESULTADOS, l["resultado"]), l["natureza"], l["vinculo"], l["validacao"],
                      l["revisor"], l["revisado_em"], "SIM" if l["refeito"] else "NÃO", "SIM" if l["sem_efeito"] else "NÃO",
                      l["url_oficial"] or "não informado", l["trecho"], l["id"], l["ato_id"]])
    return saida


def planilha(projecao: dict) -> bytes:
    """Abas: Decisoes, Atos, Eventos_de_Alteracao, Indicadores, Metadados."""
    meta, f = projecao["meta"], projecao["meta"]["filtros"]
    atos = [["Data", "Resenha", "Página", "Eixo", "Modalidade", "Grupo", "Subcategoria", "Decisões", "Deferidos", "Indeferidos",
             "Vínculo GEDIV", "Refeito", "Tornado sem efeito", "Fonte oficial", "ID do ato"]]
    for r in projecao["resenhas"]:
        atos.append([r["data"], r["resenha"], r["pagina"], _nome(C.EIXOS, r["eixo"]), _nome(C.MODALIDADES, r["modalidade"]), r["grupo"],
                     r["subcategoria"], r["decisoes"], r["deferido"], r["indeferido"], r["vinculo"], "SIM" if r["refeito"] else "NÃO",
                     "SIM" if r["sem_efeito"] else "NÃO", r["url_oficial"] or "não informado", r["ato_id"]])
    eventos = [["Data do evento", "Tipo", "Subtipo", "Ato modificador", "Página", "Resenhas citadas", "Estado do vínculo",
                "Ato original", "Fundamento", "Fonte oficial", "ID do evento"]]
    for e in projecao["eventos"]:
        eventos.append([e["data_publicacao"], _nome(C.ALTERACOES, e["tipo"]), e["subtipo"], e["modificador"], e["pagina"],
                        ", ".join(e["resenhas_citadas"]), e["estado"], e["ato_original_id"], e["fundamento"],
                        e.get("url_oficial") or "não informado", e["id"]])
    indicadores = [["Indicador", "Valor", "Observação"]] + [
        [projecao["ajuda"][c], "não calculado" if projecao["indicadores"][c] is None else projecao["indicadores"][c],
         "Os indicadores não se somam entre si."] for c in projecao["indicadores"]]
    cob = meta["cobertura"]
    metadados = [["Campo", "Valor"], ["Sistema", meta["sistema"]], ["Situação dos dados", meta["rotulo"]],
                 ["Gerado em (UTC)", datetime.now(timezone.utc).isoformat(timespec="seconds")],
                 ["Versão do dicionário de regras", meta["versao_regras"]], ["Filtros", json.dumps(f, ensure_ascii=False)],
                 ["Cartão selecionado", meta["cartao"] or "nenhum"], ["Cobertura", cob["parecer"]],
                 ["Edições no acervo", cob["edicoes_no_acervo"]], ["Edições com pendência de leitura", cob["edicoes_com_pendencia_de_leitura"]],
                 ["Período das edições", f"{cob['primeira_data'] or '—'} a {cob['ultima_data'] or '—'}"],
                 ["Fonte", "Diário Oficial do Estado da Paraíba"],
                 ["Aviso", "Contém dados funcionais individualizados. Uso restrito a pessoas autorizadas."]]
    return xlsx({"Decisoes": linhas_decisoes(projecao), "Atos": atos, "Eventos_de_Alteracao": eventos,
                 "Indicadores": indicadores, "Metadados": metadados})
