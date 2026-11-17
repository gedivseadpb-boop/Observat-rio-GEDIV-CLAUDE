"""Controle reversível usa somente GitHub Pages simulado; nunca chama rede real."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from observatorio.sites.controle import Controle, Recusado, assinatura, validar_registro

RAIZ = Path(__file__).resolve().parents[1]


class GitHubFalso:
    def __init__(self, arquivos, url, fonte):
        self.arquivos = arquivos
        self.url, self.fonte = url, fonte
        self.pages_ativo = True
        self.workflow_state = {10: "active", 20: "active", 30: "active"}
        self.restaurado = None
        self.chamadas = []

    def api(self, repo, recurso="", metodo="GET", corpo=None, ausente=False):
        self.chamadas.append((recurso, metodo, corpo))
        if recurso == "pages":
            if metodo == "GET":
                return {"html_url": self.url, "status": "built", "build_type": "legacy", "source": {"branch": "gh-pages", "path": "/"}, "https_enforced": True, "public": True} if self.pages_ativo else None
            if metodo == "DELETE":
                self.pages_ativo = False
                return None
            if metodo == "POST":
                self.pages_ativo = True
                self.arquivos = self.restaurado
                return {"html_url": self.url, "status": "built", "build_type": "legacy", "source": corpo["source"], "https_enforced": True}
            if metodo == "PUT":
                return {"https_enforced": True}
        if recurso == "pages/builds/latest":
            return {"status": "built", "commit": "a" * 40}
        if recurso == "actions/workflows?per_page=100":
            return {"total_count": 3, "workflows": [{"id": i, "name": str(i), "path": str(i), "state": s} for i, s in self.workflow_state.items()]}
        if recurso.startswith("actions/workflows/") and recurso.endswith("/disable"):
            self.workflow_state[int(recurso.split("/")[2])] = "disabled_manually"
            return None
        if recurso.startswith("actions/workflows/") and recurso.endswith("/runs?per_page=100"):
            return {"workflow_runs": []}
        if recurso.startswith("actions/workflows/"):
            i = int(recurso.split("/")[2])
            return {"state": self.workflow_state[i]}
        if recurso == "actions/variables/GEDIV_SITE_ARQUIVADO":
            if any(c[0] == recurso and c[1] in {"PATCH", "POST"} for c in self.chamadas):
                return {"value": "true"}
            return None
        if recurso == "actions/variables" and metodo == "POST":
            return {"name": "GEDIV_SITE_ARQUIVADO", "value": "true"}
        if recurso == "git/ref/heads/gediv-restauracao-":
            return None
        raise AssertionError((recurso, metodo, corpo))

    def http(self, url):
        if url == self.fonte:
            return 200, self.arquivos["dados.json"]
        if not self.pages_ativo:
            return 404, b""
        nome = url.removeprefix(self.url)
        return (200, self.arquivos[nome]) if nome in self.arquivos else (404, b"")

    def preservar_git(self, repo, publicado, destino):
        destino.write_bytes(b"bundle-simulado")
        return dict(self.arquivos)

    def restaurar_git(self, repo, arquivos, pacote_hash):
        self.restaurado = dict(arquivos)
        return "gediv-restauracao-" + pacote_hash[:20]


class TesteControleSites(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        publico = RAIZ / "painel-publico"
        self.arquivos = {p.name: p.read_bytes() for p in publico.iterdir()}
        self.arquivos[".nojekyll"] = b""
        self.url_a = "https://a.github.io/painel-a/"
        self.url_b = "https://b.github.io/painel-b/"
        self.fonte = "https://raw.githubusercontent.com/fonte/gediv/main/dados.json"
        self.registro = {"schema_version": 1, "fonte_oficial": {"id": "fonte", "url": self.fonte}, "sites": [
            {"id": "vencedor", "nome": "Vencedor", "provider": "github_pages", "repo": "a/painel-a", "url": self.url_a, "fonte_id": "fonte", "arquivos_publicos": sorted(self.arquivos), "workflows_publicacao": [10], "workflows_preservados": [20, 30]},
            {"id": "secundario", "nome": "Secundário", "provider": "github_pages", "repo": "b/painel-b", "url": self.url_b, "fonte_id": "fonte", "arquivos_publicos": sorted(self.arquivos), "workflows_publicacao": [10], "workflows_preservados": [20, 30]}
        ]}
        validar_registro(self.registro)
        self.backend = GitHubFalso(self.arquivos, self.url_a, self.fonte)
        # Os sites independentes recebem backend próprio pela troca temporária em cada chamada.
        self.controle = Controle(self.registro, Path(self.tmp.name) / "controle", self.backend)

    def para(self, url):
        self.backend.url = url

    def test_sem_segundo_site_o_cadastro_real_nunca_designa_vencedor(self):
        um = json.loads((RAIZ / "config/sites-gediv.json").read_text(encoding="utf-8"))
        c = Controle(um, Path(self.tmp.name) / "um", self.backend)
        with self.assertRaisesRegex(Recusado, "não designados|cadastrado"):
            c.escolha()

    def test_backup_verificavel_detecta_adulteracao(self):
        self.para(self.url_b)
        arquivo = self.controle.preservar("secundario")
        self.assertEqual(arquivo["manifesto"]["commit_publicado"], "a" * 40)
        pacote = Path(arquivo["pasta"]) / "publicacao.zip"
        pacote.write_bytes(pacote.read_bytes() + b"adulterado")
        with self.assertRaisesRegex(Recusado, "Integridade"):
            self.controle.arquivo(arquivo["id"])

    def test_designacao_recusa_o_mesmo_site_e_arquiva_sem_tocar_workflows_de_dados(self):
        with self.assertRaisesRegex(Recusado, "independentes"):
            self.controle.designar("vencedor", "vencedor")
        self.controle.designar("vencedor", "secundario")
        self.para(self.url_b)
        arquivo = self.controle.preservar("secundario")
        self.assertTrue(Path(arquivo["pasta"]).exists())
        self.assertEqual(self.backend.workflow_state[20], "active")
        self.assertEqual(self.backend.workflow_state[30], "active")

    def test_estatico_recusa_dependencia_externa_e_nao_cria_plano(self):
        self.arquivos["app.js"] += b"\nfetch('https://secundario.invalid/dados.json')"
        self.para(self.url_a)
        with self.assertRaisesRegex(Recusado, "Dependência"):
            self.controle.saude(self.registro["sites"][0], self.registro["sites"][1])

    def test_prova_funcional_exige_todas_as_tarefas_e_hashes_atuais(self):
        self.para(self.url_a)
        saude = self.controle.saude(self.registro["sites"][0], self.registro["sites"][1])
        evidencia = {"verificado_em": datetime.now(timezone.utc).isoformat(), "site_id": "vencedor", "url": self.url_a, "arquivos": saude["arquivos"], "fluxos": {"dados": True}, "evidencias": ["local"]}
        with self.assertRaisesRegex(Recusado, "prova funcional"):
            self.controle.prova_funcional(evidencia, self.registro["sites"][0], saude)

    def test_restauracao_usa_bytes_arquivados_sem_rebuild(self):
        self.para(self.url_b)
        arquivo = self.controle.preservar("secundario")
        self.backend.pages_ativo = False
        self.controle._reativar("plano-simulado", self.registro["sites"][1], arquivo)
        self.assertTrue(self.backend.pages_ativo)
        self.assertEqual(self.backend.restaurado, self.arquivos)
        posts = [c for c in self.backend.chamadas if c[0] == "pages" and c[1] == "POST"]
        self.assertEqual(posts[-1][2]["source"]["path"], "/")


if __name__ == "__main__":
    unittest.main()
