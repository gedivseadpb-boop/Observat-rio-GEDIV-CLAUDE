"""Servidor HTTP local e PDFs sintéticos para testar a coleta sem acessar a internet."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from observatorio.nucleo.rede import Politica


def pdf_sintetico(marca: str) -> bytes:
    """PDF mínimo, sem qualquer conteúdo real, diferente para cada marca."""
    corpo = (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n% " + marca.encode() + b"\n")
    return corpo + b"x" * 1200 + b"\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


class Servidor:
    """Rotas: caminho -> (status, tipo, corpo) | callable(contador) -> mesma tupla."""

    def __init__(self):
        self.rotas: dict[str, object] = {}
        self.acessos: dict[str, int] = {}
        externo = self

        class Manipulador(BaseHTTPRequestHandler):
            def do_GET(self):
                externo.acessos[self.path] = externo.acessos.get(self.path, 0) + 1
                rota = externo.rotas.get(self.path)
                if callable(rota):
                    rota = rota(externo.acessos[self.path])
                if rota is None:
                    rota = (404, "text/plain", b"nao encontrado")
                status, tipo, corpo = rota
                self.send_response(status)
                if status in (301, 302):
                    self.send_header("Location", corpo.decode())
                    corpo = b""
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def log_message(self, *args):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Manipulador)
        self.endereco = f"127.0.0.1:{self.http.server_address[1]}"
        self.base = f"http://{self.endereco}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def politica(self, **extras) -> Politica:
        parametros = dict(servidores=frozenset({self.endereco}), esquemas=frozenset({"http"}),
                          tempo_limite=2, tentativas=2, espera=0, pausa=0)
        parametros.update(extras)
        return Politica(**parametros)

    def encerrar(self):
        self.http.shutdown()
        self.http.server_close()


class FonteLocal:
    """Fonte de teste que aponta para o servidor local, reutilizando a leitura real."""

    def __init__(self, real, servidor: Servidor):
        self.real, self.servidor = real, servidor
        self.sigla = real.sigla
        self.servidores = frozenset({servidor.endereco})

    def _local(self, url: str) -> str:
        return url.replace("https://" + self.real.servidor, self.servidor.base)

    def url_mes(self, ano, mes):
        return self._local(self.real.url_mes(ano, mes))

    def extrair(self, html, url_pagina):
        from dataclasses import replace
        oficial = url_pagina.replace(self.servidor.base, "https://" + self.real.servidor)
        itens, paginas = self.real.extrair(html, oficial)
        return [replace(i, url=self._local(i.url)) for i in itens], [self._local(p) for p in paginas]

    def enderecos_download(self, url):
        return self.real.enderecos_download(url)
