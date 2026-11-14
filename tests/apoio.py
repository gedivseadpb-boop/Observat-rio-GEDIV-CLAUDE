"""Servidor HTTP local e PDFs sintéticos para testar a coleta sem acessar a internet."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from observatorio.nucleo.rede import Politica


def pdf_sem_paginas(marca: str) -> bytes:
    """Arquivo com assinatura e fim de PDF, mas SEM estrutura legível (sem xref nem páginas)."""
    corpo = (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n% " + marca.encode() + b"\n")
    return corpo + b"x" * 1200 + b"\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def pdf_sintetico(marca: str, paginas: int = 1) -> bytes:
    """PDF estruturalmente válido (xref com deslocamentos corretos), com páginas em branco e sem
    qualquer conteúdo real. A marca torna cada arquivo diferente (SHA-256 distinto)."""
    filhos = " ".join(f"{3 + i} 0 R" for i in range(paginas))
    objetos = [b"<< /Type /Catalog /Pages 2 0 R >>",
               f"<< /Type /Pages /Kids [{filhos}] /Count {paginas} >>".encode()]
    objetos += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>"] * paginas
    saida = bytearray(b"%PDF-1.4\n% " + marca.encode() + b"\n" + b"%" + b"x" * 1100 + b"\n")
    deslocamentos = []
    for numero, objeto in enumerate(objetos, start=1):
        deslocamentos.append(len(saida))
        saida += f"{numero} 0 obj\n".encode() + objeto + b"\nendobj\n"
    inicio_xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    saida += b"".join(f"{d:010d} 00000 n \n".encode() for d in deslocamentos)
    saida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n".encode()
    return bytes(saida)


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
                # 4º elemento opcional: {"cabecalhos": {...}, "anunciar": int | None, "cortar": int}
                #   anunciar: Content-Length enviado (None = não enviar); cortar: bytes enviados antes de fechar a conexão.
                status, tipo, corpo, *resto = rota
                opcoes = resto[0] if resto else {}
                self.send_response(status)
                if status in (301, 302):
                    self.send_header("Location", corpo.decode())
                    corpo = b""
                self.send_header("Content-Type", tipo)
                anunciar = opcoes.get("anunciar", len(corpo))
                if anunciar is not None:
                    self.send_header("Content-Length", str(anunciar))
                else:
                    self.close_connection = True
                for nome, valor in opcoes.get("cabecalhos", {}).items():
                    self.send_header(nome, valor)
                self.end_headers()
                if "cortar" in opcoes:
                    self.wfile.write(corpo[:opcoes["cortar"]])
                    self.wfile.flush()
                    self.close_connection = True
                    return
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

    def __getattr__(self, nome):
        # url_recentes só existe se a fonte real a oferece (A União); a CGE continua sem ela.
        if nome == "url_recentes" and hasattr(self.real, "url_recentes"):
            return lambda: self._local(self.real.url_recentes())
        raise AttributeError(nome)

    def extrair(self, html, url_pagina):
        from dataclasses import replace
        oficial = url_pagina.replace(self.servidor.base, "https://" + self.real.servidor)
        itens, paginas = self.real.extrair(html, oficial)
        return [replace(i, url=self._local(i.url)) for i in itens], [self._local(p) for p in paginas]

    def enderecos_download(self, url):
        return self.real.enderecos_download(url)
