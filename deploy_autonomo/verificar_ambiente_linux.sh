#!/usr/bin/env bash
set -euo pipefail

# Verificação pré-implantação estritamente SOMENTE LEITURA para ambiente Linux / systemd.
# Não inicia serviços, não agenda timers, não executa coleta e não escreve em bancos SQLite.

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi
DB_CHECK="${1:-}"

if [ "$(uname -s)" != "Linux" ]; then
  echo "[AVISO] Sistema operacional atual não é Linux ($(uname -s)); verificações systemd não se aplicam."
fi

echo "[1/4] Verificando sintaxe Bash dos scripts..."
SHELL_BIN="${BASH:-$(command -v bash || command -v sh)}"
"$SHELL_BIN" -n "$APP_DIR/deploy_autonomo/rodar_diario.sh"
"$SHELL_BIN" -n "$APP_DIR/deploy_autonomo/recuperar_edicoes_manual.sh"
"$SHELL_BIN" -n "$APP_DIR/deploy_autonomo/verificar_ambiente_linux.sh"

echo "[2/4] Verificando binários operacionais exigidos..."
for cmd in flock date; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "  OK: $cmd -> $(command -v "$cmd")"
  else
    echo "  ERRO: binário ausente: $cmd" >&2
    exit 1
  fi
done
date -d "4 days ago" +%F >/dev/null

echo "[3/4] Verificando units systemd (quando systemd-analyze estiver disponível)..."
for unit in gediv-diario.service gediv-diario.timer gediv-admin.service; do
  if [ ! -f "$APP_DIR/deploy_autonomo/$unit" ]; then
    echo "  ERRO: unit ausente: $unit" >&2
    exit 1
  fi
done
if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "$APP_DIR/deploy_autonomo/gediv-diario.service" "$APP_DIR/deploy_autonomo/gediv-diario.timer" "$APP_DIR/deploy_autonomo/gediv-admin.service" || true
fi

echo "[4/4] Verificando importação Python sob PYTHONSAFEPATH=1..."
if [ -z "$PYTHON_BIN" ]; then
  echo "  ERRO: Python não encontrado." >&2
  exit 1
fi
PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}" PYTHONSAFEPATH=1 "$PYTHON_BIN" - <<'PY'
from observatorio.nucleo.banco import Banco
from observatorio.painel import adaptador, indicadores
from observatorio.web import servidor
assert hasattr(Banco, "somente_leitura")
assert hasattr(indicadores, "resumo_cobertura_edicoes")
assert hasattr(indicadores, "publicar_snapshot_publico")
assert hasattr(servidor, "criar_servidor")
print("  OK: módulos GEDIV importados com PYTHONSAFEPATH=1.")
PY

if [ -n "$DB_CHECK" ]; then
  echo "[EXTRA] Validando leitura (?mode=ro) sem escrita em $DB_CHECK..."
  PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}" PYTHONSAFEPATH=1 "$PYTHON_BIN" - "$DB_CHECK" <<'PY'
import sys
from observatorio.nucleo.banco import Banco
from observatorio.painel import indicadores
with Banco.somente_leitura(sys.argv[1]) as b_ro:
    res = indicadores.resumo_cobertura_edicoes(b_ro)
    print("  OK cobertura somente-leitura:", res)
PY
fi

echo "Verificação pré-implantação concluída sem alterações em arquivos ou bancos."
