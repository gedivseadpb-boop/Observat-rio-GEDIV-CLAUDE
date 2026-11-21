"""Conjunto-ouro: execução do fluxo real sobre edições OFICIAIS e comparação com o resultado esperado.

    python -m observatorio.operacao ouro --pdfs PASTA_COM_OS_PDFS [--manifesto docs/validacao/conjunto_ouro.json]
                                         [--saida relatorio-ouro.json]

- Os PDFs são localizados pelo SHA-256 (o nome do arquivo não importa) e nunca entram no repositório.
- Cada edição roda em um PROCESSO PRÓPRIO, com base de dados temporária: o pico de memória medido é
  o daquela edição, e uma edição não contamina a outra.
- O relatório não contém nomes, matrículas, números de processo nem trechos (é o mesmo conteúdo do
  `validar-real`, reduzido). Pode ser versionado como evidência.
- Saída 0 quando todas as edições disponíveis conferem; 1 quando há divergência (regressão); 2 quando
  alguma edição do manifesto não foi encontrada na pasta.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import saida as codigos

MANIFESTO_PADRAO = Path(__file__).resolve().parents[2] / "docs" / "validacao" / "conjunto_ouro.json"


def carregar(manifesto: str | Path = MANIFESTO_PADRAO) -> dict:
    return json.loads(Path(manifesto).read_text(encoding="utf-8"))


def localizar(pasta: str | Path, shas: set[str]) -> dict[str, Path]:
    """SHA-256 → caminho, para os PDFs da pasta cujo conteúdo está no manifesto."""
    achados: dict[str, Path] = {}
    for arquivo in sorted(Path(pasta).glob("*.pdf")):
        sha = hashlib.sha256(arquivo.read_bytes()).hexdigest()
        if sha in shas and sha not in achados:
            achados[sha] = arquivo
    return achados


def _ato_obtido(a: dict) -> dict:
    return {"numero": a["numero"], "eixo": a["eixo"], "classe": a["modalidade"] or a["subcategoria"], "grupo": a["grupo"],
            "resultado": a["resultado"], "vinculo": a["vinculo_gediv"], "decisoes": a["decisoes"]}


def comparar(esperado: dict, relatorio: dict) -> list[str]:
    """Lista de divergências entre o esperado e o relatório do `validar-real` (vazia = confere)."""
    if relatorio.get("resultado") != "FLUXO_EXECUTADO":
        return [f"fluxo não executado: {relatorio.get('resultado')}"]
    g = relatorio["gediv"]
    divergencias = []
    chave = lambda a: json.dumps(a, sort_keys=True, ensure_ascii=False)
    obtidos = {chave(_ato_obtido(a)) for a in g["atos"]}
    esperados = {chave(a) for a in esperado["atos"]}
    for falta in sorted(esperados - obtidos):
        divergencias.append(f"ato esperado não obtido: {falta}")
    for sobra in sorted(obtidos - esperados):
        divergencias.append(f"ato obtido não esperado: {sobra}")
    if g["decisoes_extraidas"] != esperado["decisoes"]:
        divergencias.append(f"decisões: esperado {esperado['decisoes']}, obtido {g['decisoes_extraidas']}")
    registrados = {(f["numero"], f["motivo"]) for f in g.get("fora_escopo", [])}
    for numero, motivo in esperado.get("fora_escopo_inclui", []):
        if (numero, motivo) not in registrados:
            divergencias.append(f"fora do escopo esperado não registrado: {numero} {motivo}")
    return divergencias


def _executar_edicao(doc: dict, arquivo: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="ouro-") as pasta:
        saida = Path(pasta) / "relatorio.json"
        comando = [sys.executable, "-m", "observatorio.operacao", "validar-real", str(arquivo), "--data", doc["data"],
                   "--url", doc["url"], "--dados", str(Path(pasta) / "dados"), "--saida", str(saida)]
        processo = subprocess.run(comando, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
        # validar-real sai com 3 quando a edição foi lida com páginas pendentes: a execução é válida e a comparação
        # com o esperado decide. Só o código é registrado — a saída de erro poderia trazer trechos do documento.
        if processo.returncode not in (codigos.SUCESSO, codigos.CONCLUIDO_COM_PENDENCIAS) or not saida.exists():
            return {"resultado": "ERRO_DE_EXECUCAO", "erro": f"validar-real terminou com código {processo.returncode}"}
        return json.loads(saida.read_text(encoding="utf-8"))


def executar(pasta_pdfs: str | Path, manifesto: str | Path = MANIFESTO_PADRAO) -> dict:
    dados = carregar(manifesto)
    arquivos = localizar(pasta_pdfs, {d["sha256"] for d in dados["documentos"]})
    edicoes = []
    for doc in dados["documentos"]:
        item = {"data": doc["data"], "sha256": doc["sha256"]}
        arquivo = arquivos.get(doc["sha256"])
        if arquivo is None:
            edicoes.append({**item, "situacao": "PDF_AUSENTE"})
            continue
        relatorio = _executar_edicao(doc, arquivo)
        divergencias = comparar(doc["esperado"], relatorio)
        gediv = relatorio.get("gediv", {})
        leitura = relatorio.get("leitura", {})
        edicoes.append({
            **item, "situacao": "CONFERE" if not divergencias else "DIVERGE", "divergencias": divergencias,
            "obtido": {"atos": [_ato_obtido(a) for a in gediv.get("atos", [])], "decisoes": gediv.get("decisoes_extraidas"),
                       "fora_escopo": gediv.get("fora_escopo", [])},
            "leitura": {k: leitura.get(k) for k in ("situacao", "numero_da_edicao_lido", "paginas", "por_metodo", "por_qualidade")},
            "desempenho": relatorio.get("desempenho"),
            "versoes": {k: relatorio.get(k) for k in ("versao", "versao_leitor", "versao_regras")},
            **({"erro": relatorio["erro"]} if "erro" in relatorio else {}),
        })
    situacoes = [e["situacao"] for e in edicoes]
    return {"manifesto_versao": dados.get("versao"), "situacao_do_manifesto": dados.get("situacao"),
            "resumo": {s: situacoes.count(s) for s in sorted(set(situacoes))}, "edicoes": edicoes}


def codigo_de_saida(resultado: dict) -> int:
    """0 só quando TODAS as edições do manifesto foram executadas e conferem. Manifesto sem edições ou nenhum PDF
    encontrado: 4 (nada avaliado). Divergência, ou parte das edições sem PDF: 1 (antes era 2, o código de erro de uso,
    e um manifesto vazio saía com 0)."""
    situacoes = [e["situacao"] for e in resultado["edicoes"]]
    if not situacoes or all(s == "PDF_AUSENTE" for s in situacoes):
        return codigos.NAO_EXECUTADO
    if "DIVERGE" in situacoes or "PDF_AUSENTE" in situacoes:
        return codigos.FALHA
    return codigos.SUCESSO
