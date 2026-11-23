#!/usr/bin/env bash
set -euo pipefail

# Rotina automática do Observatório DOE · GEDIV (TODOS OS DIAS, inclusive fins de semana e feriados).
# Fluxo canônico:
#   trava flock -> aviso informativo de feriado -> coleta DOE-PB (A União + complementar)
#   -> extração/OCR/classificação -> backup SQLite íntegro -> projeção pública sanitizada.
#
# Repositório canônico único: gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE.
# Conexão obsoleta com gediv-painel-redesign-preview foi REMOVIDA para impedir publicação indevida.

export TZ="${TZ:-America/Sao_Paulo}"

APP_DIR="${APP_DIR:-/opt/observatorio-gediv}"
DADOS_DIR="${DADOS_DIR:-/var/lib/gediv/dados}"
BACKUP_DIR="${BACKUP_DIR:-/var/lib/gediv/backups}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"
FERIADOS_ARQ="${FERIADOS_ARQ:-/etc/gediv/feriados_oficiais.txt}"
RETENCAO_DIAS="${RETENCAO_DIAS:-30}"
PUBLICAR_PAGES="${PUBLICAR_PAGES:-0}" # Mantido em 0 por padrão; exige autorização explícita
LOCK_ARQ="${LOCK_ARQ:-$DADOS_DIR/.gediv-coleta.lock}"

mkdir -p "$DADOS_DIR" "$BACKUP_DIR"

# 0. Exclusão mútua: impede dois agendadores ou execução manual simultânea no mesmo banco
exec 9>"$LOCK_ARQ"
if ! flock -n 9; then
  echo "[BLOQUEADO] Outra execução do Observatório GEDIV já está em andamento ($LOCK_ARQ)."
  exit 0
fi

# 1. Calendário no fuso America/Sao_Paulo: a coleta roda todos os dias, sem bloqueio de
#    fim de semana ou feriado (o DOE pode ter edição regular, suplementar ou extraordinária).
DATA_HOJE="$(date +%F)"
DATA_HOJE_BR="$(date +%d/%m/%Y)"
DIA_SEMANA="$(date +%u)" # 1=Segunda .. 7=Domingo (apenas informativo)

if [ -n "$FERIADOS_ARQ" ] && [ -f "$FERIADOS_ARQ" ]; then
  if grep -Eq "^(${DATA_HOJE}|${DATA_HOJE_BR})([[:space:]]|#|$)" "$FERIADOS_ARQ"; then
    echo "[INFO] $DATA_HOJE_BR consta como feriado em $FERIADOS_ARQ. A coleta do DOE será executada normalmente; ausência de edição só é registrada após consulta à fonte oficial."
  fi
fi

# 2. Janela de recuperação de lacunas: recua 3 dias para cobrir falhas de execuções anteriores
DIAS_RECUO=3
INICIO_JANELA="$(date -d "$DIAS_RECUO days ago" +%F)"
INICIO_JANELA_BR="$(date -d "$DIAS_RECUO days ago" +%d/%m/%Y)"

cd "$APP_DIR"
export PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}"

echo "[1/6] Coletando edições oficiais de $INICIO_JANELA_BR até $DATA_HOJE_BR (fuso=$TZ, dia ISO=$DIA_SEMANA)..."
set +e
"$PYTHON_BIN" -m observatorio.operacao coletar-intervalo --inicio "$INICIO_JANELA" --fim "$DATA_HOJE" --dados "$DADOS_DIR"
RC_COLETA=$?
set -e
if [ "$RC_COLETA" -ne 0 ] && [ "$RC_COLETA" -ne 3 ]; then
  echo "ERRO: coleta retornou código $RC_COLETA (4 = fonte inacessível/bloqueio; 1/2 = falha). Abortando sem simular sucesso."
  exit "$RC_COLETA"
fi

echo "[2/6] Executando extração, OCR (quando necessário) e classificação GEDIV (somente pendentes/novos)..."
set +e
"$PYTHON_BIN" -m observatorio.operacao executar --dados "$DADOS_DIR"
RC_EXEC=$?
set -e
if [ "$RC_EXEC" -ne 0 ] && [ "$RC_EXEC" -ne 3 ]; then
  echo "ERRO: processamento retornou código $RC_EXEC. Abortando antes da projeção pública."
  exit "$RC_EXEC"
fi

echo "[3/6] Gerando backup consistente do SQLite com verificação PRAGMA integrity_check e SHA-256..."
BACKUP_ARQ="$BACKUP_DIR/observatorio-$DATA_HOJE.sqlite3"
"$PYTHON_BIN" - "$DADOS_DIR/observatorio.sqlite3" "$BACKUP_ARQ" <<'PY'
import hashlib, sqlite3, sys
from pathlib import Path

