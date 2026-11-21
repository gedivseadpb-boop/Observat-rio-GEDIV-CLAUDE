"""Congela o frontend Clareza para revisão local. Não publica nem acessa o GitHub."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from preparar_painel_publico import ASSETS, RAIZ, validar_snapshot

VERSAO = "2026.11.18-clareza-r1"


def preparar(saida: Path) -> dict:
    origem = RAIZ / "painel-publico"
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=RAIZ, text=True).strip():
        raise ValueError("Registre o código e as evidências no commit antes de congelar a revisão.")
    dados = (origem / "dados.json").read_bytes()
    validar_snapshot(json.loads(dados))
    if saida.exists() or saida.resolve().is_relative_to(RAIZ):
        raise ValueError("Use uma saída nova, fora do repositório, preservando entregas anteriores.")
    saida.mkdir(parents=True)
    site = saida / "site"
    site.mkdir()
    for nome in ASSETS:
        if (origem / nome).is_symlink():
            raise ValueError("O pacote aceita somente arquivos públicos regulares.")
        shutil.copy2(origem / nome, site / nome)
    (site / "dados.json").write_bytes(dados)
    (site / ".nojekyll").write_bytes(b"")
    html = (site / "index.html").read_text(encoding="utf-8")
    for nome in ASSETS:
        if nome.endswith((".js", ".css")):
            digest = hashlib.sha256((site / nome).read_bytes()).hexdigest()[:12]
            if f'./{nome}?v={digest}' not in html:
                raise ValueError(f"Recurso sem versão de cache correspondente: {nome}")
    # A prévia offline usa os mesmos arquivos e a mesma projeção pública congelada.
    # O fetch real lê uma data URL; não há servidor simulado nem credenciais.
    offline = html
    for nome in ("estilo.css", "calendario.css"):
        offline = re.sub(r'<link rel="stylesheet" href="\./' + re.escape(nome) + r'\?v=[^"]+">',
                         lambda _: "<style>" + (site / nome).read_text(encoding="utf-8") + "</style>", offline)
    scripts = re.findall(r'<script src="\./([^?]+)\?v=[^"]+" defer></script>', offline)
    offline = re.sub(r'<script src="\./[^?]+\?v=[^"]+" defer></script>', "", offline)
    logo = base64.b64encode((site / "logo.png").read_bytes()).decode()
    offline = offline.replace('src="./logo.png"', 'src="data:image/png;base64,' + logo + '"')
    snapshot = "data:application/json;base64," + base64.b64encode(dados).decode()
    inline = []
    for nome in scripts:
        script = (site / nome).read_text(encoding="utf-8")
        if nome == "app.js":
            if script.count("'./dados.json'") != 1:
                raise ValueError("Rever a adaptação offline do carregamento da projeção.")
            script = script.replace("'./dados.json'", json.dumps(snapshot))
        inline.append("<script>" + script.replace("</script", "<\\/script") + "</script>")
    offline = offline.replace("</body>", "\n".join(inline) + "\n</body>")
    offline = offline.replace("Em avaliação · Clareza r1", "Prévia offline · Clareza r1")
    (saida / "PREVIA_INTERATIVA.html").write_text(offline, encoding="utf-8")
    arquivos = {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
                for p in sorted(site.iterdir())}
    manifesto = {"versao": VERSAO, "publicado": False,
                 "commit_fonte": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=RAIZ, text=True).strip(),
                 "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=RAIZ, text=True).strip(),
                 "dados_sha256": hashlib.sha256(dados).hexdigest(),
                 "site": arquivos,
                 "previa_offline": "Mesmo frontend com recursos incorporados e projeção pública congelada. Não atualiza dados pela internet."}
    (saida / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    (saida / "LEIA-ME.md").write_text(
        "# GEDIV Clareza — revisão local\n\nAbra PREVIA_INTERATIVA.html no navegador para avaliar os dois temas, "
        "calendário, filtros e gráficos sem instalar programas. Esta cópia usa a projeção pública de16/11/2026, "
        "com cobertura parcial. Não há dados individuais.\n\nA pasta site contém os11 arquivos para uma futura "
        "publicação, que exige autorização específica. Nenhum site foi atualizado por este pacote.\n", encoding="utf-8")
    with zipfile.ZipFile(saida / "GEDIV-Clareza-revisao.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(saida.rglob("*")):
            if p.is_file() and p.suffix != ".zip":
                z.write(p, p.relative_to(saida))
    return manifesto


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saida", type=Path)
    print(json.dumps(preparar(parser.parse_args().saida), ensure_ascii=False, indent=2))
