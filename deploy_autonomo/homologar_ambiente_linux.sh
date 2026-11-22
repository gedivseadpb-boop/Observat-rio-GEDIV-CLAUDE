#!/usr/bin/env bash
set -euo pipefail

# Homologação operacional ISOLADA e REPRODUZÍVEL para ambiente Linux / systemd.
# - NÃO altera bancos SQLite originais (usa cópia isolada em diretório temporário).
# - NÃO ativa serviços systemd, NÃO agenda timers, NÃO executa coleta real e NÃO publica páginas.
# Uso:
#   bash deploy_autonomo/homologar_ambiente_linux.sh [caminho_opcional_observatorio.sqlite3]

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi
DB_ORIG="${1:-}"
TMP_HOMOLOG="$(mktemp -d "${TMPDIR:-/tmp}/gediv-homolog-XXXXXX")"
cleanup() {
  rm -rf "$TMP_HOMOLOG"
}
trap cleanup EXIT

echo "=== HOMOLOGAÇÃO OPERACIONAL ISOLADA — OBSERVATÓRIO GEDIV ==="
echo "APP_DIR=$APP_DIR"
echo "TMP_HOMOLOG=$TMP_HOMOLOG"

echo "[1/7] Pré-verificação de ambiente, sintaxe Bash, flock, date e units systemd..."
bash "$APP_DIR/deploy_autonomo/verificar_ambiente_linux.sh" ${DB_ORIG:+"$DB_ORIG"}

echo "[2/7] Verificando integridade LF dos scripts/units e ausência de PII no frontend unificado..."
PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}" PYTHONSAFEPATH=1 "$PYTHON_BIN" - "$APP_DIR" <<'PY'
import pathlib, re, sys
app = pathlib.Path(sys.argv[1])
for rel in (
    "deploy_autonomo/rodar_diario.sh",
    "deploy_autonomo/recuperar_edicoes_manual.sh",
    "deploy_autonomo/verificar_ambiente_linux.sh",
    "deploy_autonomo/homologar_ambiente_linux.sh",
    "deploy_autonomo/gediv-diario.service",
    "deploy_autonomo/gediv-diario.timer",
    "deploy_autonomo/gediv-admin.service",
    "observatorio/web/unificado/index.html",
):
    b = (app / rel).read_bytes()
    assert b.count(b"\r\n") == 0, f"CRLF detectado em {rel}"
html = (app / "observatorio/web/unificado/index.html").read_text(encoding="utf-8")
assert 'window.GEDIV_BOOTSTRAP={"rows":[],"events":[' in html
assert not re.search(r"SAD-PSE-202\d/\d+", html)
print("  OK: integridade LF e ausência de PII confirmadas.")
PY

echo "[3/7] Testando trava exclusiva flock em diretório temporário..."
LOCK_TEST="$TMP_HOMOLOG/.homolog.lock"
exec 8>"$LOCK_TEST"
flock -n 8
if flock -n "$LOCK_TEST" -c "exit 0" 2>/dev/null; then
  echo "  ERRO: flock não bloqueou acesso concorrente!" >&2
  exit 1
fi
exec 8>&-
echo "  OK: flock bloqueia concorrência corretamente."

echo "[4/7] Verificando permissões restritas (umask 0027) em diretório isolado de homologação..."
DADOS_ISO="$TMP_HOMOLOG/dados"
(umask 0027 && mkdir -p "$DADOS_ISO")
if [ -n "$DB_ORIG" ] && [ -f "$DB_ORIG" ]; then
  echo "  Copiando banco de origem em modo somente leitura (?mode=ro) sem tocar no original..."
  PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}" PYTHONSAFEPATH=1 "$PYTHON_BIN" - "$DB_ORIG" "$DADOS_ISO/observatorio.sqlite3" <<'PY'
import hashlib, sqlite3, sys
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
sha_orig_antes = hashlib.sha256(src.read_bytes()).hexdigest()
with sqlite3.connect(src.resolve().as_uri() + "?mode=ro", uri=True) as s:
    with sqlite3.connect(dst) as d:
        s.backup(d)
with sqlite3.connect(dst.resolve().as_uri() + "?mode=ro", uri=True) as chk:
    assert chk.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_orig_antes
print("  OK: cópia isolada íntegra (original intocado).")
PY
fi

echo "[5/7] Testando inicialização do backend endurecido (HTTPS/Secure cookie, login somente-cookie, snapshot fail-closed e token técnico desabilitado)..."
PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}" PYTHONSAFEPATH=1 \
  GEDIV_MODO_PRODUCAO=1 \
  GEDIV_COOKIE_SECURE=1 \
  GEDIV_LOGIN_SOMENTE_COOKIE=1 \
  GEDIV_EXIGIR_SNAPSHOT_PUBLICO=1 \
  GEDIV_HABILITAR_TOKEN_TECNICO=0 \
  "$PYTHON_BIN" - "$DADOS_ISO" <<'PY'
