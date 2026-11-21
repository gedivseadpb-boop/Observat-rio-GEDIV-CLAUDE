"""Gera a distribuição estática pública, sem copiar bancos ou documentos de origem.

Atualização privada: --banco pode ser repetido, com prioridade para a última fonte.
Build de um snapshot público já revisado: --projecao painel-publico/dados.json.
Nenhuma coleta, aprovação, alteração de banco ou publicação é feita por este comando.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import sys

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
ASSETS = ("index.html", "app.js", "modelo.js", "estilo.css", "logo.png", "xlsx.js", "pdf.js", "calendario.js", "calendario.css")


def preparar(saida: Path, bancos: list[Path] | None = None, projecao: Path | None = None, cobertura: Path | None = None) -> dict:
    from observatorio.painel.publicacao import projetar
    if bool(bancos) == bool(projecao):
        raise ValueError("Informe bancos privados OU uma projeção pública pronta.")
    if saida.resolve() in {RAIZ, RAIZ / "painel-publico"}:
        raise ValueError("A saída deve ser uma pasta de distribuição separada.")
    fontes = {Path(p).resolve() for p in (bancos or [])}
    if any((saida / nome).resolve() in fontes for nome in (*ASSETS, "dados.json")):
        raise ValueError("A distribuição nunca pode sobrescrever um banco de origem.")
    if bancos:
        dados = projetar(bancos, cobertura=cobertura)
    else:
        dados = json.loads(projecao.read_text(encoding="utf-8"))
    validar_snapshot(dados)
    # Uma distribuição é sempre formada por esta lista fixa de arquivos.
    saida.mkdir(parents=True, exist_ok=True)
    inesperados = [p.name for p in saida.iterdir() if p.name not in {*ASSETS, "dados.json"}]
    if inesperados:
        raise ValueError("A pasta de saída contém arquivos não permitidos; use uma pasta nova.")
    for nome in ASSETS:
        shutil.copyfile(RAIZ / "painel-publico" / nome, saida / nome)
    # Recursos com conteúdo novo não podem herdar o cache de uma versão anterior.
    indice = saida / "index.html"
    versoes = {nome: hashlib.sha256((saida / nome).read_bytes()).hexdigest()[:12]
               for nome in ASSETS if nome.endswith((".js", ".css"))}
    def versionar(achado):
        nome = achado.group(2)
        return achado.group(1) + nome + ("?v=" + versoes[nome] if nome in versoes else "") + achado.group(3)
    html = re.sub(r'((?:src|href)="\./)([^"?]+)(?:\?v=[^"]*)?(")',
                  versionar, indice.read_text(encoding="utf-8"))
    indice.write_text(html, encoding="utf-8", newline="\n")
    (saida / "dados.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"arquivos_publicos": len(ASSETS) + 1, "saida": str(saida)}


def validar_snapshot(dados: dict) -> None:
    if dados.get("schema_version") != 1 or dados.get("origem") != "dados_reais":
        raise ValueError("A publicação exige projeção real no contrato público versão 1.")
    permitidos = {"schema_version", "atualizado_em", "origem", "experimental", "versao_regras", "catalogo", "cobertura", "privacidade", "resumo", "resumo_eixos", "celulas"}
    if set(dados) != permitidos:
        raise ValueError("Campos fora do contrato público.")
    from observatorio.gerencias.gediv import catalogo as C
    from observatorio.painel.publicacao import projetar
    from datetime import datetime
    base = projetar([])
    if dados["experimental"] is not True or dados["versao_regras"] != C.VERSAO_REGRAS:
        raise ValueError("Metadados de versão não permitidos.")
    datetime.fromisoformat(dados["atualizado_em"])
    if set(dados["cobertura"]) != set(base["cobertura"]):
        raise ValueError("Cobertura fora do contrato público.")
    c = dados["cobertura"]
    for campo in ("edicoes", "paginas", "ausencia_tecnica_edicoes", "inconclusivas"):
        if type(c[campo]) is not int or c[campo] < 0:
            raise ValueError("Quantidade de cobertura inválida.")
    for campo in ("primeira_publicacao", "ultima_publicacao"):
        if c[campo] is not None:
            datetime.strptime(c[campo], "%Y-%m-%d")
    for campo in ("inicio_historico", "historico_completo", "observacao"):
        if c[campo] != base["cobertura"][campo]:
            raise ValueError("A cobertura não aceita texto livre ou homologação presumida.")
    if dados["privacidade"] != base["privacidade"]:
        raise ValueError("Política de privacidade fora do contrato público.")
    catalogo = {"grupos": [{"codigo": g.codigo, "nome": g.nome} for g in C.GRUPOS],
                "subcategorias": [{"codigo": x.codigo, "nome": x.nome} for x in C.SUBCATEGORIAS]}
    if dados["catalogo"] != catalogo:
        raise ValueError("Catálogo fora do conjunto institucional permitido.")
    proibidos = {"servidor", "matricula", "processo", "processos", "processos_citados", "trecho", "texto", "ato_id", "pdf_no_acervo", "fundamento", "revisor", "justificativa", "sha256", "resenha", "pagina", "url_oficial"}
    def percorrer(v):
        if isinstance(v, dict):
            if proibidos.intersection(v):
                raise ValueError("A projeção contém campo individual ou privado.")
            for filho in v.values():
                percorrer(filho)
        elif isinstance(v, list):
            for filho in v:
                percorrer(filho)
    percorrer(dados)
    def metrica(m):
        if set(m) != {"valor", "minimo", "maximo", "rotulo", "protegido"}:
            raise ValueError("Métrica fora do contrato público.")
        if m["valor"] == 0 and m["minimo"] == m["maximo"] == 0 and m["rotulo"] == "0" and m["protegido"] is False:
            return
        lo, hi = m["minimo"], m["maximo"]
        if (m["valor"] is not None or type(lo) is not int or type(hi) is not int
                or lo < 0 or lo % 5 or hi != lo + 4 or m["protegido"] is not True
                or m["rotulo"] != f"{lo}–{hi}"):
            raise ValueError("Contagem positiva deve ser uma faixa protegida.")
    if set(dados["resumo"]) != {"conferidos", "provisorios", "atos", "publicacoes_pendentes"}:
        raise ValueError("Resumo fora do contrato público.")
    for m in dados["resumo"].values():
        metrica(m)
    if not set(dados["resumo_eixos"]).issubset(C.EIXOS):
        raise ValueError("Resumo de eixo fora do contrato público.")
    for resumo in dados["resumo_eixos"].values():
        if set(resumo) != set(dados["resumo"]):
            raise ValueError("Resumo de eixo fora do contrato público.")
        for m in resumo.values():
            metrica(m)
    chaves = set()
    for celula in dados.get("celulas", []):
        if set(celula) != {"periodo", "eixo", "modalidade", "grupo", "subcategoria", "situacao", "atos", "decisoes"}:
            raise ValueError("Célula contém campos fora do contrato público.")
        if not re.fullmatch(r"20[0-9]{2}-(?:0[1-9]|1[0-2])", celula["periodo"]):
            raise ValueError("A divulgação é somente mensal.")
        if celula["eixo"] not in C.EIXOS or celula["situacao"] not in {"conferido", "provisorio"}:
            raise ValueError("Eixo ou situação fora do contrato público.")
        if celula["grupo"] is not None and celula["grupo"] not in C.GRUPO_POR_CODIGO:
            raise ValueError("Grupo não oficial.")
        if celula["subcategoria"] is not None and celula["subcategoria"] not in C.SUBCATEGORIA_POR_CODIGO:
            raise ValueError("Assunto não oficial.")
        if celula["modalidade"] not in {None, "HORIZONTAL", "VERTICAL"}:
            raise ValueError("Modalidade não permitida.")
        if celula["eixo"] == "PROGRESSAO":
            if celula["subcategoria"] is not None:
                raise ValueError("Progressão não admite serviço TS.")
        elif celula["modalidade"] is not None or celula["grupo"] is not None:
            raise ValueError("Tempo de Serviço não admite modalidade ou grupo de Progressão.")
        chave = tuple(celula[k] for k in ("periodo", "eixo", "modalidade", "grupo", "subcategoria", "situacao"))
        if chave in chaves:
            raise ValueError("Célula pública duplicada: somas e denominadores seriam incorretos.")
        chaves.add(chave)
        metrica(celula["atos"])
        metrica(celula["decisoes"])
        decisoes = celula.get("decisoes", {})
        if decisoes.get("valor") is not None or decisoes.get("minimo", 0) < 5:
            raise ValueError("Célula pública sem proteção de contagem mínima.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--banco", action="append", type=Path, default=[])
    p.add_argument("--projecao", type=Path)
    p.add_argument("--cobertura", type=Path)
    p.add_argument("--saida", type=Path, default=RAIZ / "dist")
    a = p.parse_args()
    print(json.dumps(preparar(a.saida, a.banco, a.projecao, a.cobertura), ensure_ascii=False))

if __name__ == "__main__":
    main()
