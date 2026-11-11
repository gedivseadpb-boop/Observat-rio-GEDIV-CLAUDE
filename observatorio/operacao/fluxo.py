"""Fluxo completo sobre PDFs já obtidos: importar → ler (texto/OCR) → classificar GEDIV.

A obtenção automática nas fontes oficiais é feita por `observatorio.coleta` (lotes). Este fluxo
serve tanto para PDFs baixados quanto para PDFs fornecidos manualmente — o caminho é o mesmo.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..coleta import coletor
from ..coleta.fontes import data_do_nome
from ..gerencias.gediv import processo
from ..leitura import leitor
from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco


def executar(pasta_dados: str | Path, origem: str | Path | None = None, data: date | None = None, url: str | None = None) -> dict:
    pasta = Path(pasta_dados)
    banco, acervo = Banco(pasta / "observatorio.sqlite3"), Acervo(pasta / "acervo")
    try:
        importados = []
        if origem is not None:
            origem = Path(origem)
            for arquivo in (sorted(origem.glob("*.pdf")) if origem.is_dir() else [origem]):
                quando = data or data_do_nome(arquivo.name)
                if quando is None:
                    importados.append({"arquivo": arquivo.name, "aceito": False, "motivo": "DATA_NAO_INFORMADA_NEM_NO_NOME"})
                    continue
                importados.append({"arquivo": arquivo.name, "data": quando.isoformat(),
                                   **coletor.importar_manual(banco, acervo, arquivo.read_bytes(), quando,
                                                             url or f"manual:{arquivo.name}", arquivo.name)})
        return {"importacao": importados, "leitura": leitor.processar(banco, acervo),
                "classificacao": processo.classificar_pendentes(banco), "situacao": processo.situacao(banco)}
    finally:
        banco.fechar()
