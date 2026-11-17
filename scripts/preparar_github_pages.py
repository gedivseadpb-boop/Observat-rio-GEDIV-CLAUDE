"""Congela o pacote público para revisão. NÃO publica nem altera a hospedagem.

Uso: python scripts/preparar_github_pages.py --saida /pasta/externa/nova
Verificação posterior: python scripts/preparar_github_pages.py --verificar /pasta
O ZIP contém apenas os oito arquivos públicos e .nojekyll. O manifesto fica fora dele.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

import preparar_painel_publico as painel

RAIZ = Path(__file__).resolve().parents[1]
BRANCH = "entrega/painel-completo-referencias"
URL = "https://gedivseadpb-boop.github.io/Observat-rio-GEDIV-CLAUDE/"
ARQUIVOS = frozenset((*painel.ASSETS, "dados.json", ".nojekyll"))
PACOTE = "GEDIV_GitHub_Pages.zip"
MANIFESTO = "MANIFESTO_PUBLICACAO.json"


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(RAIZ), *args], text=True).strip()


def sha(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def inventario(pasta: Path) -> dict:
    if pasta.is_symlink() or not pasta.is_dir():
        raise ValueError("Distribuição ausente ou vinculada a outra pasta.")
    if {p.name for p in pasta.iterdir()} != ARQUIVOS:
        raise ValueError("A distribuição contém arquivos ausentes ou não permitidos.")
    if any(p.is_symlink() or not p.is_file() for p in pasta.iterdir()):
        raise ValueError("A distribuição aceita apenas arquivos regulares.")
    return {nome: {"bytes": (pasta / nome).stat().st_size,
                   "sha256": sha((pasta / nome).read_bytes())} for nome in sorted(ARQUIVOS)}


def validar_recursos(pasta: Path) -> None:
    html = (pasta / "index.html").read_text(encoding="utf-8")
    recursos = re.findall(r'(?:src|href)="([^"]+)"', html)
    for recurso in recursos:
        if recurso.startswith(("#", "data:")):
            continue
        nome = recurso.removeprefix("./").split("?", 1)[0]
        if not recurso.startswith("./") or nome not in ARQUIVOS:
            raise ValueError("Recurso incompatível com o subdiretório do GitHub Pages.")
        if nome.endswith((".js", ".css")) and recurso != "./" + nome + "?v=" + sha((pasta / nome).read_bytes())[:12]:
            raise ValueError("Recurso sem versão de conteúdo válida.")
    for nome in ("estilo.css", "app.js", "modelo.js", "xlsx.js", "pdf.js", "logo.png"):
        if not any(r.split("?", 1)[0] == "./" + nome for r in recursos):
            raise ValueError("Recurso obrigatório não referenciado.")
    if (pasta / ".nojekyll").read_bytes() != b"":
        raise ValueError("Marcador estático inesperado.")
    painel.validar_snapshot(json.loads((pasta / "dados.json").read_text(encoding="utf-8")))


def verificar(saida: Path) -> dict:
    if {p.name for p in saida.iterdir()} != {"site", PACOTE, MANIFESTO}:
        raise ValueError("Pacote externo contém arquivos inesperados.")
    manifesto = json.loads((saida / MANIFESTO).read_text(encoding="utf-8"))
    if (manifesto["url_proposta"] != URL or manifesto["branch"] != BRANCH
            or manifesto["publicado"] is not False
            or not re.fullmatch(r"[a-f0-9]{40}", manifesto["commit"])):
        raise ValueError("Identidade da entrega inválida.")
    arquivos = inventario(saida / "site")
    if arquivos != manifesto["arquivos"]:
        raise ValueError("A distribuição difere dos hashes aprováveis.")
    validar_recursos(saida / "site")
    if sha((saida / PACOTE).read_bytes()) != manifesto["zip_sha256"]:
        raise ValueError("O ZIP difere do manifesto.")
    with zipfile.ZipFile(saida / PACOTE) as z:
        if len(z.namelist()) != len(ARQUIVOS) or set(z.namelist()) != ARQUIVOS:
            raise ValueError("O ZIP contém arquivos fora da lista pública.")
        for nome in ARQUIVOS:
            if z.read(nome) != (saida / "site" / nome).read_bytes():
                raise ValueError("O ZIP não corresponde à distribuição.")
    return manifesto


def preparar(saida: Path) -> dict:
    saida = saida.resolve()
    if saida == RAIZ.resolve() or RAIZ.resolve() in saida.parents:
        raise ValueError("Use uma saída externa ao repositório, separada dos dados privados.")
    if saida.exists():
        raise ValueError("Use uma pasta nova; entregas anteriores não serão substituídas.")
    if git("branch", "--show-current") != BRANCH:
        raise ValueError("A preparação exige a branch de entrega autorizada.")
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Registre e revise as alterações antes de congelar a entrega.")
    commit = git("rev-parse", "HEAD")
    origem = RAIZ / "painel-publico"
    if {p.name for p in origem.iterdir()} != ARQUIVOS - {".nojekyll"}:
        raise ValueError("A origem pública contém arquivos não permitidos.")
    for nome in ARQUIVOS - {".nojekyll"}:
        arquivo = origem / nome
        registrado = subprocess.check_output(["git", "-C", str(RAIZ), "show", f"{commit}:painel-publico/{nome}"])
        if arquivo.is_symlink() or not arquivo.is_file() or arquivo.read_bytes() != registrado:
            raise ValueError("A origem pública não corresponde ao commit registrado.")
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gediv-preparacao-", dir=saida.parent) as tmp:
        pasta = Path(tmp)
        site = pasta / "site"
        painel.preparar(site, projecao=origem / "dados.json")
        if (site / "dados.json").read_bytes() != (origem / "dados.json").read_bytes():
            raise ValueError("A projeção existente deve ser preservada byte a byte.")
        (site / ".nojekyll").write_bytes(b"")
        validar_recursos(site)
        with zipfile.ZipFile(pasta / PACOTE, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for nome in sorted(ARQUIVOS):
                info = zipfile.ZipInfo(nome, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, (site / nome).read_bytes())
        dados = json.loads((site / "dados.json").read_text(encoding="utf-8"))
        manifesto = {"versao": 1, "branch": BRANCH, "commit": commit,
                     "url_proposta": URL, "publicado": False,
                     "projecao": {"sha256": sha((site / "dados.json").read_bytes()),
                                  "atualizado_em": dados["atualizado_em"],
                                  "cobertura": dados["cobertura"],
                                  "versao_regras": dados["versao_regras"]},
                     "arquivos": inventario(site), "zip_sha256": sha((pasta / PACOTE).read_bytes())}
        (pasta / MANIFESTO).write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        verificar(pasta)
        if git("rev-parse", "HEAD") != commit or git("status", "--porcelain", "--untracked-files=normal"):
            raise ValueError("O repositório mudou durante a preparação; refaça a revisão.")
        pasta.rename(saida)
    return manifesto


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    opcoes = parser.add_mutually_exclusive_group(required=True)
    opcoes.add_argument("--saida", type=Path)
    opcoes.add_argument("--verificar", type=Path)
    args = parser.parse_args()
    m = verificar(args.verificar) if args.verificar else preparar(args.saida)
    print(json.dumps({"commit": m["commit"], "url_proposta": m["url_proposta"],
                      "publicado": False, "zip_sha256": m["zip_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
