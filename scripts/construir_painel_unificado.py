"""Constrói o dashboard unificado em `observatorio/web/unificado/index.html` e `paleta-aprovada.json`.

Partindo do `index.html` homologado (`SHA-256: 3460020F4F9383D92F9FCB35EC24228292010C9B8CCC9E399A91B503C8D412E5`):
1. Remove o payload de 1,29 MB (`window.GEDIV_BOOTSTRAP` com dados pessoais em texto claro) do código-fonte HTML,
   substituindo-o por um esqueleto público vazio (zero nomes, zero matrículas, zero processos no HTML estático);
2. Conecta `window.GEDIV_READY` e `refreshData()` à API real `/api/data` com suporte a autenticação gerencial
   (`POST /api/login`, `POST /api/logout`, `GET /api/sessao`) via `Authorization: Bearer <token>`;
3. Integra a revisão documental (`POST /api/revisao`) diretamente na interface para decisões (`CONFERIR`, `REJEITAR`,
   `REABRIR`, com correção auditada de campos) e para os 23 eventos modificadores (`VINCULAR`, `REJEITAR`, `REABRIR`),
   exigindo usuário autenticado, justificativa, `confirma_fonte` e `confirma_vinculo`;
4. Aplica a regra especial de grupos ocupacionais da Etapa 8 (`PENDENTE:TEC. ADM` separado de `AST`;
   `PENDENTE:STF` separado de `SFT`; `SSA` e `ESP` com equivalência comprovada e apelidos de filtro compatíveis);
5. Preserva integralmente a paleta de 240 cores HEX originais (**0 novas cores**), sem sobrescrever `revisao-2910/index.html`.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re

REPO_DIR = pathlib.Path(__file__).resolve().parents[1]


def construir(origem_html: pathlib.Path | None = None) -> None:
    env_origem = os.environ.get("GEDIV_ORIGEM_HTML")
    src_path = origem_html or (pathlib.Path(env_origem) if env_origem else None)
    if src_path is None or not src_path.is_file():
        raise FileNotFoundError(
            "Informe --origem <caminho_index_homologado.html> ou defina a variável de ambiente GEDIV_ORIGEM_HTML."
        )

    dest_unificado = REPO_DIR / "observatorio" / "web" / "unificado" / "index.html"
    dest_paleta = REPO_DIR / "observatorio" / "web" / "unificado" / "paleta-aprovada.json"

    html = src_path.read_text(encoding="utf-8")

    # Extrair conjunto de cores HEX originais antes de qualquer alteração
    hex_pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    orig_colors = {c.lower() for c in hex_pattern.findall(html)}
    print(f"Cores HEX originais: {len(orig_colors)}")
    html = re.sub(r"<!--\s*saved from url=\([^)]*\)[^>]*-->\s*", "", html, count=1)

    # 1. Substituir window.GEDIV_BOOTSTRAP (1.29MB) por esqueleto vazio sem dados pessoais
    # e atualizar window.GEDIV_MODEL para aceitar os 3 escopos ('pendente', 'conferido', 'rejeitado')
    m_boot = re.search(r"window\.GEDIV_BOOTSTRAP\s*=\s*", html)
    idx_model = html.find("window.GEDIV_MODEL=")
    idx_script_end = html.find("</script>", idx_model)
    assert m_boot and idx_model > m_boot.start() and idx_script_end > idx_model

    esqueleto_publico = """window.GEDIV_BOOTSTRAP={"rows":[],"events":[],"categories":[["TS-01","Anotação de Tempo de Serviço/Contribuição"],["TS-02","Desaverbação de Tempo de Serviço"],["TS-03","Licença para Tratar de Interesses Particulares"],["TS-04","Desistência de Licença de Interesse Particular"],["TS-05","Licença Especial"],["TS-06","Conversão de Licença Especial em Tempo de Serviço"],["TS-07","Conversão de Férias"],["ABONO_PERMANENCIA","Abono de Permanência"]],"groups":[],"urls":{},"meta":{"version":"Painel Diário Oficial | GEDIV · Regras 0.4","dictionary":"Catálogo controlado GEDIV (expressões não homologadas mantidas separadas)","verifiedAt":"","coverage":"Conectando ao servidor do Observatório DOE · GEDIV...","automation":"Motor Python/SQLite v8 conectado · Revisão auditada por servidor.","personal":"Sessão pública: dados individuais e anotações internas protegidos (faça login gerencial para conferir).","semBaseCarregada":true,"edicoes":0,"edicoesPendentes":0,"conferidos":0,"pendentes":0,"rejeitados":0,"eventosPendentes":0,"semDecisoesConferidas":true,"connection":{"batches":0,"source":"sqlite_v8_canonico","overlaps":0,"partialCoverage":true,"fullPeriodComplete":false}},"dashboard":{"schemaVersion":1,"revision":"0000000000000000000000000000000000000000000000000000000000000000","defaultScope":"conferido","counts":{"received":0,"pending":0,"confirmed":0,"rejected":0,"unlinkedEvents":0},"views":{"pendente":{"rowIds":[],"metrics":{"processes":0,"resenhas":0,"decisions":0,"deferidos":0,"indeferidos":0,"refeitos":null,"semEfeito":null},"series":{"vertical":0,"horizontal":0,"tempo":0,"other":0}},"conferido":{"rowIds":[],"metrics":{"processes":0,"resenhas":0,"decisions":0,"deferidos":0,"indeferidos":0,"refeitos":0,"semEfeito":0},"series":{"vertical":0,"horizontal":0,"tempo":0,"other":0}}}}};"""

    novo_model = """window.GEDIV_MODEL={dashboardModel:function t(e,t={}){let n=t.validation||e.dashboard?.defaultScope||`pendente`;if(![`pendente`,`conferido`,`rejeitado`].includes(n))throw Error(`Situação de conferência inválida.`);let r=e=>String(e??``).normalize(`NFD`).replace(/[\\u0300-\\u036f]/g,``).toLowerCase(),i=e=>(!t.from||e>=t.from)&&(!t.to||e<=t.to),a=(e,t)=>new Set(e.map(e=>e[t]).filter(Boolean)).size,o=new Map(e.categories||[]),s=e=>!(t.view===`outras`&&e.axis!==`outros`||t.axis&&e.axis!==t.axis||t.modality&&(e.axis!==`progressao`||e.modality!==t.modality)||t.group&&(e.axis!==`progressao`||(t.group===`NAO_INFORMADO`?e.group:e.group!==t.group))||t.category?.length&&(e.axis!==`tempo`||!t.category.includes(e.category))||t.merit&&e.merit!==t.merit||t.query&&!r([e.resenha,e.process,e.server,e.registration,e.group,e.groupExpression,t.groupNames?.[e.group],e.modality,o.get(e.category)].join(` `)).includes(r(t.query))),c=e.rows.filter(e=>e.validation===n&&s(e)),l=c.filter(e=>i(e.date)),u=new Set(c.map(e=>e.act).filter(Boolean)),d=n===`conferido`?e.events.filter(e=>e.validation===`conferido`&&e.act&&u.has(e.act)&&i(e.date)):[],f=d.filter(e=>[`Retificação`,`Correção`,`Republicação`].includes(e.type)),p=d.filter(e=>e.type===`Tornado sem efeito`),m={processes:a(l,`process`),resenhas:a(l,`resenha_id`),decisions:l.length,deferidos:l.filter(e=>e.merit===`deferido`).length,indeferidos:l.filter(e=>e.merit===`indeferido`).length,refeitos:n===`conferido`?new Set(f.map(e=>e.act)).size:null,semEfeito:n===`conferido`?new Set(p.map(e=>e.act)).size:null},h=l;if(t.card===`deferidos`||t.card===`indeferidos`)h=l.filter(e=>e.merit===(t.card===`deferidos`?`deferido`:`indeferido`));else if(t.card===`processes`)h=l.filter(e=>!!e.process);else if(t.card===`refeitos`||t.card===`semEfeito`){let e=new Set((t.card===`refeitos`?f:p).map(e=>e.act));h=c.filter(t=>t.act&&e.has(t.act))}let g={vertical:h.filter(e=>e.axis===`progressao`&&e.modality===`Vertical`).length,horizontal:h.filter(e=>e.axis===`progressao`&&e.modality===`Horizontal`).length,tempo:h.filter(e=>e.axis===`tempo`).length,other:h.filter(e=>![`tempo`,`progressao`].includes(e.axis)||e.axis===`progressao`&&![`Vertical`,`Horizontal`].includes(e.modality)).length},_=[...new Set(h.map(e=>e.date))].sort().map(e=>({date:e,records:h.filter(t=>t.date===e).length})),v=[...new Set(h.filter(e=>e.axis===`progressao`).map(e=>e.group||`NAO_INFORMADO`))].map(e=>({group:e,records:h.filter(t=>t.axis===`progressao`&&(t.group||`NAO_INFORMADO`)===e).length}));return{scope:n,preliminary:n!==`conferido`,label:n===`pendente`?`Em conferência · dados preliminares`:n===`rejeitado`?`Registros rejeitados`:`Decisões conferidas`,rows:h,original:l,metrics:m,redo:f,voided:p,series:g,timeline:_,groupSeries:v}},acceptSnapshot:function n(e){let t=e?.dashboard;if(!Array.isArray(e?.rows)||!Array.isArray(e?.events)||!Array.isArray(e?.categories)||!e?.meta?.connection||t?.schemaVersion!==1||!/^[0-9a-f]{64}$/.test(t.revision)||![`pendente`,`conferido`,`rejeitado`].includes(t.defaultScope))throw Error(`Resposta do backend incompatível; a base anterior foi mantida.`);let n=t.counts;if(!n||n.received!==e.rows.length||n.pending+n.confirmed+n.rejected!==n.received)throw Error(`Contagem do backend inconsistente; a base anterior foi mantida.`);for(let n of[`pendente`,`conferido`]){let r=e.rows.filter(e=>e.validation===n),i=t.views?.[n],a=new Set(r.map(e=>e.id));if(!i||!Array.isArray(i.rowIds)||i.rowIds.length!==r.length||new Set(i.rowIds).size!==r.length||i.rowIds.some(e=>!a.has(e))||i.metrics?.decisions!==r.length||!i.series||Object.values(i.series).reduce((e,t)=>e+t,0)!==r.length)throw Error(`Registros e gráficos do backend divergem; a base anterior foi mantida.`)}return e}};"""

    html = (
        html[: m_boot.start()]
        + esqueleto_publico
        + novo_model
        + html[idx_script_end:]
    )

    # 1b. Atualizar endpoint de recebimento de lote para /api/admin/lote com RBAC admin + token Bearer
    old_batch_js = """document.getElementById('receiveBatch').onclick=()=>{const out=document.getElementById('batchResult');out.textContent='';out.classList.remove('is-error');document.getElementById('batchDialog').showModal();};
document.getElementById('closeBatch').onclick=()=>document.getElementById('batchDialog').close();
document.getElementById('closeBatchTop').onclick=()=>document.getElementById('batchDialog').close();
document.getElementById('batchFile').onchange=async e=>{if(e.target.files[0])document.getElementById('batchText').value=await e.target.files[0].text();};
document.getElementById('sendBatch').onclick=async()=>{const b=document.getElementById('sendBatch'),out=document.getElementById('batchResult');out.classList.remove('is-error');const raw=document.getElementById('batchText').value.trim();if(!raw){out.textContent='Selecione um arquivo .json ou cole o JSON do lote antes de enviar.';out.classList.add('is-error');return;}b.disabled=true;out.textContent='Recebendo…';try{JSON.parse(raw);const r=await fetch('/api/ingest',{method:'POST',headers:{'Content-Type':'application/json'},body:raw});let d={};try{d=await r.json();}catch{}if(!r.ok)throw new Error(d.error||(r.status===404?'Envio disponível apenas no servidor local GEDIV (endpoint /api/ingest não existe nesta publicação estática).':'HTTP '+r.status));out.textContent=(d.status==='ja_recebido'?'Lote já recebido. Nenhum registro duplicado.':'Lote recebido: '+d.records+' registro(s) pendente(s).')+' Recibo: '+d.batchId;sessionStorage.setItem('gedivUltimoRecibo',JSON.stringify(d));}catch(e){out.textContent='Falha: '+e.message;out.classList.add('is-error');}finally{b.disabled=false;}};"""
    new_batch_js = """function openAdminBatchDialog(){
 if(!window.GEDIV_DATA?.backend?.ehAdmin){
  if(typeof toast==='function')toast('Operação restrita a contas de Administração.');
  return;
 }
 const out=document.getElementById('batchResult');out.textContent='';out.classList.remove('is-error');
 document.getElementById('batchDialog').showModal();
}
document.getElementById('receiveBatch').onclick=openAdminBatchDialog;
document.getElementById('closeBatch').onclick=()=>document.getElementById('batchDialog').close();
document.getElementById('closeBatchTop').onclick=()=>document.getElementById('batchDialog').close();
document.getElementById('batchFile').onchange=async e=>{if(e.target.files[0])document.getElementById('batchText').value=await e.target.files[0].text();};
document.getElementById('sendBatch').onclick=async()=>{
 const b=document.getElementById('sendBatch'),out=document.getElementById('batchResult');
 out.classList.remove('is-error');
 if(!window.GEDIV_DATA?.backend?.ehAdmin){out.textContent='Permissão administrativa necessária.';out.classList.add('is-error');return;}
 const raw=document.getElementById('batchText').value.trim();
 if(!raw){out.textContent='Selecione um arquivo .json ou cole o JSON do lote antes de enviar.';out.classList.add('is-error');return;}
 b.disabled=true;out.textContent='Validando lote (sem alterar o banco principal)…';
 try{
  const parsed=JSON.parse(raw);
  if(!parsed||typeof parsed!=='object'||(!Array.isArray(parsed.rows)&&!Array.isArray(parsed.edicoes)&&!Array.isArray(parsed.lote)))throw new Error('JSON precisa conter a lista "rows", "edicoes" ou "lote".');
  const hdrs=window.GEDIV_AUTH?window.GEDIV_AUTH.headers({'Content-Type':'application/json'}):{'Content-Type':'application/json'};
  const r=await fetch('/api/admin/lote',{method:'POST',headers:hdrs,body:raw});
  let d={};try{d=await r.json();}catch{}
  if(!r.ok)throw new Error(d.erro||d.error||'HTTP '+r.status);
  out.textContent=`Validação concluída (${d.status} · não importado ao banco): ${d.recebidos} analisado(s) · ${d.novos} inédito(s) · ${d.ja_existentes} já existente(s). Os registros foram apenas validados e não incorporados ao banco principal (importação definitiva: pendência operacional).`;
 }catch(e){out.textContent='Falha: '+e.message;out.classList.add('is-error');}
 finally{b.disabled=false;}
};"""
    assert old_batch_js in html
    html = html.replace(old_batch_js, new_batch_js, 1)

    # 2. Limpar registros pré-renderizados no HTML estático (para que o arquivo HTML não contenha nomes/resenhas fixas)
    html = re.sub(
        r'(<div id="records" class="records">).*?(</div><div class="list-footer">)',
        r'\1<div class="empty-small">Carregando base autorizada...</div>\2',
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'(<div id="details" class="detail-body">).*?(</div></section>)',
        r'\1<div class="empty-small">Selecione uma publicação para ver os detalhes.</div>\2',
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'(<div id="timeline" class="timeline">).*?(</div><div class="legend">)',
        r'\1<div class="empty-small">Carregando série temporal...</div>\2',
        html,
        flags=re.DOTALL,
    )
    html = html.replace(
        '<span class="eyebrow">RECEBIMENTO DE LOTE</span><h2 id="batchDialogTitle">Receber lote oficial</h2>',
        '<span class="eyebrow">ADMINISTRAÇÃO · VALIDAÇÃO PRELIMINAR DE LOTE</span><h2 id="batchDialogTitle">Validar lote oficial (sem importação no banco)</h2>',
        1,
    )
    html = html.replace(
        '<p>A entrega preserva o histórico e mantém os novos registros pendentes de conferência.</p>',
        '<p>Validação estrutural e verificação de duplicidades com registro em auditoria. <strong>Os registros são apenas validados e NÃO são incorporados ao banco principal nesta etapa (importação definitiva: pendência operacional).</strong></p>',
        1,
    )
    html = html.replace(
        '<button type="button" id="sendBatch">Receber e atualizar</button>',
        '<button type="button" id="sendBatch">Validar lote (sem importar)</button>',
        1,
    )
    html = html.replace(
        ' &nbsp; Download da página <span aria-hidden="true">⌄</span>',
        ' &nbsp; Exportar visualização <span aria-hidden="true">⌄</span>',
        1,
    )
    html = html.replace(
        '<div class="download-menu" id="downloadMenu" role="menu" hidden="">',
        '<div class="download-menu" id="downloadMenu" role="menu" hidden=""><div id="exportScopeHead" class="delicate-exp-head">Modo público: apenas indicadores agregados</div>',
        1,
    )

    # 2b. Suporte a Abono de Permanência no eixo Tempo de Serviço (preservando TS-01 a TS-07, sem TS-08, 0 cores novas)
    html = html.replace(
        "<p>Os sete serviços permanecem visíveis · clique para filtrar</p>",
        "<p>Os sete serviços (TS-01 a TS-07) e Abono de Permanência permanecem visíveis · clique para filtrar</p>",
        1,
    )
    html = html.replace(
        "let colors=['#f49b45','#d36a44','#e0ad40','#d2866d','#bf6858','#e8be79','#a879bb'];",
        "let colors=['#f49b45','#d36a44','#e0ad40','#d2866d','#bf6858','#e8be79','#a879bb','#175ca8'];",
        1,
    )

    # 3. Adicionar estilos para formulários de autenticação e revisão usando EXCLUSIVAMENTE cores já existentes na paleta
    css_extra = """
