"""Valida e congela exclusivamente a distribuição de homologação; não publica."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

from preparar_painel_publico import validar_snapshot

DESTINO = "https://gedivseadpb-boop.github.io/gediv-painel-redesign-preview/"
ARQUIVOS = frozenset({".nojekyll", "index.html", "app.js", "estilo.css", "modelo.js",
                      "xlsx.js", "pdf.js", "logo.png", "dados.json", "calendario.js", "calendario.css"})


def preparar(origem: Path, saida: Path) -> dict:
    nomes = {p.name for p in origem.iterdir() if p.name != ".git"}
    if nomes != ARQUIVOS:
        raise ValueError("O pacote não corresponde à lista de arquivos públicos aprovada.")
    for nome in ARQUIVOS:
        p = origem / nome
        if p.is_symlink() or not p.is_file():
            raise ValueError("Somente arquivos regulares são permitidos.")
    dados = json.loads((origem / "dados.json").read_text(encoding="utf-8"))
    validar_snapshot(dados)
    html = (origem / "index.html").read_text(encoding="utf-8")
    for recurso in re.findall(r'(?:src|href)="([^"]+)"', html):
        if recurso.startswith(("#", "data:")):
            continue
        nome = recurso.removeprefix("./").split("?", 1)[0]
        if not recurso.startswith("./") or nome not in ARQUIVOS:
            raise ValueError("Recurso externo ou inesperado no pacote público.")
        if nome.endswith((".js", ".css")):
            digest = hashlib.sha256((origem / nome).read_bytes()).hexdigest()[:12]
            if recurso != f"./{nome}?v={digest}":
                raise ValueError("Versão de cache não corresponde ao conteúdo.")
    if (origem / ".nojekyll").read_bytes():
        raise ValueError("Marcador estático inválido.")
    if saida.exists():
        raise ValueError("Use saída nova para preservar entregas anteriores.")
    saida.mkdir(parents=True)
    inventario = {n: {"sha256": hashlib.sha256((origem / n).read_bytes()).hexdigest(),
                     "bytes": (origem / n).stat().st_size} for n in sorted(ARQUIVOS)}
    manifesto = {"destino_exclusivo": DESTINO, "versao": "2026.11.17-h1",
                 "projecao_gerada_em": dados["atualizado_em"], "cobertura": dados["cobertura"],
                 "privacidade": "validar_snapshot aprovado; somente projeção pública agregada",
                 "arquivos": inventario}
    with zipfile.ZipFile(saida / "GEDIV-homologacao.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for nome in sorted(ARQUIVOS):
            z.write(origem / nome, nome)
    (saida / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origem", type=Path)
    parser.add_argument("saida", type=Path)
    args = parser.parse_args()
    print(json.dumps(preparar(args.origem, args.saida), ensure_ascii=False, indent=2))