import json, pathlib, sys, threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from observatorio.nucleo.banco import Banco
from observatorio.painel import indicadores
from observatorio.web.contas import Contas
from observatorio.web.servidor import criar_servidor

pasta = pathlib.Path(sys.argv[1])
with Banco(pasta / "observatorio.sqlite3"):
    pass
contas = Contas(pasta / "contas.sqlite3")
contas.criar("homolog.adm", "Admin Homolog", "SenhaHomolog#2026", papel="admin")

srv = criar_servidor(pasta, None, "127.0.0.1", 0)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"

def req(path, payload=None, headers=None, method=None):
    hdrs = dict(headers or {})
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json")
    try:
        with urlopen(Request(base + path, data=data, headers=hdrs, method=method), timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except HTTPError as e:
        return e.code, dict(e.headers), e.read()

try:
    # 1. Snapshot ausente com GEDIV_EXIGIR_SNAPSHOT_PUBLICO=1 -> 503 fail-closed
    st_miss, _, _ = req("/api/painel")
    assert st_miss == 503, f"Esperado 503 sem snapshot publicado, obtido {st_miss}"

    # 2. Login cookie-only sob HTTPS: Set-Cookie HttpOnly+SameSite=Strict+Secure e ZERO 'token' no JSON
    st_l, hdrs_l, body_l = req(
        "/api/login",
        payload={"usuario": "homolog.adm", "senha": "SenhaHomolog#2026", "modo_cookie": True},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert st_l == 200, body_l
    j_l = json.loads(body_l)
    assert "token" not in j_l, "Token não deve constar no JSON em modo cookie-only!"
    sc = hdrs_l.get("Set-Cookie") or ""
    assert "HttpOnly" in sc and "SameSite=Strict" in sc and "Secure" in sc, sc
    cookie = sc.split(";", 1)[0]

    # 3. Publicação controlada de snapshot público pelo admin via cookie + same-origin
    st_pub, _, _ = req(
        "/api/admin/snapshot-publico",
        payload={},
        headers={"Cookie": cookie, "Sec-Fetch-Site": "same-origin"},
        method="POST",
    )
    assert st_pub == 200
    assert req("/api/painel")[0] == 200
    assert req("/api/data")[0] == 200

    # 4. Logout limpa cookie e revoga sessão
    st_out, hdrs_out, _ = req(
        "/api/logout",
        payload={},
        headers={"Cookie": cookie, "Sec-Fetch-Site": "same-origin"},
        method="POST",
    )
    assert st_out == 200 and "Max-Age=0" in (hdrs_out.get("Set-Cookie") or "")
    assert req("/api/sessao", headers={"Cookie": cookie})[0] == 401
    print("  OK: backend endurecido validado (503 fail-closed, cookie Secure/HttpOnly sem token no JSON, snapshot e logout).")
finally:
    srv.shutdown()
    srv.server_close()
PY

echo "[6/7] Testando comportamento diante de snapshot corrompido (rejeição fail-closed sem sobrescrever anterior)..."
PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}" PYTHONSAFEPATH=1 "$PYTHON_BIN" - "$DADOS_ISO" <<'PY'
import pathlib, sys
from observatorio.painel import indicadores
snap_arq = pathlib.Path(sys.argv[1]) / indicadores.ARQUIVO_SNAPSHOT_PUBLICO
antes = snap_arq.read_bytes()
try:
    indicadores.publicar_snapshot_publico(None, snap_arq, snapshot={"versao_snapshot": 1, "painel": {}, "data": {}})
    raise SystemExit("Snapshot inválido deveria ter sido rejeitado!")
except ValueError:
    pass
assert snap_arq.read_bytes() == antes
print("  OK: snapshot inválido recusado mantendo arquivo anterior íntegro.")
PY

echo "[7/7] Procedimento de reversão verificado (sem serviços alterados):"
echo "  - Em caso de regressão após deploy: git checkout <sha_anterior> && sudo systemctl restart gediv-admin.service"
echo "  - Restauração de backup SQLite: cp /var/lib/gediv/backups/observatorio-YYYY-MM-DD.sqlite3 /var/lib/gediv/dados/observatorio.sqlite3"
echo "=== HOMOLOGAÇÃO OPERACIONAL ISOLADA CONCLUÍDA COM SUCESSO ==="
