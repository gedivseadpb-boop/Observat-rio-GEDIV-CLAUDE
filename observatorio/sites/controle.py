"""Despublicação reversível de GitHub Pages. Nenhuma mutação em importação/preparação.

Credenciais são usadas exclusivamente pelo gh/Git; nunca entram no arquivo preservado.
O provedor Sites não tem adaptador de despublicação neste módulo: falha fechada.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
import zipfile

from scripts.preparar_painel_publico import validar_snapshot

RAIZ = Path(__file__).resolve().parents[2]
REGISTRO = RAIZ / "config/sites-gediv.json"
PRIVADO = "gediv-conferencia-privada-20261031.ylenaluna.chatgpt.site"
VARIAVEL = "GEDIV_SITE_ARQUIVADO"


class Recusado(RuntimeError):
    """Operação não segura, incompleta ou sem autorização específica."""


def agora():
    return datetime.now(timezone.utc).isoformat()


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def assinatura(obj) -> str:
    return digest(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def gravar(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=p.parent, delete=False) as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
        nome = f.name
    os.replace(nome, p)
    p.chmod(0o600)


def ler(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def seguro(nome):
    if (not isinstance(nome, str) or not nome or "\\" in nome or "\x00" in nome
            or PurePosixPath(nome).is_absolute() or any(x in {"", ".", ".."} for x in nome.split("/"))):
        raise Recusado("Caminho de arquivo não permitido.")
    return nome


def validar_registro(registro):
    if registro.get("schema_version") != 1 or not 1 <= len(registro.get("sites", [])) <= 2:
        raise Recusado("Registre um ou dois sites, sem escolher vencedor automaticamente.")
    fonte = urlsplit(registro["fonte_oficial"]["url"])
    if fonte.scheme != "https" or fonte.hostname != "raw.githubusercontent.com" or fonte.query or fonte.fragment or fonte.username:
        raise Recusado("A fonte pública oficial precisa ser independente das hospedagens.")
    ids, repos, urls = set(), set(), set()
    for s in registro["sites"]:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", s["id"]) or s["id"] in ids:
            raise Recusado("Identificador de site ausente ou duplicado.")
        u = urlsplit(s["url"])
        if u.hostname == PRIVADO or u.scheme != "https" or u.username or u.query or u.fragment:
            raise Recusado("URL protegida ou incompatível com este controle.")
        if s["url"] in urls or s["fonte_id"] != registro["fonte_oficial"]["id"]:
            raise Recusado("Os sites precisam da mesma fonte oficial e endereços independentes.")
        if s["provider"] == "github_pages":
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", s["repo"]):
                raise Recusado("Repositório GitHub inválido.")
            owner, repo = s["repo"].split("/")
            if s["repo"].lower() in repos:
                raise Recusado("Dois Pages no mesmo repositório não são publicações independentes.")
            esperado = f"https://{owner.lower()}.github.io/{repo}/"
            if s["url"] != esperado:
                raise Recusado("Este adaptador exige a URL de projeto github.io, sem domínio compartilhado.")
            repos.add(s["repo"].lower())
            nomes = s["arquivos_publicos"]
            if len(nomes) != len(set(nomes)) or not {"index.html", "dados.json", ".nojekyll"}.issubset(nomes):
                raise Recusado("Inventário público incompleto ou duplicado.")
            for nome in nomes:
                seguro(nome)
                if nome != ".nojekyll" and (any(x.startswith(".") for x in nome.split("/")) or nome.endswith((".bundle", ".sqlite3", ".env"))):
                    raise Recusado("Arquivo privado ou de administração na lista publicável.")
            p, d = s["workflows_publicacao"], s["workflows_preservados"]
            if not p or set(p) & set(d) or any(type(i) is not int or i <= 0 for i in p + d):
                raise Recusado("Separe workflows de publicação dos fluxos preservados de dados/testes.")
        ids.add(s["id"])
        urls.add(s["url"])


class GitHub:
    """Único transporte de produção; não aceita host/API alternativo ou token na linha de comando."""

    def api(self, repo, recurso="", metodo="GET", corpo=None, ausente=False):
        endpoint = "repos/" + repo + ("/" + recurso if recurso else "")
        comando = ["gh", "api", "--method", metodo, endpoint]
        if corpo is not None:
            comando += ["--input", "-"]
        r = subprocess.run(comando, input=json.dumps(corpo) if corpo is not None else None,
                           text=True, capture_output=True)
        if r.returncode:
            if ausente and "(HTTP 404)" in r.stderr:
                return None
            # Não imprimir respostas brutas de autenticação, configuração ou ambiente.
            codigo = re.search(r"HTTP (\d{3})", r.stderr)
            motivo = "HTTP " + codigo[1] if codigo else "falha no gh/autenticação"
            raise Recusado(f"GitHub recusou {metodo} {recurso or 'repositório'}: {motivo}. Nenhuma credencial será solicitada em texto.")
        return json.loads(r.stdout) if r.stdout.strip() else None

    def http(self, url):
        try:
            with urlopen(Request(url, headers={"Cache-Control": "no-cache"}), timeout=25) as r:
                if r.url != url:
                    raise Recusado("Redirecionamento inesperado no site ou fonte oficial.")
                b = r.read(32 * 1024 * 1024 + 1)
                if len(b) > 32 * 1024 * 1024:
                    raise Recusado("Recurso excede o limite de conferência.")
                return r.status, b
        except HTTPError as e:
            return e.code, b""

    def preservar_git(self, repo, publicado, destino):
        def git(*args):
            r = subprocess.run(["git", *map(str, args)], capture_output=True)
            if r.returncode:
                raise Recusado("Não foi possível preservar/verificar o histórico Git. A publicação não será alterada.")
            return r.stdout
        with tempfile.TemporaryDirectory(prefix="gediv-historico-") as tmp:
            espelho = Path(tmp) / "repo.git"
            git("clone", "--mirror", "--", "https://github.com/" + repo + ".git", espelho)
            git("-C", espelho, "cat-file", "-e", publicado + "^{commit}")
            git("-C", espelho, "bundle", "create", destino, "--all")
            git("-C", espelho, "bundle", "verify", destino)
            tree = git("-C", espelho, "ls-tree", "-rz", publicado).split(b"\x00")
            arquivos = {}
            for item in filter(None, tree):
                meta, caminho = item.split(b"\t", 1)
                modo, tipo, blob = meta.split()
                nome = seguro(caminho.decode("utf-8"))
                if modo != b"100644" or tipo != b"blob":
                    raise Recusado("Publicação com link, submódulo ou modo não suportado.")
                arquivos[nome] = git("-C", espelho, "cat-file", "blob", blob.decode())
            return arquivos

    def restaurar_git(self, repo, arquivos, pacote_hash):
        branch = "gediv-restauracao-" + pacote_hash[:20]
        # Uma referência existente precisa corresponder aos mesmos blobs; nunca é sobrescrita.
        ref = self.api(repo, "git/ref/heads/" + branch, ausente=True)
        esperado = {n: hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest() for n, b in arquivos.items()}
        if ref:
            commit = self.api(repo, "git/commits/" + ref["object"]["sha"])
            tree = self.api(repo, "git/trees/" + commit["tree"]["sha"] + "?recursive=1")
            blobs = {x["path"]: x["sha"] for x in tree["tree"] if x["type"] == "blob"}
            if tree.get("truncated") or blobs != esperado or any(x["mode"] not in {"100644", "040000"} for x in tree["tree"]):
                raise Recusado("A referência de restauração existente diverge do arquivo preservado.")
            return branch
        entradas = []
        for nome, b in sorted(arquivos.items()):
            blob = self.api(repo, "git/blobs", "POST", {"content": base64.b64encode(b).decode(), "encoding": "base64"})
            if blob["sha"] != esperado[nome]:
                raise Recusado("Blob remoto não corresponde ao pacote preservado.")
            entradas.append({"path": nome, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = self.api(repo, "git/trees", "POST", {"tree": entradas})
        commit = self.api(repo, "git/commits", "POST", {"message": "Restaura pacote GEDIV " + pacote_hash, "tree": tree["sha"], "parents": []})
        self.api(repo, "git/refs", "POST", {"ref": "refs/heads/" + branch, "sha": commit["sha"]})
        return branch


class Recursos(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in {"script", "img", "iframe", "source"} and a.get("src"):
            self.urls.append(a["src"])
        if tag == "link" and a.get("href") and a.get("rel") in {"stylesheet", "preload", "modulepreload"}:
            self.urls.append(a["href"])


def validar_estatico(arquivos, site, secundario=None):
    if set(arquivos) != set(site["arquivos_publicos"]) or arquivos.get(".nojekyll") != b"":
        raise Recusado("Árvore publicada não corresponde ao inventário estático completo.")
    dados = json.loads(arquivos["dados.json"].decode())
    validar_snapshot(dados)
    parser = Recursos()
    parser.feed(arquivos["index.html"].decode())
    urls = parser.urls + ["./dados.json"]
    for nome, b in arquivos.items():
        if nome.endswith((".html", ".js", ".css", ".json")):
            texto = b.decode("utf-8")
            if secundario and urlsplit(secundario["url"]).netloc in texto:
                raise Recusado("O vencedor referencia o endereço do secundário.")
            if nome.endswith(".js"):
                chamadas = list(re.finditer(r"\bfetch\s*\(", texto))
                literais = list(re.finditer(r"\bfetch\s*\(\s*(['\"])([^'\"]+)\1", texto))
                if len(chamadas) != len(literais) or any(m[2] != "./dados.json" for m in literais):
                    raise Recusado("Dependência dinâmica ou externa não comprovada; revise antes de desativar.")
                if re.search(r"\b(XMLHttpRequest|WebSocket|EventSource|sendBeacon|serviceWorker)\b|\bimport\s*(?:\(|[{'\"])", texto):
                    raise Recusado("Integração de rede exige verificação específica; não se presume independência.")
            if nome.endswith(".css"):
                if "@import" in texto:
                    raise Recusado("Importação CSS externa não inventariada.")
                urls += re.findall(r"url\(\s*['\"]?([^)'\"]+)", texto)
    for url in urls:
        if url.startswith(("data:", "#")):
            continue
        if not url.startswith("./") or seguro(url.split("?", 1)[0][2:]) not in arquivos:
            raise Recusado("Recurso externo, ausente ou dependente de outra hospedagem.")
    return dados


class Controle:
    def __init__(self, registro, pasta: Path, backend=None):
        validar_registro(registro)
        self.registro = registro
        self.pasta = pasta.resolve()
        if self.pasta == RAIZ or RAIZ in self.pasta.parents:
            raise Recusado("Arquivos administrativos e backups devem ficar fora do repositório público.")
        self.pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.backend = backend or GitHub()

    def site(self, id):
        encontrado = next((s for s in self.registro["sites"] if s["id"] == id), None)
        if not encontrado:
            raise Recusado("Site não cadastrado; nenhum alvo será inferido.")
        return encontrado

    def pages(self, site):
        if site["provider"] != "github_pages":
            raise Recusado("Despublicação disponível somente para GitHub Pages; outro provedor exige adaptador e autorização próprios.")
        return self.backend.api(site["repo"], "pages", ausente=True)

    @contextmanager
    def trava(self):
        lock = self.pasta / "operacao.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise Recusado("Outra operação está em andamento ou requer conciliação. Não remova a trava sem conferir o diário.")
        os.close(fd)
        try:
            yield
        finally:
            lock.unlink()

    def evento(self, operacao, etapa, **campos):
        p = self.pasta / "diario.jsonl"
        anterior = digest(p.read_bytes()) if p.exists() else None
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"em": agora(), "operacao": operacao, "etapa": etapa,
                                "anterior_sha256": anterior, **campos}, ensure_ascii=False) + "\n")
        p.chmod(0o600)

    def designar(self, vencedor, secundario):
        a, b = self.site(vencedor), self.site(secundario)
        if a["id"] == b["id"] or a["provider"] != "github_pages" or b["provider"] != "github_pages" or a["repo"].lower() == b["repo"].lower():
            raise Recusado("Designe dois GitHub Pages em repositórios independentes. Não há vencedor presumido.")
        if (self.pasta / "estado.json").exists() and ler(self.pasta / "estado.json").get("situacao") != "ativo":
            raise Recusado("Conclua ou concilie a operação anterior antes de trocar os papéis.")
        escolha = {"vencedor": vencedor, "secundario": secundario, "registro_sha256": assinatura(self.registro)}
        gravar(self.pasta / "escolha.json", escolha)
        return escolha

    def escolha(self):
        p = self.pasta / "escolha.json"
        if not p.exists():
            raise Recusado("Vencedor e secundário ainda não designados pela responsável.")
        e = ler(p)
        if e["registro_sha256"] != assinatura(self.registro):
            raise Recusado("O cadastro mudou; confirme novamente a designação.")
        return e, self.site(e["vencedor"]), self.site(e["secundario"])

    def saude(self, site, secundario=None):
        paginas = self.pages(site)
        if not paginas or paginas["status"] != "built" or not paginas.get("https_enforced") or paginas["html_url"] != site["url"]:
            raise Recusado("Site sem publicação HTTPS acessível e concluída.")
        arquivos = {".nojekyll": b""}
        for nome in site["arquivos_publicos"]:
            if nome == ".nojekyll":
                continue
            status, b = self.backend.http(urljoin(site["url"], nome))
            if status != 200:
                raise Recusado("Site ou recurso sem HTTP 200: " + nome)
            arquivos[nome] = b
        dados = validar_estatico(arquivos, site, secundario)
        status, fonte = self.backend.http(self.registro["fonte_oficial"]["url"])
        if status != 200 or fonte != arquivos["dados.json"]:
            raise Recusado("A projeção do site não corresponde à fonte oficial independente.")
        return {"arquivos": {n: digest(b) for n, b in sorted(arquivos.items())},
                "dados_atualizados_em": dados["atualizado_em"], "cobertura": dados["cobertura"],
                "fonte_id": site["fonte_id"]}

    def preservar(self, id):
        site = self.site(id)
        pages = self.pages(site)
        if not pages or pages.get("build_type") != "legacy" or pages["source"]["path"] != "/":
            raise Recusado("Preservação automática exige Pages estático por branch na raiz, sem rebuild externo.")
        saude = self.saude(site)
        build = self.backend.api(site["repo"], "pages/builds/latest")
        if build["status"] != "built" or not re.fullmatch(r"[0-9a-f]{40}", build["commit"]):
            raise Recusado("Não foi possível determinar o commit da última publicação concluída.")
        workflows = self.backend.api(site["repo"], "actions/workflows?per_page=100")
        if workflows["total_count"] != len(workflows["workflows"]):
            raise Recusado("Inventário de workflows incompleto; não se pode congelar a publicação.")
        conhecidos = set(site["workflows_publicacao"] + site["workflows_preservados"])
        if {w["id"] for w in workflows["workflows"]} != conhecidos:
            raise Recusado("Há workflow novo/ausente não classificado; revise o cadastro sem interromper a coleta.")
        with tempfile.TemporaryDirectory(prefix="gediv-preservar-", dir=self.pasta) as tmp:
            t = Path(tmp)
            arquivos = self.backend.preservar_git(site["repo"], build["commit"], t / "historico.bundle")
            validar_estatico(arquivos, site)
            if {n: digest(b) for n, b in sorted(arquivos.items())} != saude["arquivos"]:
                raise Recusado("Código e publicação divergentes; não se afirma ter preservado a versão no ar.")
            with zipfile.ZipFile(t / "publicacao.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for nome, b in sorted(arquivos.items()):
                    info = zipfile.ZipInfo(nome, (1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    z.writestr(info, b)
            configuracao = {k: pages.get(k) for k in ("html_url", "source", "build_type", "https_enforced", "cname", "public")}
            gravar(t / "configuracao.json", {"pages": configuracao, "workflows": [{k: w[k] for k in ("id", "name", "path", "state")} for w in workflows["workflows"]]})
            gravar(t / "ORIGEM.json", {"site": site, "fonte_oficial": self.registro["fonte_oficial"], "commit_publicado": build["commit"]})
            manifesto = {"schema_version": 1, "site_id": id, "em": agora(), "commit_publicado": build["commit"],
                         "saude": saude, "registro_sha256": assinatura(self.registro),
                         "arquivos": {p.name: digest(p.read_bytes()) for p in t.iterdir()}}
            arquivo_id = assinatura(manifesto)
            gravar(t / "manifesto.json", manifesto)
            destino = self.pasta / "arquivos" / arquivo_id
            destino.parent.mkdir(exist_ok=True, mode=0o700)
            t.rename(destino)
            for p in destino.iterdir():
                p.chmod(0o600)
        self.evento("preservar", "verificado", site=id, arquivo_id=arquivo_id)
        return self.arquivo(arquivo_id)

    def arquivo(self, id):
        if not re.fullmatch(r"[0-9a-f]{64}", id):
            raise Recusado("Identificador de arquivo inválido.")
        pasta = self.pasta / "arquivos" / id
        m = ler(pasta / "manifesto.json")
        if assinatura(m) != id or {p.name for p in pasta.iterdir()} != set(m["arquivos"]) | {"manifesto.json"}:
            raise Recusado("Arquivo preservado ou inventário adulterado.")
        for nome, h in m["arquivos"].items():
            p = pasta / seguro(nome)
            if p.is_symlink() or not p.is_file() or digest(p.read_bytes()) != h:
                raise Recusado("Integridade da cópia preservada não confere.")
        with zipfile.ZipFile(pasta / "publicacao.zip") as z:
            if len(z.namelist()) != len(set(z.namelist())):
                raise Recusado("Arquivo ZIP duplicado.")
            arquivos = {seguro(n): z.read(n) for n in z.namelist()}
        origem = ler(pasta / "ORIGEM.json")
        validar_estatico(arquivos, origem["site"])
        return {"id": id, "manifesto": m, "pasta": str(pasta)}

    def prova_funcional(self, evidencia, site, saude):
        exigidos = {"dados", "graficos", "filtros", "tabelas", "navegacao", "exportacoes"}
        try:
            data = datetime.fromisoformat(evidencia["verificado_em"])
            idade = datetime.now(timezone.utc) - data
            valido = (timedelta(0) <= idade <= timedelta(hours=1) and evidencia["site_id"] == site["id"]
                      and evidencia["url"] == site["url"] and evidencia["arquivos"] == saude["arquivos"]
                      and set(evidencia["fluxos"]) == exigidos and all(v is True for v in evidencia["fluxos"].values())
                      and bool(evidencia["evidencias"]))
        except (KeyError, ValueError, TypeError):
            valido = False
        if not valido:
            raise Recusado("Falta prova funcional recente do vencedor, vinculada aos hashes no ar. HTTP sozinho não comprova filtros/gráficos.")

    def preparar(self, operacao, evidencia=None):
        if operacao not in {"desativar", "reativar"}:
            raise Recusado("Operação desconhecida.")
        escolha, vencedor, secundario = self.escolha()
        saude = self.saude(vencedor, secundario)
        self.prova_funcional(evidencia or {}, vencedor, saude)
        estado = ler(self.pasta / "estado.json") if (self.pasta / "estado.json").exists() else {"situacao": "ativo"}
        if operacao == "desativar":
            if estado["situacao"] != "ativo":
                raise Recusado("O secundário não está em estado ativo confirmado.")
            arquivo = self.preservar(secundario["id"])
        else:
            if estado["situacao"] != "arquivado" or self.pages(secundario) is not None:
                raise Recusado("A reativação exige arquivo registrado e Pages despublicado.")
            arquivo = self.arquivo(estado["arquivo_id"])
        planos = {"versao": 1, "operacao": operacao, "escolha": escolha, "vencedor": vencedor,
                  "secundario": secundario, "arquivo_id": arquivo["id"], "saude_vencedor": saude,
                  "evidencia_funcional_sha256": assinatura(evidencia), "criado_em": agora(),
                  "expira_em": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
        id = assinatura(planos)
        gravar(self.pasta / "planos" / (id + ".json"), planos)
        return {"plano_id": id, **planos, "autorizacao": "A responsável deve aprovar esta operação, estes endereços e esta versão preservada."}

    def executar(self, plano_id, autorizacao, evidencia):
        if not re.fullmatch(r"[0-9a-f]{64}", plano_id):
            raise Recusado("Plano inválido.")
        plano = ler(self.pasta / "planos" / (plano_id + ".json"))
        if assinatura(plano) != plano_id or datetime.fromisoformat(plano["expira_em"]) < datetime.now(timezone.utc):
            raise Recusado("Plano alterado ou expirado; prepare uma proposta atual.")
        if (autorizacao.get("plano_id") != plano_id or autorizacao.get("operacao") != plano["operacao"]
                or autorizacao.get("autorizado") is not True or not autorizacao.get("referencia_mensagem_usuario")):
            raise Recusado("Falta autorização específica da responsável para este plano. Não se aceita confirmação genérica.")
        escolha, vencedor, secundario = self.escolha()
        if escolha != plano["escolha"]:
            raise Recusado("O site vencedor mudou; nenhuma publicação será alterada.")
        if vencedor["id"] == secundario["id"]:
            raise Recusado("O vencedor nunca pode ser o alvo.")
        with self.trava():
            arquivo = self.arquivo(plano["arquivo_id"])
            if arquivo["manifesto"]["site_id"] != secundario["id"] or arquivo["manifesto"]["registro_sha256"] != assinatura(self.registro):
                raise Recusado("Arquivo de outro site ou cadastro alterado.")
            atual = self.saude(vencedor, secundario)
            if atual != plano["saude_vencedor"]:
                raise Recusado("O vencedor ou seus dados mudaram; refaça os testes e o plano.")
            self.prova_funcional(evidencia, vencedor, atual)
            if assinatura(evidencia) != plano["evidencia_funcional_sha256"]:
                raise Recusado("Prova funcional diverge da proposta aprovada.")
            self.evento(plano_id, "autorizado", alvo=secundario["id"], autorizacao=autorizacao)
            try:
                if plano["operacao"] == "desativar":
                    self._desativar(plano_id, secundario, arquivo)
                else:
                    self._reativar(plano_id, secundario, arquivo)
                if self.saude(vencedor, secundario) != atual:
                    raise Recusado("O vencedor mudou durante a execução; estado não será declarado concluído.")
            except Exception:
                self.evento(plano_id, "requer_conciliacao", alvo=secundario["id"])
                # Uma falha nunca autoriza republicar, apagar ou trocar o alvo automaticamente.
                raise
            estado = {"situacao": "arquivado" if plano["operacao"] == "desativar" else "ativo",
                      "arquivo_id": arquivo["id"], "ultimo_plano": plano_id, "em": agora()}
            gravar(self.pasta / "estado.json", estado)
            self.evento(plano_id, "concluido", **estado)
            return estado

    def _desativar(self, plano, site, arquivo):
        repo = site["repo"]
        cfg = ler(Path(arquivo["pasta"]) / "configuracao.json")
        pages = self.pages(site)
        build = self.backend.api(repo, "pages/builds/latest")
        if not pages or {k: pages.get(k) for k in cfg["pages"]} != cfg["pages"] or build["commit"] != arquivo["manifesto"]["commit_publicado"]:
            raise Recusado("A publicação secundária mudou desde a preservação; faça novo plano.")
        workflows = self.backend.api(repo, "actions/workflows?per_page=100")
        if {w["id"] for w in workflows["workflows"]} != set(site["workflows_publicacao"] + site["workflows_preservados"]):
            raise Recusado("Workflows mudaram desde a preparação.")
        gravar(self.pasta / "estado.json", {"situacao": "desativando", "arquivo_id": arquivo["id"], "ultimo_plano": plano})
        # Trava remota para os workflows que adotam o contrato; não modifica a fonte de dados.
        var = self.backend.api(repo, "actions/variables/" + VARIAVEL, ausente=True)
        self.backend.api(repo, "actions/variables/" + VARIAVEL if var else "actions/variables", "PATCH" if var else "POST", {"name": VARIAVEL, "value": "true"})
        for id in site["workflows_publicacao"]:
            self.backend.api(repo, f"actions/workflows/{id}/disable", "PUT")
            if self.backend.api(repo, f"actions/workflows/{id}")["state"] != "disabled_manually":
                raise Recusado("Não foi possível congelar uma automação de publicação; Pages mantido.")
            runs = self.backend.api(repo, f"actions/workflows/{id}/runs?per_page=100")
            if any(r["status"] != "completed" for r in runs["workflow_runs"]):
                raise Recusado("Há publicação em andamento. Aguarde e concilie o estado; nada será despublicado agora.")
        if self.backend.api(repo, "actions/variables/" + VARIAVEL)["value"] != "true":
            raise Recusado("Trava remota não confirmada; Pages mantido.")
        self.evento(plano, "automacoes_secundarias_congeladas")
        self.backend.api(repo, "pages", "DELETE")
        if self.pages(site) is not None:
            raise Recusado("GitHub ainda informa publicação ativa.")
        codigo, _ = self.backend.http(site["url"])
        if codigo not in {404, 410}:
            raise Recusado("Despublicação solicitada; cache/CDN ainda não confirmou retirada. Concilie, sem repetir exclusões.")

    def _reativar(self, plano, site, arquivo):
        if self.pages(site) is not None:
            raise Recusado("Já existe publicação; não será substituída.")
        gravar(self.pasta / "estado.json", {"situacao": "reativando", "arquivo_id": arquivo["id"], "ultimo_plano": plano})
        pasta = Path(arquivo["pasta"])
        with zipfile.ZipFile(pasta / "publicacao.zip") as z:
            arquivos = {nome: z.read(nome) for nome in z.namelist()}
        branch = self.backend.restaurar_git(site["repo"], arquivos, arquivo["manifesto"]["arquivos"]["publicacao.zip"])
        # A restauração é da cópia exata, nunca de HEAD/main nem de um build novo.
        self.backend.api(site["repo"], "pages", "POST", {"source": {"branch": branch, "path": "/"}, "build_type": "legacy"})
        self.evento(plano, "restauracao_solicitada", branch=branch)
        # A implantação e o CDN podem demorar. Conciliação posterior conclui a operação.
        self.confirmar_restauracao(site, arquivo)

    def confirmar_restauracao(self, site, arquivo):
        pages = self.pages(site)
        if not pages or pages.get("status") != "built":
            raise Recusado("Restauração solicitada, implantação ainda pendente. Use conciliar; não crie outra publicação.")
        if not pages.get("https_enforced"):
            self.backend.api(site["repo"], "pages", "PUT", {"https_enforced": True})
        # Confere a versão arquivada mesmo se a fonte oficial tiver avançado depois.
        for nome, h in arquivo["manifesto"]["saude"]["arquivos"].items():
            if nome != ".nojekyll":
                codigo, b = self.backend.http(urljoin(site["url"], nome))
                if codigo != 200 or digest(b) != h:
                    raise Recusado("CDN/versão restaurada ainda não corresponde ao arquivo. Use conciliar.")

    def conciliar(self):
        """Conclui uma operação já autorizada. Não despublica nem inicia outra implantação."""
        _, vencedor, secundario = self.escolha()
        with self.trava():
            estado = ler(self.pasta / "estado.json")
            arquivo = self.arquivo(estado["arquivo_id"])
            self.saude(vencedor, secundario)
            if estado["situacao"] == "desativando":
                if self.pages(secundario) is not None or self.backend.http(secundario["url"])[0] not in {404, 410}:
                    raise Recusado("Retirada não confirmada. Verifique o diário; não se presume que DELETE tenha ocorrido.")
                estado["situacao"] = "arquivado"
            elif estado["situacao"] == "reativando":
                self.confirmar_restauracao(secundario, arquivo)
                estado["situacao"] = "ativo"
            else:
                return estado
            estado["em"] = agora()
            gravar(self.pasta / "estado.json", estado)
            self.evento(estado["ultimo_plano"], "conciliado", **estado)
            return estado

    def verificar(self):
        resultado = {"escolha": ler(self.pasta / "escolha.json") if (self.pasta / "escolha.json").exists() else None,
                     "estado_local": ler(self.pasta / "estado.json") if (self.pasta / "estado.json").exists() else None, "sites": []}
        for site in self.registro["sites"]:
            item = {k: site[k] for k in ("id", "nome", "provider", "url")}
            try:
                pages = self.pages(site)
                item["publicacao"] = "ativa" if pages else "despublicada"
                item["configuracao"] = {k: pages.get(k) for k in ("status", "source", "https_enforced")} if pages else None
                if pages:
                    item["dados"] = self.saude(site)
                    build = self.backend.api(site["repo"], "pages/builds/latest")
                    item["versao_publicada"] = build["commit"]
            except (Recusado, OSError, ValueError) as e:
                item["verificacao"] = str(e)
                item.setdefault("publicacao", "não verificada")
            resultado["sites"].append(item)
        resultado["segundo_site_pendente"] = len(self.registro["sites"]) != 2
        return resultado


def carregar_registro(caminho=REGISTRO):
    registro = ler(Path(caminho))
    validar_registro(registro)
    return registro