orig, dest = Path(sys.argv[1]), Path(sys.argv[2])
tmp = dest.with_suffix(".sqlite3.tmp")
with sqlite3.connect(orig.resolve().as_uri() + "?mode=ro", uri=True) as src:
    with sqlite3.connect(tmp) as dst:
        src.backup(dst)
with sqlite3.connect(tmp.resolve().as_uri() + "?mode=ro", uri=True) as chk:
    res = chk.execute("PRAGMA integrity_check").fetchone()[0]
    if res != "ok":
        raise SystemExit(f"Backup corrompido: {res}")
tmp.replace(dest)
sha = hashlib.sha256(dest.read_bytes()).hexdigest()
dest.with_suffix(".sqlite3.sha256").write_text(f"{sha}  {dest.name}\n", encoding="utf-8")
print(f"Backup OK: {dest} ({dest.stat().st_size} bytes, sha256={sha})")
PY
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'observatorio-*.sqlite3*' -mtime "+$RETENCAO_DIAS" -delete

echo "[4/6] Verificando integridade e ausência de dados pessoais no frontend aprovado de 29/10..."
"$PYTHON_BIN" - "$APP_DIR/observatorio/web/unificado/index.html" <<'PY'
import re, sys
from pathlib import Path

html = Path(sys.argv[1]).read_text(encoding="utf-8")
if re.search(r"SAD-PSE-202\d/\d+", html):
    raise SystemExit("ERRO DE PRIVACIDADE: processo individual detectado no HTML estático!")
if '"rows":[{"id":' in html.replace(" ", ""):
    raise SystemExit("ERRO DE PRIVACIDADE: payload nominal embutido no HTML estático!")
print("Integridade do frontend 29/10 confirmada (0 dados pessoais embutidos).")
PY

echo "[5/6] Calculando resumo de cobertura e validando projeção somente-leitura da API para o frontend unificado..."
COBERTURA_RESUMO="$DADOS_DIR/cobertura_resumo.json"
"$PYTHON_BIN" - "$DADOS_DIR/observatorio.sqlite3" "$COBERTURA_RESUMO" <<'PY'
import json, sys
from pathlib import Path

from observatorio.nucleo.banco import Banco
from observatorio.painel import adaptador, indicadores

db, out = Path(sys.argv[1]), Path(sys.argv[2])
with Banco.somente_leitura(db) as banco_ro:
    resumo = indicadores.resumo_cobertura_edicoes(banco_ro)
    p_pub = indicadores.painel(
        banco_ro,
        {"escopo": "pendente", "inicio": "2026-01-01"},
        indicadores.PUBLICO,
        proteger_publico=True,
    )
    if p_pub["meta"]["escopo"] != "conferido" or p_pub["linhas"] != [] or p_pub["resenhas"] != [] or p_pub["eventos"] != []:
        raise SystemExit("ERRO DE PRIVACIDADE: perfil público expôs escopo pendente, resenhas, eventos ou linhas individuais!")
    if p_pub["apoio"]["decisoes_pendentes"] is not None:
        raise SystemExit("ERRO DE PRIVACIDADE: perfil público expôs fila interna de pendências!")
    proj_pub = adaptador.projetar_para_dashboard_2910(p_pub, [], [])
    if proj_pub.get("rows") or proj_pub["dashboard"]["counts"]["unlinkedEvents"] != 0:
        raise SystemExit("ERRO DE PRIVACIDADE: projeção pública contém linhas individuais ou contadores internos!")
    cats = [c[0] for c in proj_pub.get("categories", [])]
    if "TS-08" in cats or "ABONO_PERMANENCIA" not in cats:
        raise SystemExit(f"ERRO DE CONTRATO: categorias inválidas na projeção unificada: {cats}")
    snap_arq = db.parent / indicadores.ARQUIVO_SNAPSHOT_PUBLICO
    indicadores.publicar_snapshot_publico(banco_ro, snap_arq)

tmp = out.with_name(out.name + ".tmp")
tmp.write_text(json.dumps(resumo, indent=2) + "\n", encoding="utf-8")
tmp.replace(out)
print("Resumo de cobertura, snapshot público controlado (snapshot_publico.json) e projeção somente-leitura (?mode=ro) da API validados com sucesso (0 linhas individuais públicas; sem build de painel-publico/dados.json obsoleto).")
PY

echo "[6/6] Encerramento controlado..."
if [ "$PUBLICAR_PAGES" != "1" ]; then
  echo "PUBLICAR_PAGES=$PUBLICAR_PAGES (modo seguro local). Banco SQLite atualizado e pronto para consumo pelo painel unificado via API (/ e /painel)."
  exit 0
fi

echo "AVISO: publicação automática externa desativada até conclusão da contenção de segurança e definição de destino canônico autorizado."
exit 0