.auth-pill{font-size:11px;font-weight:700;color:#175a4e;background:#d9efe7;border:1px solid #a8cfbf;border-radius:12px;padding:3px 10px}
.auth-pill.is-public{color:#8c4a07;background:#fff8eb;border-color:#f4dfb6}
.review-form{display:grid;gap:10px;font-size:12px;color:#183b5d}
.review-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.review-form label{display:flex;flex-direction:column;gap:4px;font-weight:700;font-size:11px;color:#27527c}
.review-form input[type=text],.review-form input[type=password],.review-form select,.review-form textarea{width:100%;border:1px solid #cdddeb;border-radius:6px;padding:7px 9px;font-size:12px;color:#102b4d;background:#fff}
.review-form textarea{min-height:68px;resize:vertical}
.review-form .check-row{flex-direction:row;align-items:flex-start;gap:8px;font-weight:600;color:#183b5d;background:#f4f8fd;border:1px solid #dce8f1;border-radius:6px;padding:8px 10px}
.review-form .check-row input{margin-top:2px}
.review-status{min-height:18px;font-size:12px;font-weight:700;color:#175a4e;margin:4px 0 0}
.review-status.is-error{color:#b93840}
.prelim-note{margin-top:8px;padding:7px 9px;border-radius:5px;background:#fff8eb;border:1px solid #f4dfb6;color:#8c4a07;font-size:10px;line-height:1.35}
.proc-stack{display:flex;flex-direction:column;gap:14px}
.proc-card,.sel-card{background:#fff;border:1px solid #dce8f1;border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:10px}
.proc-head,.sel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.proc-title{margin:0;font-size:13px;font-weight:700;color:#102b4d;line-height:1.3}
.proc-title span{font-weight:500;color:#405d79;font-size:12px;white-space:nowrap;display:inline-block}
.proc-sub{margin:3px 0 0;font-size:11px;color:#405d79}
.proc-export-btn,.sel-expand-btn,.sel-btn-sec,.sel-btn-pri{display:inline-flex;align-items:center;justify-content:center;gap:6px;border-radius:7px;font-size:11px;font-weight:600;cursor:pointer;text-decoration:none;transition:background .15s,border-color .15s}
.proc-export-btn{border:1px solid #cdddeb;background:#fff;color:#183b5d;padding:5px 10px;min-height:30px;white-space:nowrap}
.proc-export-btn:hover,.sel-btn-sec:hover,.sel-expand-btn:hover{background:#f4f8fd;border-color:#175ca8;color:#102b4d}
.proc-export-btn:focus-visible,.sel-expand-btn:focus-visible,.sel-btn-sec:focus-visible,.sel-btn-pri:focus-visible,.proc-link-btn:focus-visible,.proc-table tbody tr:focus-visible,.doc-close-btn:focus-visible{outline:2px solid #175ca8;outline-offset:2px}
.proc-table-wrap{overflow-x:auto;overflow-y:auto;max-height:230px;border:1px solid #dce8f1;border-radius:8px;background:#fff}
.proc-table{width:100%;min-width:390px;border-collapse:collapse;font-size:11px;text-align:left}
.proc-table thead th{position:sticky;top:0;z-index:1;background:#f4f8fd;color:#27527c;font-weight:700;padding:7px;border-bottom:1px solid #dce8f1;white-space:nowrap}
.proc-table tbody td{padding:7px;border-bottom:1px solid #eef5fc;color:#102b4d;vertical-align:middle;white-space:nowrap;max-width:125px;overflow:hidden;text-overflow:ellipsis}
.proc-table tbody tr{cursor:pointer;transition:background .12s}
.proc-table tbody tr:hover{background:#f4f8fd}
.proc-table tbody tr.is-active{background:#eef5fc;font-weight:600}
.proc-table tbody tr.is-active td:first-child{box-shadow:inset 3px 0 0 #175ca8}
.proc-footer{display:flex;justify-content:flex-end;align-items:center;padding-top:2px}
.proc-link-btn{background:none;border:0;padding:4px 2px;color:#175ca8;font-size:11px;font-weight:600;cursor:pointer;display:inline-flex;align-items:center;gap:4px}
.proc-link-btn:hover{text-decoration:underline}
.sel-expand-btn{width:32px;height:32px;border:1px solid #dce8f1;background:#fff;color:#27527c;padding:0;flex-shrink:0}
.sel-grid{display:grid;grid-template-columns:minmax(108px,124px) minmax(0,1fr);gap:7px 12px;font-size:11.5px;align-items:baseline}
.sel-dt{color:#405d79;font-weight:500}
.sel-dd{color:#102b4d;font-weight:600;word-break:break-word}
.sel-dd.is-muted{color:#405d79;font-weight:400;font-style:italic}
.sel-page-badge{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:22px;padding:0 7px;border-radius:6px;background:#f4f8fd;border:1px solid #dce8f1;color:#102b4d;font-size:11px;font-weight:700}
.res-pill{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:12px;font-size:10.5px;font-weight:700;white-space:nowrap}
.res-pill.is-pos{background:#d9efe7;color:#175a4e}
.res-pill.is-neg{background:#ffefef;color:#da555c}
.res-pill.is-neu{background:#fff0de;color:#d58027}
.sel-doe-box{display:flex;align-items:center;justify-content:space-between;gap:10px;background:#f4f8fd;border:1px solid #dce8f1;border-radius:8px;padding:9px 11px}
.sel-doe-left{display:flex;align-items:center;gap:9px;min-width:0}
.sel-doe-ico{width:28px;height:28px;border-radius:6px;background:#fff;border:1px solid #dce8f1;display:inline-flex;align-items:center;justify-content:center;color:#175ca8;flex-shrink:0}
.sel-doe-title{font-size:11.5px;font-weight:700;color:#102b4d;line-height:1.25}
.sel-doe-sub{font-size:10.5px;color:#405d79;margin-top:2px}
.sel-doe-shield{color:#175a4e;flex-shrink:0;display:inline-flex;align-items:center}
.sel-actions{display:flex;gap:8px;flex-wrap:wrap}
.sel-btn-pri{flex:1 1 150px;background:#175ca8;color:#fff;border:1px solid #175ca8;padding:8px 12px;min-height:36px}
.sel-btn-pri:hover{background:#102b4d;border-color:#102b4d}
.sel-btn-sec{background:#fff;color:#183b5d;border:1px solid #cdddeb;padding:8px 12px;min-height:36px;white-space:nowrap}
.sel-btn-pri[aria-disabled="true"],.sel-btn-sec[aria-disabled="true"],.sel-btn-pri:disabled,.sel-btn-sec:disabled{opacity:.55;cursor:not-allowed;pointer-events:none}
.sel-review-strip{display:flex;align-items:center;justify-content:space-between;gap:8px;padding-top:8px;border-top:1px solid #eef5fc;font-size:11px;flex-wrap:wrap}
.sel-review-state{color:#8c4a07;font-weight:600}
.sel-review-state.is-conf{color:#175a4e}
.sel-hist-wrap{display:flex;justify-content:center;padding-top:2px}
.doc-modal{border:0;border-radius:12px;padding:0;max-width:740px;width:calc(100vw - 28px);max-height:calc(100vh - 36px);box-shadow:0 20px 50px rgba(16,43,77,.28);background:#fff;color:#102b4d;overflow:hidden}
.doc-modal::backdrop{background:rgba(16,43,77,.58);backdrop-filter:blur(2px)}
.doc-modal-shell{display:flex;flex-direction:column;max-height:calc(100vh - 36px)}
.doc-modal-top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px 10px;border-bottom:1px solid #eef5fc}
.doc-modal-id{font-size:11px;color:#405d79;word-break:break-all}
.doc-close-btn{width:32px;height:32px;border-radius:7px;border:1px solid #cdddeb;background:#fff;color:#183b5d;font-size:18px;line-height:1;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}
.doc-close-btn:hover{background:#f4f8fd;border-color:#175ca8}
.doc-modal-body{padding:16px 18px;overflow-y:auto;display:flex;flex-direction:column;gap:12px}
.doc-badges{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.doc-pill{display:inline-flex;align-items:center;padding:3px 9px;border-radius:12px;font-size:11px;font-weight:700;background:#fff0de;color:#d58027}
.doc-pill.is-prog{background:#eef5fc;color:#175ca8}
.doc-name{margin:2px 0 0;font-size:19px;font-weight:800;color:#102b4d;line-height:1.2;word-break:break-word}
.doc-proc{margin:0;font-size:12.5px;color:#405d79;font-weight:500}
.doc-meta-box{background:#f4f8fd;border:1px solid #dce8f1;border-radius:10px;padding:14px 16px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 18px}
.doc-field{display:flex;flex-direction:column;gap:3px;min-width:0}
.doc-field-lbl{font-size:10.5px;color:#405d79;font-weight:500}
.doc-field-val{font-size:12px;color:#102b4d;font-weight:700;word-break:break-word}
.doc-field-val.is-empty{color:#405d79;font-weight:400;font-style:italic}
.doc-modal-foot{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 18px 16px;border-top:1px solid #eef5fc;flex-wrap:wrap}
.doc-foot-left{display:flex;gap:8px;flex-wrap:wrap}
.explorer .record{transition:background .12s;border-radius:7px;padding:10px 10px}
.explorer .record:hover{background:#f4f8fd}
.explorer .record.selected{background:#eef5fc;box-shadow:inset 3px 0 0 #175ca8}
.explorer .record:focus-visible,.explorer .switch button:focus-visible,.explorer .list-footer button:focus-visible,.explorer .icon-btn:focus-visible{outline:2px solid #175ca8;outline-offset:2px}
.explorer .list-footer button,.explorer .icon-btn{min-width:32px;min-height:32px}
.rec-pills{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-top:4px}
.rec-qty-wrap{display:flex;flex-direction:column;align-items:flex-end;gap:2px;flex-shrink:0}
.rec-qty-sub{font-size:9.5px;color:#405d79;font-weight:500;white-space:nowrap}
/* Delicadeza visual canônica, cabeçalho único, escopo discreto, RBAC e Evolução Mensal (0 cores novas) */
body{background:#f3f7fb!important}
#connectionBar,#receivedSummaryBar,.top-status{display:none!important}
.topbar{background:linear-gradient(105deg,#072d64,#0a4d96 58%,#053b7d)!important;min-height:76px;border-bottom:1px solid rgba(255,255,255,.12);box-shadow:0 2px 10px rgba(7,45,100,.14)}
.header-title p{color:#cfe2fa}
.delicate-hdr-controls{display:flex;align-items:center;gap:8px;position:relative;flex-shrink:0}
.delicate-glass-btn{display:inline-flex;align-items:center;gap:8px;background:rgba(255,255,255,.11);border:1px solid rgba(255,255,255,.26);color:#fff;border-radius:8px;padding:6px 12px;font-size:11.5px;font-weight:600;min-height:34px;cursor:pointer;transition:background .15s,border-color .15s}
.delicate-glass-btn:hover{background:rgba(255,255,255,.2);border-color:rgba(255,255,255,.45)}
.delicate-dot{width:8px;height:8px;border-radius:50%;background:#13b88a;flex-shrink:0}
.delicate-dot.is-pub{background:#ffbb57}
.delicate-role-tag{font-size:10px;background:rgba(255,255,255,.18);padding:2px 7px;border-radius:10px;font-weight:700}
.delicate-menu{position:absolute;top:42px;right:0;min-width:248px;background:#fff;color:#102b4d;border:1px solid #dfe9f2;border-radius:9px;box-shadow:0 12px 28px rgba(16,43,77,.18);padding:6px;z-index:80}
.delicate-menu[hidden],.delicate-menu [hidden]{display:none!important}
.delicate-menu-hd{padding:8px 10px;border-bottom:1px solid #e5edf5;font-size:11px;color:#405d79}
.delicate-menu-hd b{display:block;color:#102b4d;font-size:12px}
.delicate-menu button{width:100%;text-align:left;border:0;background:transparent;color:#102b4d;font-size:11.5px;font-weight:600;padding:8px 10px;border-radius:6px;cursor:pointer;display:flex;align-items:center;justify-content:space-between}
.delicate-menu button:hover{background:#eef5fc;color:#1265ef}
.delicate-menu button.is-danger{color:#da555c}
.delicate-menu button.is-danger:hover{background:#ffefef}
.sidebar{background:linear-gradient(180deg,#f9fcff 0%,#f0f5f9 100%)!important;border-right:1px solid #dce7f1!important}
.card{border:1px solid #dfe9f2!important;border-radius:9px!important;box-shadow:0 2px 6px rgba(16,43,77,.03)!important}
.kpi{background:linear-gradient(145deg,#f9fcff,#edf5ff)!important;border:1px solid #dce8f3!important;border-radius:8px!important;transition:transform .12s,border-color .15s}
.kpi.green{background:linear-gradient(145deg,#f4faf8,#e5f8ee)!important;border-color:#d9efe7!important}
.kpi.green .val{color:#0b9d71!important}
.kpi.red{background:linear-gradient(145deg,#fff0f0,#ffefef)!important;border-color:#f7d6ad!important}
.kpi.red .val{color:#e45158!important}
.toolbar{gap:8px;align-items:center}
.tabs{flex:1 1 auto;min-width:0;gap:5px!important}
.tabs button{border:1px solid #dfe9f2;background:#f9fcff;color:#27527c;padding:7px 10px!important;font-size:11px!important;white-space:nowrap}
.tabs button:hover{background:#eef5fc;border-color:#b8d5fa}
.tabs button.active{background:#1265ef;border-color:#1265ef;color:#fff;box-shadow:0 3px 8px #1265ef2c}
.downloads{display:flex;align-items:center;gap:6px;flex-wrap:wrap;flex-shrink:0}
.delicate-scope-inline{border:1px solid #f4dfb6;background:#fff8eb;color:#8c4a07;border-radius:6px;padding:6px 9px;font-size:11px;font-weight:700;min-height:33px;cursor:pointer}
.delicate-exp-head{padding:7px 10px;border-bottom:1px solid #e5edf5;font-size:10.5px;font-weight:700;color:#27527c;background:#f9fcff;border-radius:6px 6px 0 0;margin-bottom:3px}
.banner{background:#edf5ff!important;border:1px solid #d1e3f6!important;border-radius:8px!important;padding:9px 14px!important;align-items:center!important;min-height:40px}
.banner .banner-symbol{width:20px;height:20px;font-size:11px;background:#1265ef;color:#fff}
.banner div:nth-child(2){display:flex;flex-direction:row;flex-wrap:wrap;align-items:baseline;gap:2px 8px;flex:1 1 200px;min-width:0}
.banner #bannerTitle{display:inline;font-size:12px;color:#102b4d;margin-right:0}
.banner #bannerText{display:inline;font-size:11.5px;color:#405d79}
.banner #coverageOpen{background:transparent!important;border:0!important;color:#1265ef!important;font-size:11.5px!important;font-weight:700!important;padding:4px 6px!important;white-space:nowrap}
.explorer .record{border:1px solid #e5edf5;background:#fff;margin-bottom:6px;padding:10px 11px}
.explorer .record:hover{border-color:#b8d5fa;background:#f9fcff}
.explorer .record.selected{background:#eef5fc;border-color:#175ca8;box-shadow:inset 3px 0 0 #1265ef}
.delicate-tl-bar{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;flex-wrap:wrap}
.delicate-seg{display:inline-flex;background:#f0f5f9;border:1px solid #dce8f1;border-radius:7px;padding:2px}
.delicate-seg button{border:0;background:transparent;color:#27527c;font-size:10.5px;font-weight:700;padding:4px 9px;border-radius:5px;cursor:pointer}
.delicate-seg button.active{background:#0a4d96;color:#fff}
.delicate-tl-svg{width:100%;height:176px;display:block}
.delicate-tl-svg [data-dtip]{cursor:pointer}
.delicate-tl-leg{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;align-items:center}
.delicate-lg-btn{display:inline-flex;align-items:center;gap:5px;border:1px solid transparent;background:transparent;color:#27527c;font-size:11px;font-weight:600;padding:3px 7px;border-radius:6px;cursor:pointer}
.delicate-lg-btn:hover{background:#eef5fc;border-color:#cdddeb}
.delicate-lg-btn.is-off{opacity:.42;text-decoration:line-through}
.delicate-lg-dot{width:9px;height:9px;border-radius:2px;display:inline-block}
.delicate-tl-tip{font-size:11px;color:#102b4d;font-weight:600;background:#f4f8fd;border:1px solid #dce8f1;border-radius:6px;padding:5px 10px;margin-top:6px;min-height:26px}
.delicate-tl-note{font-size:11px;color:#27527c;margin-top:5px;line-height:1.35}
@media(max-width:920px){.topbar{flex-wrap:wrap;gap:10px}.header-title{flex:1 1 220px;overflow:hidden}.header-title h1,.header-title p{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
@media(max-width:760px){.tabs{flex-wrap:nowrap!important;overflow-x:auto!important;-webkit-overflow-scrolling:touch;scroll-snap-type:x mandatory;padding-bottom:6px;scrollbar-width:thin}.tabs::-webkit-scrollbar{height:4px}.tabs::-webkit-scrollbar-thumb{background:#b8d5fa;border-radius:4px}.tabs button{scroll-snap-align:start;flex-shrink:0!important}.kpi[data-card="decisions"]{grid-column:1 / -1}.banner{align-items:flex-start!important;flex-wrap:wrap!important;gap:6px 10px!important}.banner div:nth-child(2){flex:1 1 220px;min-width:0}.banner #coverageOpen{display:inline-flex!important;align-self:flex-start;margin-left:30px!important;margin-top:0!important;padding:2px 0!important}.downloads{width:100%}.downloads .delicate-scope-inline{flex:1 1 180px}.downloads .download-main{flex:1 1 180px}}
@media(max-width:700px){.review-grid,.doc-meta-box{grid-template-columns:1fr}.sel-grid{grid-template-columns:minmax(96px,112px) minmax(0,1fr)}}
"""
    html = html.replace(
        "@media print{\n #connectionBar",
        css_extra + "\n@media print{\n #connectionBar",
    )

    # 4. Atualizar #connectionBar e diálogos de Login e Revisão Documental
    old_conn_bar = """<section id="connectionBar" style="background:#eaf6f1;border:1px solid #a8cfbf;padding:12px 20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap"><strong id="connectionState" role="status">Conectado · 3 lote(s) recebido(s) · 327 registros pendentes</strong><span class="static-badge" id="staticBadge" hidden>Modo consulta estática</span><button id="refreshData">Atualizar dados</button><button id="receiveBatch">Receber lote oficial</button></section>"""
    new_conn_bar = """<section id="connectionBar" style="background:#eaf6f1;border:1px solid #a8cfbf;padding:12px 20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap"><strong id="connectionState" role="status">Conectando ao servidor GEDIV…</strong><span class="auth-pill is-public" id="authBadge">Consulta pública (dados individuais restritos)</span><span class="static-badge" id="staticBadge" hidden>Modo consulta estática</span><button type="button" id="authToggleBtn">Acesso da gerência</button><button type="button" id="logoutBtn" hidden>Encerrar sessão</button><button id="refreshData">Atualizar dados</button><button id="receiveBatch">Receber lote oficial</button></section>"""
    assert old_conn_bar in html
    html = html.replace(old_conn_bar, new_conn_bar, 1)

    dialogs_auth_review = """
<dialog id="loginDialog" aria-labelledby="loginDialogTitle"><div class="dialog-head"><div><span class="eyebrow">ACESSO RESTRITO · GEDIV / SEAD-PB</span><h2 id="loginDialogTitle">Autenticação da gerência</h2></div><button type="button" id="closeLoginTop" class="icon-btn" aria-label="Fechar janela">×</button></div><form id="loginForm" class="dialog-body review-form" method="dialog"><p style="margin:0;font-size:11px;color:#405d79">O acesso aos nomes, matrículas, processos, anotações preliminares, PDFs do acervo e ações de revisão documental é exclusivo para contas autorizadas da gerência.</p><div class="review-grid"><label>Usuário da conta<input type="text" id="loginUser" autocomplete="username" placeholder="Ex.: revisor.gediv"></label><label>Senha<input type="password" id="loginPass" autocomplete="current-password" placeholder="Senha da conta"></label></div><details><summary style="cursor:pointer;font-weight:600;color:#175ca8;font-size:11px">Usar credencial técnica (token Bearer da gerência)</summary><label style="margin-top:8px">Token técnico de sessão / gerência<input type="password" id="loginTokenInput" autocomplete="off" placeholder="Cole o token de autorização da gerência"></label></details><p id="loginStatus" class="review-status" role="status"></p><div class="dialog-footer" style="padding:12px 0 0"><button type="button" id="closeLoginBtn" class="btn-secondary">Cancelar</button><button type="submit" id="submitLoginBtn">Entrar e carregar dados</button></div></form></dialog>
<dialog id="reviewDialog" aria-labelledby="reviewDialogTitle"><div class="dialog-head"><div><span class="eyebrow">REVISÃO DOCUMENTAL AUDITADA</span><h2 id="reviewDialogTitle">Conferir ou revisar registro</h2></div><button type="button" id="closeReviewTop" class="icon-btn" aria-label="Fechar janela">×</button></div><form id="reviewForm" class="dialog-body review-form" method="dialog"><input type="hidden" id="revTargetType" value="decisao"><input type="hidden" id="revTargetId" value=""><div id="revContextBox" class="reconcile-note" style="margin:0"></div><div class="review-grid"><label>Decisão de revisão<select id="revDecision"><option value="CONFERIR">CONFERIR (homologar após leitura do PDF)</option><option value="REJEITAR">REJEITAR (excluir dos indicadores)</option><option value="REABRIR">REABRIR (retornar para fila pendente)</option></select></label><label>Responsável pela revisão<input type="text" id="revAuthor" placeholder="Nome do revisor (automático em conta nominal)"></label></div><div id="revEventBox" hidden><label>ID do ato original a vincular (20 caracteres hexadecimais)<input type="text" id="revOriginalActId" placeholder="Obrigatório para VINCULAR evento modificador"></label></div><details id="revCorrectionsDetails"><summary style="cursor:pointer;font-weight:700;color:#175ca8;font-size:11px">Corrigir campos extraídos (preserva valor original na trilha de auditoria)</summary><div class="review-grid" style="margin-top:8px"><label>Processo<input type="text" id="revCorrProcess"></label><label>Matrícula<input type="text" id="revCorrRegistration"></label><label>Servidor<input type="text" id="revCorrServer"></label><label>Resultado<select id="revCorrResult"><option value="">Manter atual</option><option value="DEFERIDO">DEFERIDO</option><option value="INDEFERIDO">INDEFERIDO</option><option value="NAO_INFORMADO">NAO_INFORMADO</option></select></label><label>Classe origem (A–F)<input type="text" id="revCorrClassFrom" maxlength="1" placeholder="A..F"></label><label>Classe destino (A–F)<input type="text" id="revCorrClassTo" maxlength="1" placeholder="A..F"></label></div></details><label class="check-row"><input type="checkbox" id="revConfirmSource"><span>Declaro que consultei o PDF oficial do Diário Oficial na página indicada (<code>confirma_fonte</code>).</span></label><label class="check-row" id="revConfirmLinkRow"><input type="checkbox" id="revConfirmLink"><span>Confirmo o vínculo institucional deste ato com a GEDIV/SEAD-PB, mesmo quando a sigla não consta expressamente no cabeçalho (<code>confirma_vinculo</code>).</span></label><label>Justificativa técnica (obrigatória · mínimo 5 caracteres)<textarea id="revJustification" placeholder="Descreva a verificação realizada no PDF oficial do DOE..."></textarea></label><p id="revStatus" class="review-status" role="status"></p><div class="dialog-footer" style="padding:12px 0 0"><button type="button" id="closeReviewBtn" class="btn-secondary">Cancelar</button><button type="submit" id="submitReviewBtn">Registrar decisão auditada</button></div></form></dialog>
<dialog id="docModal" class="doc-modal" aria-labelledby="docModalTitle"><div class="doc-modal-shell"><div class="doc-modal-top"><span id="docModalId" class="doc-modal-id">Registro documental</span><button type="button" id="closeDocModal" class="doc-close-btn" aria-label="Fechar janela documental">×</button></div><div id="docModalBody" class="doc-modal-body"></div><div id="docModalFoot" class="doc-modal-foot"></div></div></dialog>
"""

    old_boot_script = """<script>
window.GEDIV_READY=(async()=>{const d=window.GEDIV_BOOTSTRAP;if(!Array.isArray(d.rows)||!d.meta?.connection)throw new Error('Resposta inválida');window.GEDIV_DATA=d;document.getElementById('connectionState').textContent='Conectado · '+d.meta.connection.batches+' lote(s) recebido(s) · '+d.meta.pendentes+' registros pendentes';return d;})().catch(e=>{document.getElementById('connectionState').textContent='Não foi possível conectar. Atualize para tentar novamente.';throw e;});"""

    new_boot_script = (
        dialogs_auth_review
        + """<script>
window.GEDIV_AUTH={
 token:()=>sessionStorage.getItem('gedivTokenGerencia')||'',
 user:()=>{try{return JSON.parse(sessionStorage.getItem('gedivContaGerencia')||'null');}catch{return null;}},
 set:(tok,usr)=>{if(tok)sessionStorage.setItem('gedivTokenGerencia',tok);else sessionStorage.removeItem('gedivTokenGerencia');if(usr)sessionStorage.setItem('gedivContaGerencia',JSON.stringify(usr));else sessionStorage.removeItem('gedivContaGerencia');},
 headers:(extra={})=>{const tok=window.GEDIV_AUTH.token();return tok?{...extra,Authorization:'Bearer '+tok}:{...extra};}
};
window.GEDIV_FETCH_DATA=async()=>{
 const r=await fetch('/api/data',{cache:'no-store',headers:window.GEDIV_AUTH.headers({Accept:'application/json'})});
 if(!r.ok)throw new Error('HTTP '+r.status);
 return window.GEDIV_MODEL.acceptSnapshot(await r.json());
};
window.GEDIV_READY=(async()=>{
 let d=window.GEDIV_BOOTSTRAP;
 if(location.protocol!=='file:'&&!location.hostname.endsWith('github.io')){
  try{d=await window.GEDIV_FETCH_DATA();}catch(err){console.warn('Usando esqueleto inicial:',err);}
 }
 window.GEDIV_DATA=d;
 return d;
})();"""
    )
    assert old_boot_script in html
    html = html.replace(old_boot_script, new_boot_script, 1)

    # 5. Atualizar groupNames e normalização de filtro de grupo para atender à Regra Especial da Etapa 8
    old_group_names = """const groupNames={'NAO_INFORMADO':'Grupo não informado','MAG':'MAG · Magistério','SAUDE':'Saúde','GAJ':'GAJ · Apoio Judiciário','FAP':'FAP · Fiscalização Agropecuária','TEC-ADM':'TEC-ADM · Técnicos Administrativos','ANS':'ANS · Nível Superior','ESPECIAL':'Grupo Especial','DPS':'DPS · Divulgação e Promoção','STF':'STF · Auditor Fiscal Tributário','OSPB':'OSPB · Orquestra Sinfônica','GPC':'GPC · Polícia Civil','SEI':'SEI · Informática','SAT':'SAT · Área Tecnológica','ACI':'ACI · Auditoria e Controle Interno','PPGG':'PPGG · Políticas Públicas e Gestão'};"""
    new_group_names = """const groupNames={'NAO_INFORMADO':'Grupo não informado','MAG':'MAG · Magistério','SSA':'SSA · Saúde','GAJ':'GAJ · Apoio Judiciário','FAP':'FAP · Fiscalização Agropecuária','AST':'AST · Técnicos Administrativos (PCCR)','PENDENTE:TEC. ADM':'TEC. ADM · Técnicos Administrativos (vínculo com AST pendente)','ANS':'ANS · Nível Superior','ESP':'ESP · Grupo Especial','DPS':'DPS · Divulgação e Promoção','SFT':'SFT · Serviço Fazendário Tributário (PCCR)','PENDENTE:STF':'STF · Auditor Fiscal Tributário (vínculo com SFT pendente)','OSPB':'OSPB · Orquestra Sinfônica','GPC':'GPC · Polícia Civil','SEI':'SEI · Informática','SAT':'SAT · Área Tecnológica','ACI':'ACI · Auditoria e Controle Interno','PPGG':'PPGG · Políticas Públicas e Gestão','INT':'INT · Interiorização'};
const GROUP_ALIASES={'TEC-ADM':'PENDENTE:TEC. ADM','TEC. ADM':'PENDENTE:TEC. ADM','STF':'PENDENTE:STF','SAUDE':'SSA','ESPECIAL':'ESP','GAJ-1700':'GAJ','FAP-1300':'FAP','ANS-900':'ANS','DPS-1600':'DPS','FAZENDA':'SFT'};
const resolveGroupKey=g=>GROUP_ALIASES[g]||g;"""
    assert old_group_names in html
    html = html.replace(old_group_names, new_group_names, 1)

    # Atualizar parseVerticalLevel para respeitar classe_anterior / classe_posterior já vindos do backend quando disponíveis
    old_parse_lvl = """function parseVerticalLevel(r){
 if(!r||r.axis!=='progressao'||r.modality!=='Vertical')return {from:'',to:'',transition:'',status:'',label:'',reason:''};
 if(r.merit==='indeferido')return {from:'',to:'',transition:'',status:'NI',label:'Nível não identificado',reason:'indeferido_sem_classe'};"""
    new_parse_lvl = """function parseVerticalLevel(r){
 if(!r||r.axis!=='progressao'||r.modality!=='Vertical')return {from:'',to:'',transition:'',status:'',label:'',reason:''};
 if(r.merit==='indeferido')return {from:'',to:'',transition:'',status:'NI',label:'Nível não identificado',reason:'indeferido_sem_classe'};
 const df=(r.detalhe?.classe_anterior||r.levelFrom||'').toUpperCase(),dtTo=(r.detalhe?.classe_posterior||r.levelTo||'').toUpperCase();
 if(/^[A-F]$/.test(df)&&/^[A-F]$/.test(dtTo)){
  if(df<dtTo)return {from:df,to:dtTo,transition:`${df} → ${dtTo}`,status:dtTo,label:`Nível ${dtTo}`,reason:'ok'};
  return {from:'',to:'',transition:'',status:'NI',label:'Nível não identificado',reason:'anomalia_ordem_ou_igual'};
 }"""
    assert old_parse_lvl in html
    html = html.replace(old_parse_lvl, new_parse_lvl, 1)

    # Em loadFromHash(), aceitar 'rejeitado' e resolver apelidos de grupos ('TEC-ADM' -> 'PENDENTE:TEC. ADM', etc.)
    old_hash_grp = """ S.validation=['pendente','conferido'].includes(p.get('validation'))?p.get('validation'):defVal;
 S.view=views[p.get('view')]?p.get('view'):'geral';
 S.axis=['progressao','tempo','outros'].includes(p.get('axis'))?p.get('axis'):'';
 S.modality=['Horizontal','Vertical'].includes(p.get('modality'))?p.get('modality'):'';
 S.group=groupNames[p.get('group')]?p.get('group'):'';"""
    new_hash_grp = """ S.validation=['pendente','conferido','rejeitado'].includes(p.get('validation'))?p.get('validation'):defVal;
 S.view=views[p.get('view')]?p.get('view'):'geral';
 S.axis=['progressao','tempo','outros'].includes(p.get('axis'))?p.get('axis'):'';
 S.modality=['Horizontal','Vertical'].includes(p.get('modality'))?p.get('modality'):'';
 const rawGrp=resolveGroupKey(p.get('group')||'');
 S.group=groupNames[rawGrp]?rawGrp:'';"""
    assert old_hash_grp in html
    html = html.replace(old_hash_grp, new_hash_grp, 1)

    # Em labelGroup, resolver apelido também
    html = html.replace(
        "const labelGroup=id=>groupNames[id]||id||'Grupo não informado';",
        "const labelGroup=id=>groupNames[resolveGroupKey(id)]||id||'Grupo não informado';",
        1,
    )

    # 5b. Melhorar a seção "Publicações e processos" (explorer) seguindo as mesmas regras visuais,
    # de privacidade (matrícula mascarada), acessibilidade e separação processos x ocorrências
    html = html.replace(
        '<button class="icon-btn" id="full" title="Ampliar tabela" aria-label="Ampliar tabela">↗</button>',
        '<button class="icon-btn" id="full" title="Ampliar tabela de publicações" aria-label="Ampliar tabela de publicações">⤢</button>',
        1,
    )
    old_records_fn = """function records(rows){let g=groups(rows),pages=Math.max(1,Math.ceil(g.length/5));S.page=Math.max(0,Math.min(S.page,pages-1));let shown=g.slice(S.page*5,S.page*5+5);if(!shown.some(x=>x.key===S.selected))S.selected=shown[0]?.key||'';
 $('#listHeading').textContent=S.mode==='resenha'?'RESENHA / ASSUNTO':'PROCESSO / SERVIDOR';$('#resultCount').textContent=`${rows.length} ${S.validation==='pendente'?'registros em conferência':'decisões conferidas'} · ${uniq(rows,'resenha_id')} ${uniq(rows,'resenha_id')===1?'resenha':'resenhas'} · ${uniq(rows,'process')} ${uniq(rows,'process')===1?'processo identificado':'processos identificados'}`;
 $('#records').innerHTML=shown.length?shown.map(x=>{let r=x.items[0],label=S.mode==='resenha'?'Resenha '+r.resenha:(r.process||'Processo não transcrito'),sub=S.mode==='resenha'?`${dt(r.date)} · ${labelRow(r)}`:`${r.server} · Resenha ${r.resenha}`;return `<button class="record ${S.selected===x.key?'selected':''}" data-select="${esc(x.key)}"><span><b>${esc(label)}</b><small>${esc(sub)}</small><small>${badge(r)}</small></span><span class="qty">${x.items.length} ›</span></button>`;}).join(''):emptyStateHtml('records');
 $('#pagination').textContent=g.length?`${S.page*5+1}–${Math.min((S.page+1)*5,g.length)} de ${g.length}`:'0 registros';$('#prev').disabled=S.page===0;$('#next').disabled=S.page>=pages-1;
 let sel=g.find(x=>x.key===S.selected);details(sel);
}"""
    new_records_fn = """function resenhaTitleFmt(r){
 const raw=String(r.resenha||'').trim();
 if(!raw)return 'Publicação sem número';
 return /^Resenha\\b/i.test(raw)?raw:'Resenha '+raw;
}
function records(rows){
 let g=groups(rows),pages=Math.max(1,Math.ceil(g.length/5));
 S.page=Math.max(0,Math.min(S.page,pages-1));
 let shown=g.slice(S.page*5,S.page*5+5);
 if(!shown.some(x=>x.key===S.selected))S.selected=shown[0]?.key||'';
 $('#listHeading').textContent=S.mode==='resenha'?'RESENHA / ASSUNTO':'PROCESSO / SERVIDOR';
 const resCnt=uniq(rows,'resenha_id'),procCnt=uniq(rows,'process');
 $('#resultCount').textContent=`${rows.length} ${S.validation==='pendente'?'registros em conferência':S.validation==='rejeitado'?'registros rejeitados':'decisões conferidas'} · ${resCnt} ${resCnt===1?'resenha':'resenhas'} · ${procCnt} ${procCnt===1?'processo identificado':'processos identificados'}`;
 $('#records').innerHTML=shown.length?shown.map(x=>{
  let r=x.items[0],defN=x.items.filter(i=>i.merit==='deferido').length,indN=x.items.filter(i=>i.merit==='indeferido').length;
  let dProcs=new Set(x.items.map(i=>String(i.process||'').trim().toUpperCase()).filter(Boolean)).size;
  let occN=x.items.length;
  let label=S.mode==='resenha'?resenhaTitleFmt(r):(r.process||NAO_EXTRAIDO);
  let modDesc=S.mode==='resenha'?(r.axis==='tempo'?(r.category?catName(r.category):'Tempo de Serviço'):labelRow(r)):`${r.server||NAO_EXTRAIDO} · ${maskMatricula(r.registration)} · ${resenhaTitleFmt(r)}`;
  let sub=S.mode==='resenha'?`${dt(r.date)} · ${modDesc}`:modDesc;
  let meritPills=S.mode==='resenha'
   ?`${defN?`<span class="res-pill is-pos" aria-label="${defN} deferidos">✓ ${defN} def.</span>`:''}${indN?`<span class="res-pill is-neg" aria-label="${indN} indeferidos">✕ ${indN} ind.</span>`:''}`
   :resultPill(r);
  let qtyMain=S.mode==='resenha'?(dProcs||occN):occN;
  let qtySub=S.mode==='resenha'&&dProcs>0&&dProcs!==occN?`<span class="rec-qty-sub">${occN} ocorr.</span>`:'';
  let qtyTip=S.mode==='resenha'?`${dProcs||occN} processo(s) distinto(s) · ${occN} ocorrência(s)`:`${occN} ocorrência(s)`;
  return `<button class="record ${S.selected===x.key?'selected':''}" data-select="${esc(x.key)}" aria-pressed="${S.selected===x.key?'true':'false'}"><span style="min-width:0"><b title="${esc(label)}">${esc(label)}</b><small title="${esc(sub)}">${esc(sub)}</small><span class="rec-pills">${badge(r)}${meritPills}</span></span><span class="rec-qty-wrap" title="${esc(qtyTip)}"><span class="qty">${qtyMain} ›</span>${qtySub}</span></button>`;
 }).join(''):emptyStateHtml('records');
 $('#pagination').textContent=g.length?`${S.page*5+1}–${Math.min((S.page+1)*5,g.length)} de ${g.length}`:'0 registros';
 $('#prev').disabled=S.page===0;$('#next').disabled=S.page>=pages-1;
 let sel=g.find(x=>x.key===S.selected);details(sel);
}"""
    assert old_records_fn in html
    html = html.replace(old_records_fn, new_records_fn, 1)

    # 5c. Melhorar "Evolução das publicações" (visão mensal empilhada/linhas sem rolagem horizontal + legenda clicável)
    old_tl_fn = """function timeline(rows){
 let dates=[...new Set(rows.map(r=>r.date))].sort();
 let n=dates.map(day=>({day,v:rows.filter(r=>r.date===day&&r.modality==='Vertical').length,h:rows.filter(r=>r.date===day&&r.modality==='Horizontal').length,t:rows.filter(r=>r.date===day&&r.axis==='tempo').length,o:rows.filter(r=>r.date===day&&r.axis==='outros').length}));
 let max=Math.max(1,...n.flatMap(q=>[q.v,q.h,q.t,q.o]));
 const seriesDefs=[['v','vertical','Vertical'],['h','horizontal','Horizontal'],['t','tempo','Tempo de Serviço'],['o','outros','Outros benefícios']];
 let activeFound=false,firstEnabledAssigned=false;
 $('#timeline').innerHTML=n.length?n.map(q=>`<div class="time-col"><div class="bar-set">${seriesDefs.map(([key,cl,lbl])=>{
  const enabled=q[key]>0,act=enabled&&isBarActive(q.day,cl);
  if(act)activeFound=true;
  return `<button class="${cl}${act?' active-bar':''}" data-day="${q.day}" data-series="${cl}" ${enabled?'':'disabled'} aria-pressed="${act}" title="${dt(q.day)} · ${lbl}: ${q[key]}" style="height:${Math.max(enabled?5:1,95*q[key]/max)}px"></button>`;
 }).join('')}</div><small>${shortDate(q.day)}</small></div>`).join(''):emptyStateHtml('timeline');
 $$('#timeline button[data-day]:not(:disabled)').forEach(btn=>{
  const isTarget=activeFound?btn.classList.contains('active-bar'):!firstEnabledAssigned;
  if(isTarget)firstEnabledAssigned=true;
  btn.setAttribute('tabindex',isTarget?'0':'-1');
 });
}"""
    new_tl_fn = """const MONTH_SHORT=['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
const TL_SERIES=[
 {k:'vertical',name:'Vertical',color:'#1265ef'},
 {k:'horizontal',name:'Horizontal',color:'#13b88a'},
 {k:'tempo',name:'Tempo de Serviço + Abono',color:'#ff973c'},
 {k:'outros',name:'Outros benefícios',color:'#7c5ce6'}
];
let tlChartMode='monthly', tlOffSeries=new Set(), lastTlRows=[];
function renderDelicateTimeline(rows){
 lastTlRows=rows||[];
 const tl=$('#timeline');if(!tl)return;
 const card=tl.closest('.card');if(!card)return;
 const legOrig=card.querySelector(':scope > .legend');
 const hdTag=card.querySelector('.card-heading .chart-tag');
 if(hdTag)hdTag.hidden=true;
 let bar=card.querySelector('.delicate-tl-bar');
 if(!bar){
  bar=document.createElement('div');bar.className='delicate-tl-bar';
  bar.innerHTML=`<span id="delicateTlSub" style="font-size:11px;color:#405d79">Composição mensal por modalidade · sem rolagem horizontal</span>
   <div class="delicate-seg" role="group" aria-label="Modo de visualização temporal">
    <button type="button" data-dl-tl="monthly" class="active">Empilhadas (Mês)</button>
    <button type="button" data-dl-tl="lines">Linhas (Mês)</button>
    <button type="button" data-dl-tl="daily">Diário</button>
   </div>`;
  tl.parentElement.insertBefore(bar,tl);
  bar.querySelectorAll('[data-dl-tl]').forEach(b=>b.addEventListener('click',()=>{
   tlChartMode=b.dataset.dlTl;
   bar.querySelectorAll('[data-dl-tl]').forEach(x=>x.classList.toggle('active',x===b));
   renderDelicateTimeline(lastTlRows);
  }));
 }
 let wrap=card.querySelector('#delicateTlWrap');
 if(!wrap){wrap=document.createElement('div');wrap.id='delicateTlWrap';tl.parentElement.insertBefore(wrap,tl);}
 if(tlChartMode==='daily'||!lastTlRows.length){
  wrap.hidden=true;tl.style.display='';if(legOrig)legOrig.style.display='';
  return;
 }
 tl.style.display='none';if(legOrig)legOrig.style.display='none';wrap.hidden=false;
 const byMonth={};
 lastTlRows.forEach(r=>{
  const d=String(r.date||'');if(d.length<7)return;
  const ym=d.slice(0,7);
  if(!byMonth[ym])byMonth[ym]={ym,vertical:0,horizontal:0,tempo:0,outros:0};
  if(r.axis==='tempo')byMonth[ym].tempo++;
  else if(r.axis==='outros')byMonth[ym].outros++;
  else if(r.modality==='Horizontal')byMonth[ym].horizontal++;
  else byMonth[ym].vertical++;
 });
 const months=Object.values(byMonth).sort((a,b)=>a.ym.localeCompare(b.ym));
 const active=TL_SERIES.filter(s=>!tlOffSeries.has(s.k));
 const subEl=$('#delicateTlSub');
 if(subEl)subEl.textContent=tlChartMode==='lines'?'Tendência mensal por modalidade · clique na legenda para isolar séries':'Composição mensal por modalidade · sem rolagem horizontal';
 const W=620,H=168,padL=38,padR=14,padT=14,padB=24,plotW=W-padL-padR,plotH=H-padT-padB;
 const step=plotW/Math.max(1,months.length),barW=Math.min(34,Math.max(14,step*0.58));
 let svg=`<line x1="${padL}" y1="${padT}" x2="${W-padR}" y2="${padT}" stroke="#e5edf5"/>
  <line x1="${padL}" y1="${padT+plotH/2}" x2="${W-padR}" y2="${padT+plotH/2}" stroke="#e5edf5"/>
  <line x1="${padL}" y1="${padT+plotH}" x2="${W-padR}" y2="${padT+plotH}" stroke="#d5e3f1"/>`;
 if(tlChartMode==='lines'){
  const maxV=Math.max(1,...months.flatMap(m=>active.map(s=>m[s.k])));
  svg+=`<text x="${padL-6}" y="${padT+4}" font-size="9.5" fill="#405d79" text-anchor="end">${maxV}</text>
        <text x="${padL-6}" y="${padT+plotH/2+4}" font-size="9.5" fill="#405d79" text-anchor="end">${Math.round(maxV/2)}</text>
        <text x="${padL-6}" y="${padT+plotH+3}" font-size="9.5" fill="#405d79" text-anchor="end">0</text>`;
  active.forEach(s=>{
   const pts=months.map((m,i)=>`${(padL+step*i+step/2).toFixed(1)},${(padT+plotH-(plotH*m[s.k]/maxV)).toFixed(1)}`).join(' ');
   svg+=`<polyline fill="none" stroke="${s.color}" stroke-width="2.3" points="${pts}"/>`;
   months.forEach((m,i)=>{
    const cx=(padL+step*i+step/2).toFixed(1),cy=(padT+plotH-(plotH*m[s.k]/maxV)).toFixed(1);
    const lbl=MONTH_SHORT[Number(m.ym.slice(5,7))-1]+'/'+m.ym.slice(2,4);
    const tip=`${lbl} · ${s.name}: ${m[s.k]} | Total no recorte do mês: ${m.vertical+m.horizontal+m.tempo+m.outros}`;
    svg+=`<circle cx="${cx}" cy="${cy}" r="4" fill="${s.color}" tabindex="0" role="button" aria-label="${esc(tip)}" data-dtip="${esc(tip)}"/>`;
   });
  });
 }else{
  const maxT=Math.max(1,...months.map(m=>active.reduce((a,s)=>a+m[s.k],0)));
  svg+=`<text x="${padL-6}" y="${padT+4}" font-size="9.5" fill="#405d79" text-anchor="end">${maxT}</text>
        <text x="${padL-6}" y="${padT+plotH/2+4}" font-size="9.5" fill="#405d79" text-anchor="end">${Math.round(maxT/2)}</text>
        <text x="${padL-6}" y="${padT+plotH+3}" font-size="9.5" fill="#405d79" text-anchor="end">0</text>`;
  months.forEach((m,i)=>{
   let y=padT+plotH;const x=padL+step*i+(step-barW)/2;
   const lbl=MONTH_SHORT[Number(m.ym.slice(5,7))-1]+'/'+m.ym.slice(2,4);
   const tot=m.vertical+m.horizontal+m.tempo+m.outros;
   const tip=`${lbl} · Total: ${tot} (Vertical: ${m.vertical} · Horizontal: ${m.horizontal} · Tempo+Abono: ${m.tempo} · Outros: ${m.outros})`;
   let rects='';
   active.forEach(s=>{
    if(!m[s.k])return;
    const bh=Math.max(3,plotH*m[s.k]/maxT);y-=bh;
    rects+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${bh.toFixed(1)}" rx="1.5" fill="${s.color}"/>`;
   });
   svg+=`<g tabindex="0" role="button" aria-label="${esc(tip)}" data-dtip="${esc(tip)}">${rects}<rect x="${x.toFixed(1)}" y="${padT}" width="${barW.toFixed(1)}" height="${plotH}" fill="transparent"/></g>`;
  });
 }
 months.forEach((m,i)=>{
  const cx=(padL+step*i+step/2).toFixed(1),lbl=MONTH_SHORT[Number(m.ym.slice(5,7))-1];
  svg+=`<text x="${cx}" y="${H-6}" font-size="9.5" fill="#405d79" text-anchor="middle">${lbl}</text>`;
 });
 const totals={vertical:lastTlRows.filter(r=>r.axis==='progressao'&&r.modality!=='Horizontal').length,horizontal:lastTlRows.filter(r=>r.axis==='progressao'&&r.modality==='Horizontal').length,tempo:lastTlRows.filter(r=>r.axis==='tempo').length,outros:lastTlRows.filter(r=>r.axis==='outros').length};
 wrap.innerHTML=`<svg class="delicate-tl-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolução mensal das publicações">${svg}</svg>
  <div class="delicate-tl-leg">${TL_SERIES.map(s=>`<button type="button" class="delicate-lg-btn ${tlOffSeries.has(s.k)?'is-off':''}" data-tl-ser="${s.k}" aria-pressed="${!tlOffSeries.has(s.k)}"><i class="delicate-lg-dot" style="background:${s.color}"></i>${s.name} (${totals[s.k]})</button>`).join('')}</div>
  <div class="delicate-tl-tip" id="delicateTlTip" role="status">Passe o mouse ou foque em um mês para ver a composição · clique na legenda para isolar séries.</div>
  <div class="delicate-tl-note">Lacunas ou ausência de barra refletem falta de coleta no intervalo ou filtro aplicado — nunca equivalem a zero publicações confirmadas.</div>`;
 wrap.querySelectorAll('[data-tl-ser]').forEach(b=>b.addEventListener('click',()=>{
  const k=b.dataset.tlSer;
  if(tlOffSeries.has(k))tlOffSeries.delete(k);else if(tlOffSeries.size<TL_SERIES.length-1)tlOffSeries.add(k);
  renderDelicateTimeline(lastTlRows);
 }));
 wrap.querySelectorAll('[data-dtip]').forEach(el=>{
  const showTip=()=>{const t=$('#delicateTlTip');if(t)t.textContent=el.dataset.dtip;};
  el.addEventListener('mouseenter',showTip);el.addEventListener('focus',showTip);el.addEventListener('click',showTip);
 });
}
function timeline(rows){
 let dates=[...new Set(rows.map(r=>r.date))].sort();
 let n=dates.map(day=>({day,v:rows.filter(r=>r.date===day&&r.modality==='Vertical').length,h:rows.filter(r=>r.date===day&&r.modality==='Horizontal').length,t:rows.filter(r=>r.date===day&&r.axis==='tempo').length,o:rows.filter(r=>r.date===day&&r.axis==='outros').length}));
 let max=Math.max(1,...n.flatMap(q=>[q.v,q.h,q.t,q.o]));
 const seriesDefs=[['v','vertical','Vertical'],['h','horizontal','Horizontal'],['t','tempo','Tempo de Serviço'],['o','outros','Outros benefícios']];
 let activeFound=false,firstEnabledAssigned=false;
 $('#timeline').innerHTML=n.length?n.map(q=>`<div class="time-col"><div class="bar-set">${seriesDefs.map(([key,cl,lbl])=>{
  const enabled=q[key]>0,act=enabled&&isBarActive(q.day,cl);
  if(act)activeFound=true;
  return `<button class="${cl}${act?' active-bar':''}" data-day="${q.day}" data-series="${cl}" ${enabled?'':'disabled'} aria-pressed="${act}" title="${dt(q.day)} · ${lbl}: ${q[key]}" style="height:${Math.max(enabled?5:1,95*q[key]/max)}px"></button>`;
 }).join('')}</div><small>${shortDate(q.day)}</small></div>`).join(''):emptyStateHtml('timeline');
 $$('#timeline button[data-day]:not(:disabled)').forEach(btn=>{
  const isTarget=activeFound?btn.classList.contains('active-bar'):!firstEnabledAssigned;
  if(isTarget)firstEnabledAssigned=true;
  btn.setAttribute('tabindex',isTarget?'0':'-1');
 });
 renderDelicateTimeline(rows);
}"""
    assert old_tl_fn in html
    html = html.replace(old_tl_fn, new_tl_fn, 1)

    # 5d. Proteger exportXlsx() e exportCsv() no modo público para zero vazamento e explicitar escopo
    old_exports = """function exportXlsx(){let m=model(),summary=[['Visão',views[S.view][1]],['Filtros',filterText()],['Cobertura',data.meta.coverage],['Atualização',data.meta.automation],[],['Indicador','Valor'],...Object.entries(m.metrics)],list=[['Resenha / processo','Assunto','Resultado','Data','Quantidade'],...exportRows()];exp.download(exp.xlsx({'Resumo':summary,'Visão selecionada':list,'Decisões':decisionRows()}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-visao-selecionada.xlsx');toast('Planilha da visão selecionada gerada.');}
function exportCsv(){exp.download(exp.csv(decisionRows()),'text/csv;charset=utf-8','GEDIV-decisoes-filtradas.csv');toast('Lista filtrada gerada.');}"""
    new_exports = """function exportXlsx(){
 let isAuth=!!data.backend?.autenticado,m=model();
 let summary=[['Visão',views[S.view][1]],['Escopo',isAuth?m.label:'Público (somente agregados)'],['Filtros',filterText()],['Cobertura',data.meta.coverage],[],['Indicador','Valor'],...Object.entries(m.metrics)];
 if(!isAuth){
  exp.download(exp.xlsx({'Resumo':summary}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-resumo-publico.xlsx');
  toast('Resumo agregado gerado (dados individuais protegidos).');return;
 }
 let list=[['Resenha / processo','Assunto','Resultado','Data','Quantidade'],...exportRows()];
 exp.download(exp.xlsx({'Resumo':summary,'Visão selecionada':list,'Decisões':decisionRows()}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-visao-selecionada.xlsx');
 toast('Planilha da visão selecionada gerada.');
}
function exportCsv(){
 if(!data.backend?.autenticado){toast('Lista individual (.csv) disponível apenas após login gerencial.');return;}
 exp.download(exp.csv(decisionRows()),'text/csv;charset=utf-8','GEDIV-decisoes-filtradas.csv');toast('Lista filtrada gerada.');
}"""
    assert old_exports in html
    html = html.replace(old_exports, new_exports, 1)

    # 6. Em details(sel) e detailDialog(sel), implementar exclusivamente as 3 partes aprovadas:
    # Parte 1 (Processos da Resenha), Parte 2 (Detalhes do processo selecionado) e Parte 3 (Modal Registro documental)
    old_details = """function details(sel){if(!sel){$('#details').innerHTML='<div class="empty-small">Selecione uma publicação para ver os detalhes.</div>';return;}let r=sel.items[0],ev=data.events.filter(e=>r.act&&e.act===r.act&&e.validation==='conferido'),url=official(r.url,r.page),lvInfo=levelSummaryForSelection(sel.items),assunto=lvInfo?`${labelRow(r)} · ${lvInfo}`:labelRow(r),pages=[...new Set(sel.items.map(x=>Number(x.page)).filter(Boolean))].sort((a,b)=>a-b),pageTxt=pages.length?pages.join(', '):esc(r.page);$('#details').innerHTML=`<div class="detail-grid"><span class="dt">Publicação</span><span class="dd">${dt(r.date)}</span><span class="dt">Resenha</span><span class="dd">${esc(r.resenha)}</span><span class="dt">Assunto</span><span class="dd">${esc(assunto)}</span><span class="dt">Grupo</span><span class="dd">${esc(r.axis==='progressao'?labelGroup(r.group):'—')}</span><span class="dt">Resultado</span><span class="dd">${meritBadge(r)}</span><span class="dt">Registros</span><span class="dd">${sel.items.length} nesta seleção</span><span class="dt">Conferência</span><span class="dd">${S.validation==='pendente'?'Pendente · dados preliminares':'Conferido'}</span><span class="dt">Página DOE</span><span class="dd">${pageTxt}</span><span class="dt">Alterações</span><span class="dd">${ev.length?esc(ev[0].type)+' em '+dt(ev[0].date):'Não identificada na amostra'}</span></div><div class="detail-actions">${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">↗ Abrir PDF oficial</a>`:''}<button id="showDetails">Ver processos / histórico</button></div>`;$('#showDetails')?.addEventListener('click',()=>detailDialog(sel));}"""
    new_details = """const NAO_EXTRAIDO='Não extraído neste recorte';
let activeProcId='';
function maskMatricula(v){
 const raw=String(v||'').trim();if(!raw)return NAO_EXTRAIDO;
 const digits=raw.replace(/\\D/g,'');
 if(digits.length<=2)return '*****';
 return '*****'+digits.slice(-2);
}
function axisTitle(r){return r.axis==='progressao'?'Progressão Funcional':r.axis==='tempo'?'Tempo de Serviço':'Outros benefícios';}
function modalityFull(r){
 if(r.axis==='progressao'){
  if(r.modality==='Vertical'){
   if(r.levelTo)return `Progressão Vertical · Nível ${r.levelTo}${r.levelTransition?' ('+r.levelTransition+')':''}`;
   return 'Progressão Vertical · Nível não identificado';
  }
  return r.modality==='Horizontal'?'Progressão Horizontal':'Progressão Funcional';
 }
 if(r.axis==='tempo')return r.category?catName(r.category):'Tempo de Serviço';
 return labelRow(r)||'Outros benefícios';
}
function modalityCompact(r){
 if(r.axis==='progressao'&&r.modality==='Vertical')return r.levelTo?`Vertical · ${r.levelTo}`:'Vertical · NI';
 if(r.axis==='progressao'&&r.modality==='Horizontal')return 'Horizontal';
 if(r.axis==='tempo')return r.category?catName(r.category):'Tempo de Serviço';
 return labelRow(r)||'Outros';
}
function resultPill(r){
 if(r.merit==='deferido')return '<span class="res-pill is-pos" aria-label="Deferido">✓ Deferido</span>';
 if(r.merit==='indeferido')return '<span class="res-pill is-neg" aria-label="Indeferido">✕ Indeferido</span>';
 return '<span class="res-pill is-neu" aria-label="Outro resultado">• Outro</span>';
}
function resenhaShort(r){
 const s=String(r.resenha||'').trim();
 if(!s)return 'Sem número';
 return s.split('·')[0].replace(/^Resenha\\s*(n[º°]\\s*)?/i,'').trim()||s;
}
function doeLink(r){return official(r.url,r.page)||r.urlOficial||r.pdfNoAcervo||'';}
function pdfAcervoLink(r){return r.pdfNoAcervo||doeLink(r)||'';}
async function openAuthPdf(url){
 if(!url)return;
 if(!url.startsWith('/api/pdf/')){window.open(url,'_blank','noopener,noreferrer');return;}
 const [base,hash]=url.split('#');
 try{
  const resp=await fetch(base,{headers:window.GEDIV_AUTH.headers()});
  if(!resp.ok)throw new Error('HTTP '+resp.status);
  const blob=await resp.blob();
  const objUrl=URL.createObjectURL(blob)+(hash?'#'+hash:'');
  window.open(objUrl,'_blank','noopener,noreferrer');
  setTimeout(()=>URL.revokeObjectURL(objUrl.split('#')[0]),60000);
 }catch(err){toast('Não foi possível abrir o PDF oficial: '+err.message);}
}
const SVG_BOOK='<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>';
const SVG_SHIELD='<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>';
function exportResenhaCsv(sel){
 const items=sel?.items||[];if(!items.length)return;
 const header=['Resenha','Data','Servidor','Matricula_Mascarada','Processo','Eixo','Modalidade','Grupo','Resultado','Pagina_DOE','Situacao'];
 const escCsv=v=>`"${String(v??'').replace(/"/g,'""')}"`;
 const lines=[header.map(escCsv).join(';')].concat(items.map(x=>[
  x.resenha,dt(x.date),x.server,maskMatricula(x.registration),x.process||'',axisTitle(x),modalityFull(x),
  x.axis==='progressao'?labelGroup(x.group):'',x.merit,x.page||'',x.validation
 ].map(escCsv).join(';')));
 const blob=new Blob(['\\ufeff'+lines.join('\\r\\n')],{type:'text/csv;charset=utf-8'});
 const a=document.createElement('a');
 a.href=URL.createObjectURL(blob);
 a.download='GEDIV-resenha-'+resenhaShort(items[0]).replace(/[^a-zA-Z0-9_-]+/g,'-')+'.csv';
 document.body.appendChild(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(a.href),1500);
 toast(`Exportação da resenha (${items.length} registro(s)) iniciada.`);
}
function openDocModal(r,sel){
 if(!r)return;
 const isAuth=!!data.backend?.autenticado,doe=doeLink(r),pdf=pdfAcervoLink(r);
 const pageTxt=r.page?String(r.page):'—';
 const valLabel=r.validation==='conferido'?'Conferido':r.validation==='rejeitado'?'Rejeitado':'Em conferência';
 const mentionTxt=r.sourceMention==='expresso'?'Expressa no bloco':'Não expressa no bloco';
 const natTxt=r.natureza?String(r.natureza).toLowerCase():'original';
 const field=(lbl,val)=>{
  const empty=!val||String(val).trim()===''||String(val).trim()==='—';
  return `<div class="doc-field"><span class="doc-field-lbl">${esc(lbl)}</span><span class="doc-field-val ${empty?'is-empty':''}">${esc(empty?NAO_EXTRAIDO:val)}</span></div>`;
 };
 $('#docModalId').textContent=`Registro documental · ${r.id||r.process||'sem-id'}`;
 const modPillClass=r.axis==='progressao'?'doc-pill is-prog':'doc-pill';
 const clsAnt=r.levelFrom?`Classe ${r.levelFrom}`:'';
 const clsAtu=r.levelTo?`Classe ${r.levelTo}`:'';
 const orgaoVal=r.orgao||(String(r.resenha||'').includes('·')?String(r.resenha).split('·')[1].trim():'');
 $('#docModalBody').innerHTML=`
  <div class="doc-badges"><span class="${modPillClass}">${esc(modalityFull(r))}</span>${resultPill(r)}<span class="doc-pill">${esc(valLabel)}</span></div>
  <h2 id="docModalTitle" class="doc-name">${esc(r.server||NAO_EXTRAIDO)}</h2>
  <p class="doc-proc">${esc(r.process||NAO_EXTRAIDO)}</p>
  <div class="doc-meta-box">
   ${field('Nome do servidor',r.server)}
   ${field('Matrícula',maskMatricula(r.registration))}
   ${field('Órgão',orgaoVal)}
   ${field('Cargo',r.cargo)}
   ${field('Data da publicação',dt(r.date))}
   ${field('Resenha / ato',r.resenha)}
   ${field('Página no PDF',r.page?String(r.page):'')}
   ${field('Menção à GEDIV',mentionTxt)}
   ${field('Tipo de ato',String(r.actType||'resenha').toLowerCase())}
   ${field('Natureza da publicação',natTxt)}
   ${r.axis==='progressao'?field('Grupo ocupacional',labelGroup(r.group)):''}
   ${field('Resultado original',r.resultadoOriginal||(r.merit==='deferido'?'DEFERIDO':r.merit==='indeferido'?'INDEFERIDO':''))}
   ${field('Classe / nível anterior',clsAnt)}
   ${field('Classe / nível atual',clsAtu)}
   ${field('Origem do tempo',r.origemTempo)}
  </div>
  ${r.preliminaryReview?`<div class="prelim-note"><b>Nota preliminar:</b> ${esc(r.preliminaryReview)}</div>`:''}`;
 $('#docModalFoot').innerHTML=`
  <div class="doc-foot-left">
   ${doe?`<a class="sel-btn-pri" data-doc-pdf="${esc(doe)}" href="${esc(doe)}" target="_blank" rel="noopener noreferrer">↗ Abrir página ${esc(pageTxt)} no DOE</a>`:`<button type="button" class="sel-btn-pri" disabled title="Documento oficial indisponível neste recorte">↗ Página no DOE indisponível</button>`}
   ${pdf?`<a class="sel-btn-sec" data-doc-pdf="${esc(pdf)}" href="${esc(pdf)}" target="_blank" rel="noopener noreferrer">↓ Acessar PDF oficial</a>`:`<button type="button" class="sel-btn-sec" disabled title="PDF indisponível neste recorte">↓ PDF indisponível</button>`}
  </div>
  ${isAuth&&r.axis!=='outros'?`<button type="button" id="docModalReviewBtn" class="sel-btn-sec">Revisar / Conferir</button>`:''}`;
 $$('#docModalFoot a[data-doc-pdf]').forEach(a=>a.addEventListener('click',e=>{if(a.dataset.docPdf.startsWith('/api/pdf/')){e.preventDefault();openAuthPdf(a.dataset.docPdf);}}));
 $('#docModalReviewBtn')?.addEventListener('click',()=>{$('#docModal').close();openReviewModal('decisao',[r]);});
 const dlg=$('#docModal');if(!dlg.open)dlg.showModal();
 $('#closeDocModal')?.focus();
}
function details(sel){
 const host=$('#details');
 if(!sel||!sel.items||!sel.items.length){host.innerHTML='<div class="empty-small">Selecione uma publicação para ver os detalhes.</div>';return;}
 const items=sel.items;
 let active=items.find(x=>x.id===activeProcId)||items[0];
 activeProcId=active.id;
 const distinctProcs=new Set(items.map(x=>String(x.process||'').trim().toUpperCase()).filter(Boolean)).size;
 const occCount=items.length;
 const procLabel=distinctProcs===1?'1 processo':`${distinctProcs} processos`;
 const occLabel=occCount===1?'1 ocorrência na publicação selecionada':`${occCount} ocorrências na publicação selecionada`;
 const resNum=resenhaShort(items[0]);
 const isAuth=!!data.backend?.autenticado;
 const visibleItems=items.slice(0,50);
 const renderSelectedCard=r=>{
  const doe=doeLink(r),pdf=pdfAcervoLink(r),pg=r.page?String(r.page):'—';
  const valTxt=r.validation==='conferido'?'Conferido':r.validation==='rejeitado'?'Rejeitado na triagem':'Em conferência documental';
  const cardEl=$('#selectedProcCard');
  if(!cardEl)return;
  cardEl.innerHTML=`
   <div class="sel-head">
    <h3 class="proc-title">Detalhes do processo selecionado</h3>
    <button type="button" id="expandDocBtn" class="sel-expand-btn" title="Expandir registro documental" aria-label="Expandir detalhes do processo selecionado">⤢</button>
   </div>
   <div class="sel-grid">
    <span class="sel-dt">Nome do servidor</span><span class="sel-dd ${!r.server?'is-muted':''}">${esc(r.server||NAO_EXTRAIDO)}</span>
    <span class="sel-dt">Matrícula</span><span class="sel-dd ${!r.registration?'is-muted':''}">${esc(maskMatricula(r.registration))}</span>
    <span class="sel-dt">Processo</span><span class="sel-dd ${!r.process?'is-muted':''}">${esc(r.process||NAO_EXTRAIDO)}</span>
    <span class="sel-dt">Eixo</span><span class="sel-dd">${esc(axisTitle(r))}</span>
    <span class="sel-dt">Modalidade</span><span class="sel-dd">${esc(modalityFull(r))}</span>
    ${r.axis==='progressao'?`<span class="sel-dt">Grupo</span><span class="sel-dd">${esc(labelGroup(r.group))}</span>`:''}
    <span class="sel-dt">Resultado</span><span class="sel-dd">${resultPill(r)}</span>
    <span class="sel-dt">Data da publicação</span><span class="sel-dd">${esc(dt(r.date))}</span>
    <span class="sel-dt">Resenha / ato</span><span class="sel-dd">${esc(r.resenha||NAO_EXTRAIDO)}</span>
    <span class="sel-dt">Página no DOE</span><span class="sel-dd"><span class="sel-page-badge">${esc(pg)}</span></span>
   </div>
   ${r.preliminaryReview?`<div class="prelim-note"><b>Nota preliminar:</b> ${esc(r.preliminaryReview)}</div>`:''}
   <div class="sel-doe-box">
    <div class="sel-doe-left">
     <span class="sel-doe-ico" aria-hidden="true">${SVG_BOOK}</span>
     <div><div class="sel-doe-title">Diário Oficial da Paraíba</div><div class="sel-doe-sub">${esc(dt(r.date))} · página ${esc(pg)}</div></div>
    </div>
    <span class="sel-doe-shield" title="Fonte oficial verificada" aria-hidden="true">${SVG_SHIELD}</span>
   </div>
   <div class="sel-actions">
    ${doe?`<a class="sel-btn-pri" data-doc-pdf="${esc(doe)}" href="${esc(doe)}" target="_blank" rel="noopener noreferrer">↗ Abrir página ${esc(pg)} no DOE</a>`:`<button type="button" class="sel-btn-pri" disabled title="Documento indisponível neste recorte">↗ Abrir página no DOE</button>`}
    ${pdf?`<a class="sel-btn-sec" data-doc-pdf="${esc(pdf)}" href="${esc(pdf)}" target="_blank" rel="noopener noreferrer">↓ PDF oficial</a>`:`<button type="button" class="sel-btn-sec" disabled title="PDF indisponível neste recorte">↓ PDF oficial</button>`}
   </div>
   ${isAuth&&r.axis!=='outros'?`<div class="sel-review-strip"><span class="sel-review-state ${r.validation==='conferido'?'is-conf':''}">Situação: ${esc(valTxt)}</span><button type="button" id="reviewSelectionBtn" class="sel-btn-sec" style="min-height:30px;padding:4px 10px">Revisar / Conferir</button></div>`:''}
   <div class="sel-hist-wrap"><button type="button" id="openDocEvidenceBtn" class="proc-link-btn">Ver evidência e histórico do processo →</button></div>`;
  $$('#selectedProcCard a[data-doc-pdf]').forEach(a=>a.addEventListener('click',e=>{if(a.dataset.docPdf.startsWith('/api/pdf/')){e.preventDefault();openAuthPdf(a.dataset.docPdf);}}));
  $('#expandDocBtn')?.addEventListener('click',()=>openDocModal(r,sel));
  $('#openDocEvidenceBtn')?.addEventListener('click',()=>openDocModal(r,sel));
  $('#reviewSelectionBtn')?.addEventListener('click',()=>openReviewModal('decisao',[r]));
 };
 host.innerHTML=`<div class="proc-stack">
  <div class="proc-card" id="resenhaProcessesCard">
   <div class="proc-head">
    <div>
     <h3 class="proc-title">Processos da Resenha ${esc(resNum)} <span>(${esc(procLabel)})</span></h3>
     <p class="proc-sub">${esc(occLabel)}</p>
    </div>
    <button type="button" id="exportResenhaBtn" class="proc-export-btn" aria-label="Exportar processos desta resenha">↓ Exportar</button>
   </div>
   <div class="proc-table-wrap" role="region" aria-label="Tabela de processos da resenha">
    <table class="proc-table">
     <thead><tr><th>Nome do servidor</th><th>Matrícula</th><th>Processo</th><th>Modalidade</th><th>Resultado</th></tr></thead>
     <tbody>${visibleItems.map(x=>`<tr tabindex="0" data-proc-id="${esc(x.id)}" class="${x.id===active.id?'is-active':''}" aria-selected="${x.id===active.id?'true':'false'}"><td title="${esc(x.server||NAO_EXTRAIDO)}">${esc(x.server||NAO_EXTRAIDO)}</td><td title="Matrícula mascarada">${esc(maskMatricula(x.registration))}</td><td title="${esc(x.process||NAO_EXTRAIDO)}">${esc(x.process||NAO_EXTRAIDO)}</td><td title="${esc(modalityFull(x))}">${esc(modalityCompact(x))}</td><td>${resultPill(x)}</td></tr>`).join('')}</tbody>
    </table>
   </div>
   <div class="proc-footer"><button type="button" id="showDetails" class="proc-link-btn">Ver todos os ${occCount} registros →</button></div>
  </div>
  <div class="sel-card" id="selectedProcCard"></div>
 </div>`;
 renderSelectedCard(active);
 $('#exportResenhaBtn')?.addEventListener('click',()=>exportResenhaCsv(sel));
 $('#showDetails')?.addEventListener('click',()=>detailDialog(sel));
 $$('#resenhaProcessesCard tbody tr[data-proc-id]').forEach(tr=>{
  const selectRow=()=>{
   const found=items.find(x=>x.id===tr.dataset.procId);if(!found)return;
   activeProcId=found.id;
   $$('#resenhaProcessesCard tbody tr[data-proc-id]').forEach(el=>{const on=el===tr;el.classList.toggle('is-active',on);el.setAttribute('aria-selected',on?'true':'false');});
   renderSelectedCard(found);
  };
  tr.addEventListener('click',selectRow);
  tr.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectRow();}});
 });
}"""
    assert old_details in html
    html = html.replace(old_details, new_details, 1)

    old_detail_dialog = """function detailDialog(sel){let r=sel.items[0],events=data.events.filter(e=>r.act&&e.act===r.act&&e.validation==='conferido'),hasVert=sel.items.some(x=>x.axis==='progressao'&&x.modality==='Vertical');let body=`<p>Resenha <b>${esc(r.resenha)}</b> · ${esc(labelRow(r))} · ${dt(r.date)}.</p><div class="table-scroll"><table class="dialog-table is-cards-sm"><thead><tr><th>Processo</th><th>Servidor</th>${hasVert?'<th>Nível (A–F)</th>':''}<th>Resultado</th></tr></thead><tbody>${sel.items.map(x=>`<tr><td data-label="Processo">${esc(x.process||'Não transcrito')}</td><td data-label="Servidor">${esc(x.server)}</td>${hasVert?`<td class="nowrap" data-label="Nível (A–F)">${esc(x.levelTo?`${x.levelLabel} (${x.levelTransition})`:(x.levelLabel||'—'))}</td>`:''}<td data-label="Resultado">${meritBadge(x)}</td></tr>`).join('')}</tbody></table></div>`;if(events.length)body+=`<p><b>Histórico documental</b></p>${events.map(e=>`<p>${esc(e.type)} em ${dt(e.date)}: ${esc(e.description)} ${official(e.url,e.page)?`<a target="_blank" rel="noopener noreferrer" href="${esc(official(e.url,e.page))}">Abrir publicação da alteração</a>`:''}</p>`).join('')}`;openDialog('Processos e histórico',body,{wide:hasVert});}"""
    new_detail_dialog = """function detailDialog(sel){let r=sel.items[0],events=data.events.filter(e=>r.act&&e.act===r.act&&e.validation==='conferido'),hasVert=sel.items.some(x=>x.axis==='progressao'&&x.modality==='Vertical'),isAuth=!!data.backend?.autenticado;let body=`<p>Resenha <b>${esc(r.resenha)}</b> · ${esc(labelRow(r))} · ${dt(r.date)}.</p><div class="table-scroll"><table class="dialog-table is-cards-sm"><thead><tr><th>Processo</th><th>Servidor</th><th>Matrícula</th>${hasVert?'<th>Nível (A–F)</th>':''}<th>Resultado</th><th>Situação</th>${isAuth?'<th class="nowrap">Revisão</th>':''}</tr></thead><tbody>${sel.items.map(x=>`<tr><td data-label="Processo">${esc(x.process||'Não transcrito')}</td><td data-label="Servidor">${esc(x.server)}${x.preliminaryReview?`<div class="prelim-note">${esc(x.preliminaryReview)}</div>`:''}</td><td class="nowrap" data-label="Matrícula">${esc(maskMatricula(x.registration))}</td>${hasVert?`<td class="nowrap" data-label="Nível (A–F)">${esc(x.levelTo?`${x.levelLabel} (${x.levelTransition})`:(x.levelLabel||'—'))}</td>`:''}<td data-label="Resultado">${meritBadge(x)}</td><td class="nowrap" data-label="Situação">${esc(x.validation)}</td>${isAuth?`<td class="nowrap" data-label="Revisão">${x.axis!=='outros'?`<button type="button" class="pdf-link" style="border:0;background:none;padding:0" data-review-row="${esc(x.id)}">Revisar →</button>`:'—'}</td>`:''}</tr>`).join('')}</tbody></table></div>`;if(events.length)body+=`<p><b>Histórico documental</b></p>${events.map(e=>`<p>${esc(e.type)} em ${dt(e.date)}: ${esc(e.description)} ${official(e.url,e.page)?`<a target="_blank" rel="noopener noreferrer" href="${esc(official(e.url,e.page))}">Abrir publicação da alteração</a>`:''}</p>`).join('')}`;openDialog('Processos e histórico',body,{wide:true});$$('#dialogBody [data-review-row]').forEach(btn=>btn.addEventListener('click',()=>{const item=sel.items.find(i=>i.id===btn.dataset.reviewRow);if(item){$('#dialog').close();openReviewModal('decisao',[item]);}}));}"""
    assert old_detail_dialog in html
    html = html.replace(old_detail_dialog, new_detail_dialog, 1)

    # 7. Em openPendingEventsModal(), adicionar ação de revisão / vinculação para perfil gerencial
    old_events_modal = """function openPendingEventsModal(){
 const pendingEvents=(data.events||[]).filter(e=>e.validation==='pendente');
 const sumTxt=txt=>{
  const s=String(txt||'').replace(/\\s+/g,' ').trim();
  const resM=s.match(/RESENHA\\s+N[º°]?\\s*:?\\s*(\\d+\\/\\d+)/i),portM=s.match(/Portaria\\s+n[º°]\\s*(\\d+\\/\\d+(?:\\s*-\\s*[A-Z]+)?)/i),procM=s.match(/SAD-PSE-\\d{4}\\/\\d+/i);
  const parts=[];if(resM)parts.push('Resenha '+resM[1]);else if(portM)parts.push('Portaria '+portM[1]);if(procM)parts.push(procM[0]);
  return parts.length?parts.join(' · '):s.slice(0,80);
 };
 const body=`<div class="reconcile-note" style="margin-top:0;margin-bottom:12px"><b>Conferência documental pendente:</b> os ${pendingEvents.length} evento(s) abaixo aguardam validação pela GEDIV e <b>não foram homologados</b>. Os indicadores <i>Refeitos</i> e <i>Sem efeito</i> permanecem desabilitados até confirmação documental.</div>
 <div class="table-scroll"><table class="dialog-table is-cards-sm"><thead><tr><th class="nowrap">Data</th><th class="nowrap">Tipo</th><th>Extrato / Processo</th><th class="nowrap">Página</th><th class="nowrap">Situação</th><th class="nowrap">Fonte</th></tr></thead><tbody>${pendingEvents.length?pendingEvents.map(ev=>{
  const u=official(ev.url,ev.page);
  return `<tr><td class="nowrap" data-label="Data">${esc(dt(ev.date))}</td><td class="nowrap" data-label="Tipo"><span class="badge ${ev.type==='Tornado sem efeito'?'neg':'t'}">${esc(ev.type||'Pendente')}</span></td><td class="event-extract" data-label="Extrato"><div>${esc(sumTxt(ev.description))}</div><details><summary>Ver texto extraído</summary><div class="event-extract-pre">${esc(ev.description||'')}</div></details></td><td class="nowrap" data-label="Página">${esc(ev.page||'—')}</td><td class="nowrap" data-label="Situação"><span class="badge t">Pendente</span></td><td class="nowrap" data-label="Fonte">${u?`<a class="pdf-link" href="${esc(u)}" target="_blank" rel="noopener noreferrer">↗ PDF</a>`:'—'}</td></tr>`;
 }).join(''):'<tr><td colspan="6" class="empty-small">Nenhum evento pendente na base.</td></tr>'}</tbody></table></div>`;
 openDialog('Eventos em conferência documental',body,{wide:true});
}"""
    new_events_modal = """function openPendingEventsModal(){
 const pendingEvents=(data.events||[]).filter(e=>e.validation==='pendente'),isAuth=!!data.backend?.autenticado;
 const sumTxt=txt=>{
  const s=String(txt||'').replace(/\\s+/g,' ').trim();
  const resM=s.match(/RESENHA\\s+N[º°]?\\s*:?\\s*(\\d+\\/\\d+)/i),portM=s.match(/Portaria\\s+n[º°]\\s*(\\d+\\/\\d+(?:\\s*-\\s*[A-Z]+)?)/i),procM=s.match(/SAD-PSE-\\d{4}\\/\\d+/i);
  const parts=[];if(resM)parts.push('Resenha '+resM[1]);else if(portM)parts.push('Portaria '+portM[1]);if(procM)parts.push(procM[0]);
  return parts.length?parts.join(' · '):s.slice(0,80);
 };
 const body=`<div class="reconcile-note" style="margin-top:0;margin-bottom:12px"><b>Conferência documental pendente:</b> os ${pendingEvents.length} evento(s) abaixo aguardam validação pela GEDIV e <b>não foram homologados</b>. Os indicadores <i>Refeitos</i> e <i>Sem efeito</i> permanecem desabilitados até confirmação documental.</div>
 <div class="table-scroll"><table class="dialog-table is-cards-sm"><thead><tr><th class="nowrap">Data</th><th class="nowrap">Tipo</th><th>Extrato / Processo</th><th class="nowrap">Página</th><th class="nowrap">Situação</th><th class="nowrap">Fonte</th>${isAuth?'<th class="nowrap">Revisão</th>':''}</tr></thead><tbody>${pendingEvents.length?pendingEvents.map(ev=>{
  const u=official(ev.url,ev.page);
  return `<tr><td class="nowrap" data-label="Data">${esc(dt(ev.date))}</td><td class="nowrap" data-label="Tipo"><span class="badge ${ev.type==='Tornado sem efeito'?'neg':'t'}">${esc(ev.type||'Pendente')}</span></td><td class="event-extract" data-label="Extrato"><div>${esc(sumTxt(ev.description))}</div><details><summary>Ver texto extraído</summary><div class="event-extract-pre">${esc(ev.description||'')}</div></details></td><td class="nowrap" data-label="Página">${esc(ev.page||'—')}</td><td class="nowrap" data-label="Situação"><span class="badge t">Pendente</span></td><td class="nowrap" data-label="Fonte">${u?`<a class="pdf-link" href="${esc(u)}" target="_blank" rel="noopener noreferrer">↗ PDF</a>`:'—'}</td>${isAuth?`<td class="nowrap" data-label="Revisão"><button type="button" class="pdf-link" style="border:0;background:none;padding:0" data-review-event="${esc(ev.id)}">Vincular / Revisar →</button></td>`:''}</tr>`;
 }).join(''):`<tr><td colspan="${isAuth?7:6}" class="empty-small">Nenhum evento pendente na base.</td></tr>`}</tbody></table></div>`;
 openDialog('Eventos em conferência documental',body,{wide:true});
 $$('#dialogBody [data-review-event]').forEach(btn=>btn.addEventListener('click',()=>{const ev=pendingEvents.find(e=>e.id===btn.dataset.reviewEvent);if(ev){$('#dialog').close();openReviewModal('evento',[ev]);}}));
}"""
    assert old_events_modal in html
    html = html.replace(old_events_modal, new_events_modal, 1)

    # 8. Atualizar refreshData() para enviar cabeçalho de autenticação e implementar openReviewModal + fluxos de login/logout
    old_refresh = """async function refreshData(){
 if(isStaticHost()){toast('Publicação estática no GitHub Pages: os dados são atualizados por novo lote publicado.');return;}
 const button=$('#refreshData'),label=button.textContent,revision=data.dashboard?.revision;
 button.disabled=true;button.textContent='Sincronizando…';
 try{
  const response=await fetch('/api/data',{cache:'no-store',headers:{Accept:'application/json'},signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw new Error('HTTP '+response.status);
  const next=window.GEDIV_MODEL.acceptSnapshot(await response.json());
  enrichVerticalLevels(next.rows);
  Object.assign(data,next);S.page=0;S.selected='';render();
  $('#connectionState').textContent='Base recebida sincronizada · '+data.rows.length+' registros · '+data.dashboard.counts.pending+' em conferência · '+(revision===data.dashboard.revision?'sem alterações':'dados atualizados');
 }catch(error){$('#connectionState').textContent='Falha ao sincronizar. A base anterior de '+data.rows.length+' registros foi mantida. '+error.message;}
 finally{button.disabled=false;button.textContent=label;}
}"""
    new_refresh = """async function refreshData(){
 if(isStaticHost()){toast('Publicação estática no GitHub Pages: os dados são atualizados por novo lote publicado.');return;}
 const button=$('#refreshData'),label=button.textContent,revision=data.dashboard?.revision;
 button.disabled=true;button.textContent='Sincronizando…';
 try{
  const next=await window.GEDIV_FETCH_DATA();
  enrichVerticalLevels(next.rows);
  Object.assign(data,next);
  if(!['pendente','conferido','rejeitado'].includes(S.validation)||(!data.backend?.autenticado&&S.validation!=='conferido')){
   S.validation=data.dashboard?.defaultScope||'conferido';
  }
  S.page=0;S.selected='';render();
  $('#connectionState').textContent='Base sincronizada · '+data.rows.length+' registro(s) carregado(s) · '+(data.meta?.pendentes||0)+' em conferência · '+(revision===data.dashboard.revision?'sem alterações':'dados atualizados');
 }catch(error){$('#connectionState').textContent='Falha ao sincronizar. A base anterior de '+data.rows.length+' registros foi mantida. '+error.message;}
 finally{button.disabled=false;button.textContent=label;}
}
function openReviewModal(targetType,items){
 if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}
 const first=items[0];if(!first)return;
 $('#revTargetType').value=targetType;
 $('#revTargetId').value=items.map(x=>x.id).join(',');
 $('#revStatus').textContent='';$('#revStatus').classList.remove('is-error');
 const usr=window.GEDIV_AUTH.user();
 $('#revAuthor').value=usr?`${usr.nome} (${usr.usuario})`:($('#revAuthor').value||'Revisor GEDIV');
 $('#revJustification').value='';
 $('#revConfirmSource').checked=false;
 $('#revConfirmLink').checked=false;
 if(targetType==='evento'){
  $('#reviewDialogTitle').textContent='Vincular ou revisar evento modificador';
  $('#revContextBox').innerHTML=`<b>Evento:</b> ${esc(first.type)} em ${dt(first.date)} (pág. ${esc(first.page||'—')})<br>${esc((first.description||'').slice(0,220))}`;
  $('#revDecision').innerHTML='<option value="VINCULAR">VINCULAR a ato original</option><option value="REJEITAR">REJEITAR evento</option><option value="REABRIR">REABRIR evento</option>';
  $('#revEventBox').hidden=false;
  $('#revOriginalActId').value=first.act||first.suggestedAct||'';
  $('#revCorrectionsDetails').hidden=true;
  $('#revConfirmLinkRow').hidden=true;
 }else{
  $('#reviewDialogTitle').textContent=items.length>1?`Revisar ${items.length} decisões da seleção`:`Revisar decisão · ${first.process||first.id}`;
  $('#revContextBox').innerHTML=`<b>Resenha ${esc(first.resenha)}</b> (${dt(first.date)}, pág. ${esc(first.page||'—')}) · Vínculo GEDIV: <b>${esc(mentionLabel(first.sourceMention))}</b><br>${items.length===1?`Servidor: <b>${esc(first.server)}</b> · Processo: <b>${esc(first.process||'Não transcrito')}</b>`:`Lote selecionado com ${items.length} registros.`}`;
  $('#revDecision').innerHTML='<option value="CONFERIR">CONFERIR (homologar após consulta ao PDF)</option><option value="REJEITAR">REJEITAR (excluir dos indicadores)</option><option value="REABRIR">REABRIR (retornar para fila pendente)</option>';
  $('#revEventBox').hidden=true;
  $('#revCorrectionsDetails').hidden=items.length!==1;
  $('#revConfirmLinkRow').hidden=false;
  if(items.length===1){
   $('#revCorrProcess').value=first.process||'';
   $('#revCorrRegistration').value=first.registration||'';
   $('#revCorrServer').value=first.server||'';
   $('#revCorrResult').value='';
   $('#revCorrClassFrom').value=first.levelFrom||'';
   $('#revCorrClassTo').value=first.levelTo||'';
  }
 }
 $('#reviewDialog').showModal();
}"""
    assert old_refresh in html
    html = html.replace(old_refresh, new_refresh, 1)

    # 9. Vincular eventos de login/logout/revisão em bind()
    old_bind_start = """function bind(){
 function closeDownloadMenu(focusToggle){"""
    new_bind_start = """function bind(){
 function openLoginModal(){
  $('#loginStatus').textContent='';$('#loginStatus').classList.remove('is-error');$('#loginDialog').showModal();
 }
 function mountDelicateChrome(){
  const hdrRight=document.querySelector('.topbar .header-right');
  if(hdrRight&&!$('#delicateHdrControls')){
   const wrap=document.createElement('div');
   wrap.id='delicateHdrControls';wrap.className='delicate-hdr-controls';
   wrap.innerHTML=`
    <button type="button" id="delicateAcctBtn" class="delicate-glass-btn" aria-expanded="false" aria-haspopup="menu">
     <span id="delicateDot" class="delicate-dot is-pub"></span>
     <span id="delicateAcctLabel">Acesso gerencial</span>
     <span id="delicateRoleTag" class="delicate-role-tag">Público</span>
     <span aria-hidden="true">▾</span>
    </button>
    <div id="delicateAcctMenu" class="delicate-menu" role="menu" hidden>
     <div class="delicate-menu-hd"><b id="delicateMenuUser">Visitante (Público)</b><span id="delicateMenuMeta">Apenas indicadores agregados</span></div>
     <button type="button" role="menuitem" id="delicateLoginAct"><span>Entrar na Gerência GEDIV</span></button>
     <button type="button" role="menuitem" id="delicateRefreshAct"><span>↻ Atualizar dados</span></button>
     <button type="button" role="menuitem" id="delicateBatchAct" hidden><span>⚙ Administração → Coleta e importação</span></button>
     <button type="button" role="menuitem" id="delicateLogoutAct" class="is-danger" hidden><span>Encerrar sessão</span></button>
    </div>`;
   hdrRight.insertBefore(wrap,$('#about')||null);
   $('#delicateAcctBtn').addEventListener('click',()=>{
    if(!data.backend?.autenticado){openLoginModal();return;}
    const m=$('#delicateAcctMenu');m.hidden=!m.hidden;
    $('#delicateAcctBtn').setAttribute('aria-expanded',String(!m.hidden));
   });
   $('#delicateLoginAct').addEventListener('click',()=>{$('#delicateAcctMenu').hidden=true;openLoginModal();});
   $('#delicateRefreshAct').addEventListener('click',()=>{$('#delicateAcctMenu').hidden=true;refreshData();});
   $('#delicateBatchAct').addEventListener('click',()=>{$('#delicateAcctMenu').hidden=true;openAdminBatchDialog();});
   $('#delicateLogoutAct').addEventListener('click',()=>{$('#delicateAcctMenu').hidden=true;$('#logoutBtn')?.click();});
   document.addEventListener('click',e=>{if(!e.target.closest('#delicateHdrControls')){const m=$('#delicateAcctMenu');if(m){m.hidden=true;$('#delicateAcctBtn')?.setAttribute('aria-expanded','false');}}});
  }
  const dlBox=document.querySelector('.downloads');
  if(dlBox&&!$('#delicateScopeProxy')){
   const sel=document.createElement('select');
   sel.id='delicateScopeProxy';sel.className='delicate-scope-inline';sel.hidden=true;
   sel.setAttribute('aria-label','Escopo de conferência');
   dlBox.insertBefore(sel,$('#downloadToggle')||null);
   sel.addEventListener('change',()=>{const orig=$('#validationScope');if(orig){orig.value=sel.value;orig.dispatchEvent(new Event('change',{bubbles:true}));}});
  }
 }
 mountDelicateChrome();
 $('#authToggleBtn')?.addEventListener('click',openLoginModal);
 $('#closeLoginTop')?.addEventListener('click',()=>$('#loginDialog').close());
 $('#closeLoginBtn')?.addEventListener('click',()=>$('#loginDialog').close());
 $('#loginForm')?.addEventListener('submit',async e=>{
  e.preventDefault();
  const st=$('#loginStatus'),btn=$('#submitLoginBtn');
  st.classList.remove('is-error');st.textContent='Autenticando…';btn.disabled=true;
  try{
   const manualTok=$('#loginTokenInput').value.trim();
   if(manualTok){
    window.GEDIV_AUTH.set(manualTok,{usuario:'token',nome:'Credencial técnica',papel:'admin'});
   }else{
    const usuario=$('#loginUser').value.trim(),senha=$('#loginPass').value;
    if(!usuario||!senha)throw new Error('Informe usuário e senha ou cole o token técnico.');
    const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usuario,senha})});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(d.erro||'Credenciais inválidas.');
    window.GEDIV_AUTH.set(d.token,{usuario:d.usuario,nome:d.nome,papel:d.papel||'gerencia'});
   }
   await refreshData();
   if(!data.backend?.autenticado){window.GEDIV_AUTH.set('','');throw new Error('Credencial não autorizada pelo servidor.');}
   S.validation='pendente';S.page=0;S.selected='';initHistory();renderMeta();render();
   $('#loginPass').value='';$('#loginTokenInput').value='';
   $('#loginDialog').close();
   toast(data.backend?.ehAdmin?'Sessão administrativa autenticada.':'Sessão gerencial autenticada.');
  }catch(err){st.textContent=err.message;st.classList.add('is-error');}
  finally{btn.disabled=false;}
 });
 $('#logoutBtn')?.addEventListener('click',async()=>{
  try{await fetch('/api/logout',{method:'POST',headers:window.GEDIV_AUTH.headers()});}catch{}
  window.GEDIV_AUTH.set('','');
  await refreshData();
  S.validation='conferido';S.page=0;S.selected='';initHistory();renderMeta();render();
  toast('Sessão encerrada.');
 });
 $('#closeReviewTop')?.addEventListener('click',()=>$('#reviewDialog').close());
 $('#closeReviewBtn')?.addEventListener('click',()=>$('#reviewDialog').close());
 $('#closeDocModal')?.addEventListener('click',()=>$('#docModal').close());
 $('#docModal')?.addEventListener('click',e=>{if(e.target===$('#docModal'))$('#docModal').close();});
 $('#reviewForm')?.addEventListener('submit',async e=>{
  e.preventDefault();
  const st=$('#revStatus'),btn=$('#submitReviewBtn');
  st.classList.remove('is-error');st.textContent='Registrando decisão…';btn.disabled=true;
  try{
   const alvo=$('#revTargetType').value,rawIds=$('#revTargetId').value.split(',').filter(Boolean);
   const payload={
    alvo,
    decisao:$('#revDecision').value,
    responsavel:$('#revAuthor').value.trim(),
    justificativa:$('#revJustification').value.trim(),
    confirma_fonte:$('#revConfirmSource').checked,
    confirma_vinculo:$('#revConfirmLink').checked
   };
   if(alvo==='evento'){
    payload.id=rawIds[0];
    payload.ato_original_id=$('#revOriginalActId').value.trim()||null;
   }else{
    payload.ids=rawIds;
    if(rawIds.length===1&&!$('#revCorrectionsDetails').hidden){
     const corr={};
     if($('#revCorrProcess').value.trim())corr.processo=$('#revCorrProcess').value.trim();
     if($('#revCorrRegistration').value.trim())corr.matricula=$('#revCorrRegistration').value.trim();
     if($('#revCorrServer').value.trim())corr.servidor=$('#revCorrServer').value.trim();
     if($('#revCorrResult').value)corr.resultado=$('#revCorrResult').value;
     if($('#revCorrClassFrom').value.trim())corr.classe_anterior=$('#revCorrClassFrom').value.trim().toUpperCase();
     if($('#revCorrClassTo').value.trim())corr.classe_posterior=$('#revCorrClassTo').value.trim().toUpperCase();
     if(Object.keys(corr).length)payload.correcoes=corr;
    }
   }
   const r=await fetch('/api/revisao',{method:'POST',headers:window.GEDIV_AUTH.headers({'Content-Type':'application/json'}),body:JSON.stringify(payload)});
   const d=await r.json().catch(()=>({}));
   if(!r.ok)throw new Error(d.erro||'Não foi possível registrar a revisão.');
   await refreshData();
   $('#reviewDialog').close();
   toast('Decisão de revisão registrada na trilha de auditoria.');
  }catch(err){st.textContent=err.message;st.classList.add('is-error');}
  finally{btn.disabled=false;}
 });
 function closeDownloadMenu(focusToggle){"""
    assert old_bind_start in html
    html = html.replace(old_bind_start, new_bind_start, 1)

    # 10. Atualizar renderMeta() para exibir o estado de autenticação, RBAC, banner em 1 linha e escopo de exportação
    old_render_meta = """ const meta=data.meta||{}, pending=data.rows.filter(r=>r.validation==='pendente').length, rej=meta.rejeitados||0;
 const batches=meta.connection?.batches||0;
 if(isStaticHost()){
  $('#connectionState').textContent=`Painel publicado · ${batches} lote(s) · ${pending} em conferência`;
  $('#staticBadge').hidden=false;$('#refreshData').hidden=true;$('#receiveBatch').hidden=true;
 }
 $('#receivedTotal').textContent=data.rows.length+' registros recebidos';
 $('#receivedMetaPill').textContent=`${pending} em conferência${rej?' · '+rej+(rej===1?' rejeitado':' rejeitados'):''}`;
 $('#receivedValidation').textContent=pending+' em conferência · '+(meta.conferidos||0)+' conferidos · '+rej+' rejeitados';
 $('#validationScope').innerHTML='<option value="pendente">Em conferência ('+pending+')</option><option value="conferido">Conferidos ('+(meta.conferidos||0)+')</option>';"""

    new_render_meta = """ const meta=data.meta||{}, isAuth=!!data.backend?.autenticado, isAdm=!!data.backend?.ehAdmin, pending=isAuth?data.rows.filter(r=>r.validation==='pendente').length:(meta.pendentes||0), confCnt=isAuth?data.rows.filter(r=>r.validation==='conferido').length:(meta.conferidos||0), rej=isAuth?data.rows.filter(r=>r.validation==='rejeitado').length:(meta.rejeitados||0);
 const batches=meta.connection?.batches||0, usr=window.GEDIV_AUTH.user();
 if(isStaticHost()){
  $('#connectionState').textContent=`Painel publicado · ${batches} lote(s) · ${pending} em conferência`;
  $('#staticBadge').hidden=false;$('#refreshData').hidden=true;$('#receiveBatch').hidden=true;
 }else{
  $('#connectionState').textContent=`Conectado · ${batches} edição(ões) · ${pending} pendentes · ${confCnt} conferidos`;
 }
 const authBadge=$('#authBadge'),authBtn=$('#authToggleBtn'),logoutBtn=$('#logoutBtn');
 if(authBadge){
  authBadge.textContent=isAuth?(usr?`${isAdm?'Admin':'Gerência'}: ${usr.nome} (${usr.usuario})`:'Gerência autenticada'):'Consulta pública (dados individuais protegidos)';
  authBadge.classList.toggle('is-public',!isAuth);
 }
 if(authBtn)authBtn.hidden=isAuth;
 if(logoutBtn)logoutBtn.hidden=!isAuth;
 const dDot=$('#delicateDot'),dLbl=$('#delicateAcctLabel'),dTag=$('#delicateRoleTag');
 if(dDot)dDot.classList.toggle('is-pub',!isAuth);
 if(dLbl)dLbl.textContent=isAuth?(usr?.nome||(isAdm?'Admin GEDIV':'Gerência GEDIV')):'Acesso gerencial';
 if(dTag)dTag.textContent=isAuth?(isAdm?'Admin':'Gerência'):'Público';
 const mu=$('#delicateMenuUser'),mm=$('#delicateMenuMeta'),la=$('#delicateLoginAct'),lo=$('#delicateLogoutAct'),ba=$('#delicateBatchAct');
 if(mu)mu.textContent=isAuth?(usr?`${usr.nome} (${usr.usuario})`:'Sessão autenticada'):'Visitante (Público)';
 if(mm)mm.textContent=isAuth?`${Number(meta.edicoes)||0} edições · perfil ${isAdm?'Administração':'Gerência'}`:'Apenas indicadores agregados';
 if(la)la.hidden=isAuth;if(lo)lo.hidden=!isAuth;if(ba)ba.hidden=!isAdm;
 const totalBase=isAuth?data.rows.length:(pending+confCnt+rej);
 $('#receivedTotal').textContent=totalBase+' registros na base';
 $('#receivedMetaPill').textContent=`${pending} em conferência${rej?' · '+rej+(rej===1?' rejeitado':' rejeitados'):''}`;
 $('#receivedValidation').textContent=pending+' em conferência · '+confCnt+' conferidos · '+rej+' rejeitados';
 $('#validationScope').innerHTML=`<option value="pendente">Em conferência (${pending})</option><option value="conferido">Conferidos (${confCnt})</option>${isAuth?`<option value="rejeitado">Rejeitados (${rej})</option>`:''}`;
 $('#validationScope').value=S.validation;
 const proxyScope=$('#delicateScopeProxy');
 if(proxyScope){proxyScope.hidden=!isAuth;if(isAuth){proxyScope.innerHTML=$('#validationScope').innerHTML;proxyScope.value=S.validation;}}
 const expHead=$('#exportScopeHead');
 if(expHead){const mRec=typeof model==='function'?model():{original:[]};expHead.textContent=isAuth?`Recorte: ${views[S.view]?.[1]||'Visão'} · ${mRec.original.length} registro(s)`:'Modo público: apenas indicadores agregados';}
 const bt=$('#bannerTitle'),bx=$('#bannerText'),edC=Number(meta.edicoes)||0,scopeLbl=S.validation==='pendente'?'conferência pendente':S.validation==='rejeitado'?'registros rejeitados':'conferência registrada';
 if(bt)bt.textContent=edC?`Cobertura parcial (${edC} ${edC===1?'edição':'edições'}) · ${scopeLbl}`:'Cobertura em atualização';
 if(bx)bx.textContent=isAuth?'Registros extraídos sujeitos a conferência documental.':'Dados públicos agregados (sujeitos a conferência); registros individuais protegidos.';"""
    assert old_render_meta in html
    html = html.replace(old_render_meta, new_render_meta, 1)

    # 10b. Manter texto curto do banner após a sobrescrita padrão do bannerText ao final de renderMeta(), diferenciar escopo 'rejeitado' e atualizar escopo de exportação em render()
    old_banner_end = """ $('#bannerTitle').textContent=S.validation==='pendente'?'Dados extraídos · conferência pendente':'Decisões com conferência registrada';
 $('#bannerText').textContent=meta.verifiedAt?`${meta.coverage} ${meta.automation} ${meta.personal}`:'Esta cópia contém apenas o layout. Nenhuma publicação foi carregada; a coleta diária não está conectada.';"""
    new_banner_end = """ if(!meta.verifiedAt)$('#bannerText').textContent='Nenhuma edição carregada nesta cópia; consulte a cobertura.';"""
    assert old_banner_end in html
    html = html.replace(old_banner_end, new_banner_end, 1)
    for old_txt, new_txt in (
        (
            "S.validation==='pendente'?'EM CONFERÊNCIA · DADOS PRELIMINARES':'DECISÕES CONFERIDAS'",
            "S.validation==='pendente'?'EM CONFERÊNCIA · DADOS PRELIMINARES':S.validation==='rejeitado'?'REGISTROS REJEITADOS':'DECISÕES CONFERIDAS'",
        ),
        (
            "'PRÉVIA: os resultados extraídos abaixo aguardam conferência documental. Nenhum registro foi homologado por esta visualização.':'Esta visão usa somente decisões com conferência registrada.'",
            "'PRÉVIA: os resultados extraídos abaixo aguardam conferência documental. Nenhum registro foi homologado por esta visualização.':S.validation==='rejeitado'?'Esta visão exibe registros marcados como rejeitados na conferência documental.':'Esta visão usa somente decisões com conferência registrada.'",
        ),
        (
            "'Prévia dos registros extraídos':'Decisões conferidas'",
            "'Prévia dos registros extraídos':S.validation==='rejeitado'?'Registros rejeitados':'Decisões conferidas'",
        ),
    ):
        assert old_txt in html, f"Trecho esperado não encontrado: {old_txt}"
        html = html.replace(old_txt, new_txt, 1)
    html = html.replace(
        "$('#validationScope').value=S.validation;",
        "$('#validationScope').value=S.validation;if($('#delicateScopeProxy'))$('#delicateScopeProxy').value=S.validation;if($('#exportScopeHead')){const isA=!!data.backend?.autenticado;const mE=model();$('#exportScopeHead').textContent=isA?`Recorte: ${views[S.view]?.[1]||'Visão'} · ${mE.original.length} registro(s)`:'Modo público: apenas indicadores agregados';}",
        1,
    )

    # Verificar que nenhuma cor nova foi introduzida e que nenhum dado pessoal permaneceu no HTML
    new_colors = {c.lower() for c in hex_pattern.findall(html)}
    added_colors = new_colors - orig_colors
    assert not added_colors, f"Cores novas detectadas: {added_colors}"
    assert 'window.GEDIV_BOOTSTRAP={"rows":[],"events":[' in html, "Esqueleto público vazio ausente!"
    assert not re.search(r"SAD-PSE-202\d/\d+", html), "Processo residual encontrado no HTML!"
    assert not re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", html), "CPF residual encontrado no HTML!"
    assert not re.search(r'"server"\s*:\s*"[A-ZÀ-Ú]{3,}', html), "Nome pessoal residual encontrado no HTML!"

    dest_unificado.parent.mkdir(parents=True, exist_ok=True)
    dest_unificado.write_text(html, encoding="utf-8")
    dest_paleta.write_text(
        json.dumps({"total": len(orig_colors), "cores_hex": sorted(orig_colors)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Salvo ({len(html):,} bytes): {dest_unificado}")
    print(f"Paleta salva ({len(orig_colors)} cores HEX): {dest_paleta}")
    print(f"Verificação de paleta: {len(new_colors)} cores HEX (0 cores novas).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstrói o painel unificado GEDIV sem dados embutidos.")
    parser.add_argument(
        "--origem",
        type=pathlib.Path,
        default=None,
        help="Caminho para o HTML base homologado (ou use GEDIV_ORIGEM_HTML).",
    )
    args = parser.parse_args(argv)
    construir(args.origem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
