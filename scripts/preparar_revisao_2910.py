"""Empacota a integração de 29/10 com uma única projeção pública validada; não publica."""
from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path
from preparar_painel_publico import RAIZ, validar_snapshot

ARQUIVOS = ('index.html', 'styles.css', 'logo.png', 'export.js', 'modelo.js', 'adapter.js', 'config.js', 'app.js')

def preparar(saida: Path, projecao: Path):
    origem = RAIZ / 'revisao-2910'
    validar_snapshot(json.loads(projecao.read_text(encoding='utf-8')))
    if saida.exists() or saida.resolve().is_relative_to(RAIZ):
        raise ValueError('Use saída nova fora do repositório, preservando entregas anteriores.')
    saida.mkdir(parents=True)
    for nome in ARQUIVOS:
        arquivo = origem / nome
        if arquivo.is_symlink() or not arquivo.is_file():
            raise ValueError('Recurso público inválido.')
        shutil.copyfile(arquivo, saida / nome)
    # A candidata lê somente este arquivo da mesma origem. A atualização no servidor
    # é responsabilidade do workflow canônico; não existe uma segunda base de dados.
    (saida / 'config.js').write_text("window.GEDIV_CONFIG=Object.freeze({source:'./dados.json',refreshMs:300000,version:'2026.11.18-integracao-2910-r1'});\n", encoding='utf-8')
    (saida / 'dados.json').write_bytes(projecao.read_bytes())
    (saida / '.nojekyll').write_bytes(b'')
    manifesto = {n: hashlib.sha256((saida/n).read_bytes()).hexdigest() for n in (*ARQUIVOS,'dados.json','.nojekyll')}
    return {'versao':'2026.11.18-integracao-2910-r1','publicado':False,'privacidade':'contrato público estrito validado','arquivos':manifesto}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--saida',type=Path,required=True)
    p.add_argument('--projecao',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(preparar(a.saida,a.projecao),ensure_ascii=False,indent=2))
