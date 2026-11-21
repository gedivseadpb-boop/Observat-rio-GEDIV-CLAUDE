"""Riscos da entrega estática: origem, arquivos extras, subcaminho e adulteração.

Usa repositórios temporários e projeções vazias; não acessa hospedagem nem dados privados.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from observatorio.painel.publicacao import projetar

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
import preparar_github_pages as pages


class TestePreparacaoPages(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.repo = self.base / "repo"
        publicos = self.repo / "painel-publico"
        publicos.mkdir(parents=True)
        for nome in pages.painel.ASSETS:
            shutil.copyfile(RAIZ / "painel-publico" / nome, publicos / nome)
        (publicos / "dados.json").write_bytes((json.dumps(projetar([]), ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        self.git("init", "-q", "-b", pages.BRANCH)
        self.git("config", "user.name", "Teste local")
        self.git("config", "user.email", "teste@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.commit()
        self.saida = self.base / "entrega"
        self.addCleanup(patch.stopall)
        patch.object(pages, "RAIZ", self.repo).start()
        patch.object(pages.painel, "RAIZ", self.repo).start()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "Origem do teste")

    def test_pacote_reproduzivel_somente_arquivos_publicos_e_commit_correto(self):
        a = pages.preparar(self.saida)
        b = pages.preparar(self.base / "segunda")
        self.assertEqual(a, b)
        self.assertEqual(a["commit"], self.git("rev-parse", "HEAD"))
        self.assertFalse(a["publicado"])
        self.assertEqual(pages.verificar(self.saida), a)
        with zipfile.ZipFile(self.saida / pages.PACOTE) as z:
            self.assertEqual(set(z.namelist()), pages.ARQUIVOS)
            self.assertNotIn(pages.MANIFESTO, z.namelist())
            self.assertEqual(z.read("dados.json"), (self.repo / "painel-publico/dados.json").read_bytes())

    def test_recusa_alteracoes_nao_registradas_e_branch_nao_autorizada(self):
        alvo = self.repo / "painel-publico/app.js"
        alvo.write_bytes(alvo.read_bytes() + b"\n// ALTERACAO LOCAL\n")
        with self.assertRaisesRegex(ValueError, "alterações"):
            pages.preparar(self.saida)
        self.git("checkout", "--", "painel-publico/app.js")
        self.git("branch", "-m", "main")
        with self.assertRaisesRegex(ValueError, "branch"):
            pages.preparar(self.saida)
        self.assertFalse(self.saida.exists())

    def test_recusa_arquivo_extra_mesmo_versionado_sem_apagar_entrega_anterior(self):
        pages.preparar(self.saida)
        (self.repo / "painel-publico/privado.txt").write_text("MARCADOR PRIVADO FICTICIO", encoding="utf-8")
        self.commit()
        with self.assertRaisesRegex(ValueError, "não permitidos"):
            pages.preparar(self.base / "outra")
        pages.verificar(self.saida)
        with self.assertRaisesRegex(ValueError, "pasta nova"):
            pages.preparar(self.saida)

    def test_detecta_adulteracao_na_distribuicao_e_no_zip(self):
        pages.preparar(self.saida)
        alvo = self.saida / "site/dados.json"
        antes = alvo.read_bytes()
        alvo.write_bytes(antes + b" ")
        with self.assertRaisesRegex(ValueError, "hashes"):
            pages.verificar(self.saida)
        alvo.write_bytes(antes)
        with zipfile.ZipFile(self.saida / pages.PACOTE, "a") as z:
            z.writestr("base-privada.sqlite3", b"MARCADOR PRIVADO FICTICIO")
        with self.assertRaisesRegex(ValueError, "ZIP"):
            pages.verificar(self.saida)

    def test_recusa_recurso_na_raiz_do_dominio_e_cache_sem_hash(self):
        alvo = self.repo / "painel-publico/index.html"
        html = alvo.read_text(encoding="utf-8")
        alvo.write_text(html.replace('src="./app.js?', 'src="/app.js?'), encoding="utf-8")
        self.commit()
        with self.assertRaisesRegex(ValueError, "subdiretório"):
            pages.preparar(self.saida)
        pasta = self.repo / "painel-publico"
        (pasta / ".nojekyll").write_bytes(b"")
        alvo.write_text(html.replace('src="./app.js?v=', 'src="./app.js?antigo='), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "versão de conteúdo"):
            pages.validar_recursos(pasta)

    def test_recusa_campo_privado_na_projecao_versionada(self):
        alvo = self.repo / "painel-publico/dados.json"
        dados = json.loads(alvo.read_text(encoding="utf-8"))
        dados["processo"] = "MARCADOR PRIVADO FICTICIO"
        alvo.write_text(json.dumps(dados), encoding="utf-8")
        self.commit()
        with self.assertRaisesRegex(ValueError, "contrato público"):
            pages.preparar(self.saida)
        self.assertFalse(self.saida.exists())

    def test_manifesto_nao_pode_afirmar_cobertura_diferente_do_json(self):
        pages.preparar(self.saida)
        arquivo = self.saida / pages.MANIFESTO
        manifesto = json.loads(arquivo.read_text(encoding="utf-8"))
        manifesto["projecao"]["cobertura"]["historico_completo"] = True
        arquivo.write_text(json.dumps(manifesto), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Metadados"):
            pages.verificar(self.saida)


if __name__ == "__main__":
    unittest.main()
