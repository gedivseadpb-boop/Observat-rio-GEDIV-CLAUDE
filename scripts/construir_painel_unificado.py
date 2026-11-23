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
MODELO_BASE_PADRAO = REPO_DIR / "observatorio" / "web" / "unificado" / "modelo-base-sanitizado.html"


def construir(
    origem_html: pathlib.Path | None = None,
    destino_html: pathlib.Path | None = None,
) -> pathlib.Path:
    env_origem = os.environ.get("GEDIV_ORIGEM_HTML")
    src_path = origem_html or (pathlib.Path(env_origem) if env_origem else MODELO_BASE_PADRAO)
    if src_path is None or not src_path.is_file():
        raise FileNotFoundError(
            "Modelo base não encontrado. Informe --origem <arquivo.html> ou utilize "
            "observatorio/web/unificado/modelo-base-sanitizado.html."
        )

    dest_unificado = destino_html or (REPO_DIR / "observatorio" / "web" / "unificado" / "index.html")
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

    esqueleto_publico = """window.GEDIV_BOOTSTRAP={"rows":[],"events":[],"otherPublications":[],"otherPublicationsSummary":{"total":0,"abonoPermanencia":0,"porTipo":{}},"categories":[["TS-01","Anotação de Tempo de Serviço/Contribuição"],["TS-02","Desaverbação de Tempo de Serviço"],["TS-03","Licença para Tratar de Interesses Particulares"],["TS-04","Desistência de Licença de Interesse Particular"],["TS-05","Licença Especial"],["TS-06","Conversão de Licença Especial em Tempo de Serviço"],["TS-07","Conversão de Férias"],["ABONO_PERMANENCIA","Abono de Permanência"]],"groups":[],"urls":{},"meta":{"version":"Painel Diário Oficial | GEDIV · Regras 0.4","dictionary":"Catálogo controlado GEDIV (AST e SFT normalizados em registros compatíveis; ambíguos separados)","verifiedAt":"","coverage":"Conectando ao servidor do Observatório DOE · GEDIV...","incompatibilidadeVersaoRegras":false,"versaoRegrasDiagnostico":{},"automation":"Motor Python/SQLite v9 conectado · Revisão auditada por servidor.","personal":"Sessão pública: dados individuais e anotações internas protegidos (faça login gerencial para conferir).","semBaseCarregada":true,"edicoes":0,"edicoesPendentes":0,"conferidos":0,"pendentes":0,"rejeitados":0,"outrasPublicacoes":0,"eventosPendentes":0,"semDecisoesConferidas":true,"connection":{"batches":0,"source":"sqlite_v9_canonico","overlaps":0,"partialCoverage":true,"fullPeriodComplete":false}},"dashboard":{"schemaVersion":1,"revision":"0000000000000000000000000000000000000000000000000000000000000000","defaultScope":"conferido","counts":{"received":0,"pending":0,"confirmed":0,"rejected":0,"otherPublications":0,"unlinkedEvents":0},"views":{"pendente":{"rowIds":[],"metrics":{"processes":0,"processesDeferidos":0,"processesIndeferidos":0,"processesMistos":0,"processesNaoInformado":0,"resenhas":0,"decisions":0,"deferidos":0,"indeferidos":0,"naoInformado":0,"servers":0,"benefitedServers":0,"refeitos":null,"semEfeito":null,"republicacoes":null,"retificacoes":null,"correcoes":null,"decisoesSemEfeito":null,"otherPublications":0},"series":{"vertical":0,"horizontal":0,"progressaoSemModalidade":0,"tempo":0,"other":0}},"conferido":{"rowIds":[],"metrics":{"processes":0,"processesDeferidos":0,"processesIndeferidos":0,"processesMistos":0,"processesNaoInformado":0,"resenhas":0,"decisions":0,"deferidos":0,"indeferidos":0,"naoInformado":0,"servers":0,"benefitedServers":0,"refeitos":0,"semEfeito":0,"republicacoes":0,"retificacoes":0,"correcoes":0,"decisoesSemEfeito":0,"otherPublications":0},"series":{"vertical":0,"horizontal":0,"progressaoSemModalidade":0,"tempo":0,"other":0}}}}};"""

    novo_model = """window.GEDIV_MODEL={dashboardModel:function t(e,t={}){let n=t.validation||e.dashboard?.defaultScope||`pendente`;if(![`pendente`,`conferido`,`rejeitado`].includes(n))throw Error(`Situação de conferência inválida.`);let r=e=>String(e??``).normalize(`NFD`).replace(/[\\u0300-\\u036f]/g,``).toLowerCase(),i=e=>(!t.from||e>=t.from)&&(!t.to||e<=t.to),a=(e,t)=>new Set(e.map(e=>e[t]).filter(Boolean)).size,o=new Map(e.categories||[]),nm=v=>{let d=String(v??``).replace(/\\D/g,``);return d.length>=6&&d.length<=9&&new Set(d).size>1?d:``},np=row=>{let raw=String(row.process??``).normalize(`NFD`).replace(/[\\u0300-\\u036f]/g,``).toUpperCase().replace(/\\s+/g,``);if(!raw)return ``;if(/^[A-Z]{2,6}-(?:PSE|PRC|OFI)-\\d{4}[/-]\\d{3,9}$/.test(raw))return raw;let org=String(row.lotacao||row.orgao||``).normalize(`NFD`).replace(/[\\u0300-\\u036f]/g,``).toUpperCase().replace(/[^0-9A-Z]/g,``),ser=String(row.actType||``).normalize(`NFD`).replace(/[\\u0300-\\u036f]/g,``).toUpperCase().replace(/[^0-9A-Z]/g,``);return org||ser?`${org}|${ser}|${raw}`:raw},ehOutras=t.view===`outras`||t.axis===`outros`,baseArr=ehOutras?(e.otherPublications||[]):(e.rows||[]),s=e=>!(t.axis&&!ehOutras&&e.axis!==t.axis||t.modality&&(e.axis!==`progressao`||e.modality!==t.modality)||t.group&&(e.axis!==`progressao`||(t.group===`NAO_INFORMADO`?e.group:e.group!==t.group))||t.category?.length&&(!ehOutras&&e.axis!==`tempo`||!t.category.includes(e.category||`SEM_SUBCATEGORIA`))||t.merit&&e.merit!==t.merit||t.query&&!r([e.resenha,e.process,e.server,e.registration,e.group,e.groupExpression,t.groupNames?.[e.group],e.modality,o.get(e.category)||(!e.category&&e.axis===`tempo`?`Subcategoria pendente`:``)].join(` `)).includes(r(t.query))),c=ehOutras?baseArr.filter(s):baseArr.filter(e=>e.validation===n&&s(e)),l=c.filter(e=>i(e.date)),u=new Set(c.map(e=>e.act).filter(Boolean)),d=n===`conferido`&&!ehOutras?e.events.filter(e=>e.validation===`conferido`&&e.act&&u.has(e.act)&&i(e.date)):[],f=d.filter(e=>[`Retificação`,`Correção`,`Republicação`].includes(e.type)),p=d.filter(e=>e.type===`Tornado sem efeito`),fRep=d.filter(e=>e.type===`Republicação`),fRet=d.filter(e=>e.type===`Retificação`),fCor=d.filter(e=>e.type===`Correção`),decSeSet=new Set(p.flatMap(e=>Array.isArray(e.decisoesVinculadas)?e.decisoesVinculadas:[])),pMap=new Map(),sMap=new Map();for(let row of l){let pk=np(row),mk=nm(row.registration),mer=row.merit===`deferido`?`D`:row.merit===`indeferido`?`I`:`N`;if(pk){if(!pMap.has(pk))pMap.set(pk,new Set());pMap.get(pk).add(mer)}if(mk){if(!sMap.has(mk))sMap.set(mk,new Set());sMap.get(mk).add(mer)}}let pDef=0,pInd=0,pMis=0,pNi=0;for(let st of pMap.values()){if(st.size>1)pMis++;else if(st.has(`D`))pDef++;else if(st.has(`I`))pInd++;else pNi++}let sBen=0,sSoInd=0,sSoNi=0;for(let st of sMap.values()){if(st.has(`D`))sBen++;else if(st.has(`I`))sSoInd++;else sSoNi++}let defCnt=l.filter(e=>e.merit===`deferido`).length,indCnt=l.filter(e=>e.merit===`indeferido`).length,niCnt=l.length-defCnt-indCnt,m={processes:pMap.size,processesDeferidos:pDef,processesIndeferidos:pInd,processesMistos:pMis,processesNaoInformado:pNi,resenhas:a(l,`resenha_id`),decisions:l.length,deferidos:defCnt,indeferidos:indCnt,naoInformado:niCnt,servers:sMap.size,benefitedServers:sBen,serversOnlyIndeferido:sSoInd,serversOnlyNaoInformado:sSoNi,refeitos:n===`conferido`&&!ehOutras?new Set(f.map(e=>e.act)).size:null,semEfeito:n===`conferido`&&!ehOutras?new Set(p.map(e=>e.act)).size:null,republicacoes:n===`conferido`&&!ehOutras?new Set(fRep.map(e=>e.act)).size:null,retificacoes:n===`conferido`&&!ehOutras?new Set(fRet.map(e=>e.act)).size:null,correcoes:n===`conferido`&&!ehOutras?new Set(fCor.map(e=>e.act)).size:null,decisoesSemEfeito:n===`conferido`&&!ehOutras?decSeSet.size:null,otherPublications:(e.otherPublications||[]).length},h=l;if(t.card===`deferidos`||t.card===`indeferidos`)h=l.filter(e=>e.merit===(t.card===`deferidos`?`deferido`:`indeferido`));else if(t.card===`processes`)h=l.filter(e=>!!e.process);else if(t.card===`refeitos`||t.card===`semEfeito`){let e=new Set((t.card===`refeitos`?f:p).map(e=>e.act));h=c.filter(t=>t.act&&e.has(t.act))}let g={vertical:h.filter(e=>e.axis===`progressao`&&e.modality===`Vertical`).length,horizontal:h.filter(e=>e.axis===`progressao`&&e.modality===`Horizontal`).length,progressaoSemModalidade:h.filter(e=>e.axis===`progressao`&&![`Vertical`,`Horizontal`].includes(e.modality)).length,tempo:h.filter(e=>e.axis===`tempo`).length,other:h.filter(e=>![`tempo`,`progressao`].includes(e.axis)).length},_=[...new Set(h.map(e=>e.date))].sort().map(e=>({date:e,records:h.filter(t=>t.date===e).length})),v=[...new Set(h.filter(e=>e.axis===`progressao`).map(e=>e.group||`NAO_INFORMADO`))].map(e=>({group:e,records:h.filter(t=>t.axis===`progressao`&&(t.group||`NAO_INFORMADO`)===e).length}));return{scope:n,preliminary:n!==`conferido`,label:n===`pendente`?`Em conferência · dados preliminares`:n===`rejeitado`?`Registros rejeitados`:`Decisões conferidas`,rows:h,original:l,metrics:m,redo:f,voided:p,series:g,timeline:_,groupSeries:v}},acceptSnapshot:function n(e){let t=e?.dashboard;if(!Array.isArray(e?.rows)||!Array.isArray(e?.events)||!Array.isArray(e?.categories)||!e?.meta?.connection||t?.schemaVersion!==1||!/^[0-9a-f]{64}$/.test(t.revision)||![`pendente`,`conferido`,`rejeitado`].includes(t.defaultScope))throw Error(`Resposta do backend incompatível; a base anterior foi mantida.`);let n=t.counts;if(!n||n.received!==e.rows.length||n.pending+n.confirmed+n.rejected!==n.received)throw Error(`Contagem do backend inconsistente; a base anterior foi mantida.`);for(let n of[`pendente`,`conferido`]){let r=e.rows.filter(e=>e.validation===n),i=t.views?.[n],a=new Set(r.map(e=>e.id));if(!i||!Array.isArray(i.rowIds)||i.rowIds.length!==r.length||new Set(i.rowIds).size!==r.length||i.rowIds.some(e=>!a.has(e))||i.metrics?.decisions!==r.length||!i.series||Object.values(i.series).reduce((e,t)=>e+t,0)!==r.length)throw Error(`Registros e gráficos do backend divergem; a base anterior foi mantida.`)}return e}};"""

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

    # 2b. Suporte a Tempo de Serviço (TS-01 a TS-07 + Subcategoria pendente) e Abono de Permanência em Outras Publicações (sem TS-08, 0 cores novas)
    html = html.replace(
        "<p>Os sete serviços permanecem visíveis · clique para filtrar</p>",
        "<p>Os sete serviços (TS-01 a TS-07) permanecem visíveis · Abono de Permanência em Outras Publicações</p>",
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
.date-actions{display:flex;gap:4px;margin-top:6px}
.date-act-btn{flex:1;height:28px;border:1px solid #cdddeb;background:#fff;color:#27527c;border-radius:5px;font-size:10.5px;font-weight:700;padding:0 6px}
.date-act-btn:hover:not(:disabled){background:#edf5ff;border-color:#9bc2f7}
.date-act-btn.is-primary{background:#1265ef;border-color:#1265ef;color:#fff}
.date-act-btn.is-primary:hover:not(:disabled){background:#0a4d96;border-color:#0a4d96}
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
<dialog id="loginDialog" aria-labelledby="loginDialogTitle"><div class="dialog-head"><div><span class="eyebrow">ACESSO RESTRITO · GEDIV / SEAD-PB</span><h2 id="loginDialogTitle">Autenticação da gerência</h2></div><button type="button" id="closeLoginTop" class="icon-btn" aria-label="Fechar janela">×</button></div><form id="loginForm" class="dialog-body review-form" method="dialog"><p style="margin:0;font-size:11px;color:#405d79">O acesso aos nomes, matrículas, processos, anotações preliminares, PDFs do acervo e ações de revisão documental é exclusivo para contas autorizadas da gerência (sessão via cookie <code>HttpOnly</code>).</p><div class="review-grid"><label>Usuário da conta<input type="text" id="loginUser" autocomplete="username" placeholder="Ex.: revisor.gediv"></label><label>Senha<input type="password" id="loginPass" autocomplete="current-password" placeholder="Senha da conta"></label></div><details><summary style="cursor:pointer;font-weight:600;color:#175ca8;font-size:11px">Usar credencial técnica legada (somente memória · sem privilégio admin)</summary><label style="margin-top:8px">Token técnico de sessão / gerência<input type="password" id="loginTokenInput" autocomplete="off" placeholder="Cole o token técnico da gerência"></label></details><p id="loginStatus" class="review-status" role="status"></p><div class="dialog-footer" style="padding:12px 0 0"><button type="button" id="closeLoginBtn" class="btn-secondary">Cancelar</button><button type="submit" id="submitLoginBtn">Entrar e carregar dados</button></div></form></dialog>
<dialog id="reviewDialog" aria-labelledby="reviewDialogTitle"><div class="dialog-head"><div><span class="eyebrow">REVISÃO DOCUMENTAL AUDITADA</span><h2 id="reviewDialogTitle">Conferir ou revisar registro</h2></div><button type="button" id="closeReviewTop" class="icon-btn" aria-label="Fechar janela">×</button></div><form id="reviewForm" class="dialog-body review-form" method="dialog"><input type="hidden" id="revTargetType" value="decisao"><input type="hidden" id="revTargetId" value=""><div id="revContextBox" class="reconcile-note" style="margin:0"></div><div class="review-grid"><label>Decisão de revisão<select id="revDecision"><option value="CONFERIR">CONFERIR (homologar após leitura do PDF)</option><option value="REJEITAR">REJEITAR (excluir dos indicadores)</option><option value="REABRIR">REABRIR (retornar para fila pendente)</option></select></label><label>Responsável pela revisão<input type="text" id="revAuthor" placeholder="Nome do revisor (automático em conta nominal)"></label></div><div id="revEventBox" hidden><label>ID do ato original a vincular (20 caracteres hexadecimais)<input type="text" id="revOriginalActId" placeholder="Obrigatório para VINCULAR evento modificador"></label></div><div id="revActClassBox" hidden><div class="review-grid" style="margin-top:4px"><label>Eixo temático<select id="revActEixo"><option value="PROGRESSAO">PROGRESSAO · Progressão Funcional</option><option value="TEMPO_SERVICO">TEMPO_SERVICO · Tempo de Serviço</option></select></label><label>Modalidade (Progressão)<select id="revActModalidade"><option value="">Não aplicável / Manter</option><option value="VERTICAL">VERTICAL</option><option value="HORIZONTAL">HORIZONTAL</option></select></label><label>Grupo PCCR (Progressão)<input type="text" id="revActGrupo" placeholder="Ex.: MAG, GAJ, ANS, SSA, AST..."></label><label>Assunto (Tempo de Serviço)<select id="revActSubcat"><option value="">Não aplicável / Manter</option><option value="TS-01">TS-01 · Anotação</option><option value="TS-02">TS-02 · Desaverbação</option><option value="TS-03">TS-03 · Licença Interesse Particular</option><option value="TS-04">TS-04 · Desistência de Licença</option><option value="TS-05">TS-05 · Licença Especial</option><option value="TS-06">TS-06 · Conversão Licença Especial</option><option value="TS-07">TS-07 · Conversão de Férias</option></select></label></div></div><details id="revCorrectionsDetails"><summary style="cursor:pointer;font-weight:700;color:#175ca8;font-size:11px">Corrigir campos extraídos (preserva valor original na trilha de auditoria)</summary><div class="review-grid" style="margin-top:8px"><label>Processo<input type="text" id="revCorrProcess"></label><label>Matrícula<input type="text" id="revCorrRegistration"></label><label>Servidor<input type="text" id="revCorrServer"></label><label>Cargo<input type="text" id="revCorrCargo"></label><label>Lotação / Órgão<input type="text" id="revCorrLotacao"></label><label>Resultado<select id="revCorrResult"><option value="">Manter atual</option><option value="DEFERIDO">DEFERIDO</option><option value="INDEFERIDO">INDEFERIDO</option><option value="NAO_INFORMADO">NAO_INFORMADO</option></select></label><label>Classe origem (A–F)<input type="text" id="revCorrClassFrom" maxlength="1" placeholder="A..F"></label><label>Classe destino (A–F)<input type="text" id="revCorrClassTo" maxlength="1" placeholder="A..F"></label></div></details><label class="check-row"><input type="checkbox" id="revConfirmSource"><span>Declaro que consultei o PDF oficial do Diário Oficial na página indicada (<code>confirma_fonte</code>).</span></label><label class="check-row" id="revConfirmLinkRow"><input type="checkbox" id="revConfirmLink"><span>Confirmo o vínculo institucional deste ato com a GEDIV/SEAD-PB, mesmo quando a sigla não consta expressamente no cabeçalho (<code>confirma_vinculo</code>).</span></label><label>Justificativa técnica (obrigatória · mínimo 5 caracteres)<textarea id="revJustification" placeholder="Descreva a verificação realizada no PDF oficial do DOE..."></textarea></label><p id="revStatus" class="review-status" role="status"></p><div class="dialog-footer" style="padding:12px 0 0"><button type="button" id="closeReviewBtn" class="btn-secondary">Cancelar</button><button type="submit" id="submitReviewBtn">Registrar decisão auditada</button></div></form></dialog>
<dialog id="conflictsDialog" class="dialog-wide" aria-labelledby="conflictsDialogTitle"><div class="dialog-head"><div><span class="eyebrow">RECONCILIAÇÃO E INTEGRIDADE · D2</span><h2 id="conflictsDialogTitle">Conflitos de leitura e vínculos órfãos</h2></div><button type="button" id="closeConflictsTop" class="icon-btn" aria-label="Fechar janela">×</button></div><div class="dialog-body review-form"><div id="conflictsSummaryBox" class="reconcile-note" style="margin:0">Carregando diagnóstico de conflitos…</div><div class="review-grid"><label>Justificativa para resolução de conflito (mín. 5 caracteres)<input type="text" id="conflictJustificationInput" placeholder="Ex.: Conferido no PDF oficial da edição"></label><label class="check-row" style="align-self:end"><input type="checkbox" id="conflictConfirmSourceInput"><span>Confirmo leitura do PDF oficial (<code>confirma_fonte</code>)</span></label></div><p id="conflictsStatus" class="review-status" role="status"></p><div id="conflictsTableWrap" class="table-scroll"></div><div class="dialog-footer" style="padding:12px 0 0"><button type="button" id="refreshConflictsBtn" class="btn-secondary">↻ Atualizar lista</button><button type="button" id="closeConflictsBtn">Fechar</button></div></div></dialog>
<dialog id="auditDialog" class="dialog-wide" aria-labelledby="auditDialogTitle"><div class="dialog-head"><div><span class="eyebrow">GOVERNANÇA E RASTREABILIDADE · D3</span><h2 id="auditDialogTitle">Trilha de auditoria e histórico</h2></div><button type="button" id="closeAuditTop" class="icon-btn" aria-label="Fechar janela">×</button></div><div class="dialog-body review-form"><div id="auditScopeNote" class="reconcile-note" style="margin:0">Consultando trilha de auditoria…</div><div id="auditAdminActions" hidden><button type="button" id="publishPublicSnapshotBtn" class="btn-secondary">Publicar snapshot público controlado</button><span id="publishSnapshotStatus" style="margin-left:8px;font-size:11px;color:#175a4e;font-weight:600"></span></div><div id="auditTableWrap" class="table-scroll"></div><div class="dialog-footer" style="padding:12px 0 0"><button type="button" id="refreshAuditBtn" class="btn-secondary">↻ Atualizar trilha</button><button type="button" id="closeAuditBtn">Fechar</button></div></div></dialog>
<dialog id="docModal" class="doc-modal" aria-labelledby="docModalTitle"><div class="doc-modal-shell"><div class="doc-modal-top"><span id="docModalId" class="doc-modal-id">Registro documental</span><button type="button" id="closeDocModal" class="doc-close-btn" aria-label="Fechar janela documental">×</button></div><div id="docModalBody" class="doc-modal-body"></div><div id="docModalFoot" class="doc-modal-foot"></div></div></dialog>
"""

    old_boot_script = """<script>
window.GEDIV_READY=(async()=>{const d=window.GEDIV_BOOTSTRAP;if(!Array.isArray(d.rows)||!d.meta?.connection)throw new Error('Resposta inválida');window.GEDIV_DATA=d;document.getElementById('connectionState').textContent='Conectado · '+d.meta.connection.batches+' lote(s) recebido(s) · '+d.meta.pendentes+' registros pendentes';return d;})().catch(e=>{document.getElementById('connectionState').textContent='Não foi possível conectar. Atualize para tentar novamente.';throw e;});"""

    new_boot_script = (
        dialogs_auth_review
        + """<script>
(()=>{
 let _legacyTok='',_usr=null;
 const _purge=()=>{try{sessionStorage.removeItem('gedivTokenGerencia');sessionStorage.removeItem('gedivContaGerencia');localStorage.removeItem('gedivTokenGerencia');localStorage.removeItem('gedivContaGerencia');}catch{}};
 _purge();
 window.GEDIV_AUTH={
  token:()=>_legacyTok,
  user:()=>_usr,
  set:(tok,usr)=>{
   _purge();
   _legacyTok=String(tok||'').trim();
   _usr=usr&&typeof usr==='object'?{usuario:String(usr.usuario||''),nome:String(usr.nome||''),papel:String(usr.papel||'gerencia')}:null;
  },
  setSession:(usr)=>{
   _purge();
   _legacyTok='';
   _usr=usr&&typeof usr==='object'?{usuario:String(usr.usuario||''),nome:String(usr.nome||''),papel:String(usr.papel||'gerencia')}:null;
  },
  clear:()=>{_purge();_legacyTok='';_usr=null;},
  headers:(extra={})=>_legacyTok?{...extra,Authorization:'Bearer '+_legacyTok}:{...extra}
 };
})();
window.GEDIV_FETCH_DATA=async()=>{
 const r=await fetch('/api/data',{cache:'no-store',credentials:'same-origin',headers:window.GEDIV_AUTH.headers({Accept:'application/json'})});
 if(!r.ok)throw new Error('HTTP '+r.status);
 const snap=window.GEDIV_MODEL.acceptSnapshot(await r.json());
 if(snap.backend?.autenticado){
  if(snap.backend.usuario||snap.backend.nome){
   window.GEDIV_AUTH.setSession({usuario:snap.backend.usuario||'gerencia',nome:snap.backend.nome||'Gerência GEDIV',papel:snap.backend.papel||'gerencia'});
  }else if(!window.GEDIV_AUTH.user()&&!window.GEDIV_AUTH.token()){
   try{
    const rs=await fetch('/api/sessao',{cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}});
    if(rs.ok){const s=await rs.json();window.GEDIV_AUTH.setSession(s);}
   }catch{}
  }
 }else if(!window.GEDIV_AUTH.token()){
  window.GEDIV_AUTH.clear();
 }
 return snap;
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

    # 4b. Adicionar controles explícitos Aplicar / Cancelar / Limpar na seção de Período de publicação
    old_dates_html = '<div class="dates"><input type="date" id="from" aria-label="Data inicial"><input type="date" id="to" aria-label="Data final"></div>'
    new_dates_html = (
        '<div class="dates"><input type="date" id="from" aria-label="Data inicial"><input type="date" id="to" aria-label="Data final"></div>'
        '<div class="date-actions" id="dateActions">'
        '<button type="button" id="applyDates" class="date-act-btn is-primary" title="Aplicar período selecionado">Aplicar</button>'
        '<button type="button" id="cancelDates" class="date-act-btn" title="Descartar alteração nas datas">Cancelar</button>'
        '<button type="button" id="clearDates" class="date-act-btn" title="Limpar apenas o período">Limpar</button>'
        '</div>'
    )
    assert old_dates_html in html
    html = html.replace(old_dates_html, new_dates_html, 1)

    # 4c. Atualizar dateBounds() para considerar cobertura pública mensal e applySnapshot() para sincronizar inputs de data
    old_date_bounds = "function dateBounds(){const ds=data.rows.map(r=>r.date).filter(Boolean).sort();minDate=ds[0]||'';maxDate=ds[ds.length-1]||'';}"
    new_date_bounds = (
        "function dateBounds(){"
        "const ds=data.rows.map(r=>r.date).filter(Boolean).sort();"
        "if(ds.length){minDate=ds[0];maxDate=ds[ds.length-1];return;}"
        "const cw=data.meta?.collectionWindow||{};"
        "const pm=(data.backend?.series?.por_data||[]).map(m=>String(m.data||'')).filter(s=>/^\\d{4}-\\d{2}/.test(s)).sort();"
        "if(cw.from&&cw.to){minDate=cw.from;maxDate=cw.to;return;}"
        "if(pm.length){"
        "const a=pm[0].slice(0,7),b=pm[pm.length-1].slice(0,7),[by,bm]=b.split('-').map(Number);"
        "const lastD=new Date(Date.UTC(by,bm,0)).toISOString().slice(0,10);"
        "minDate=a+'-01';maxDate=lastD;return;"
        "}"
        "minDate='';maxDate='';}"
    )
    assert old_date_bounds in html
    html = html.replace(old_date_bounds, new_date_bounds, 1)

    old_apply_snap = "function applySnapshot(snap){if(!snap||!snap.S)return;Object.assign(S,cloneVal(snap.S));beforeToday=cloneVal(snap.beforeToday);inducedByLevel=cloneVal(snap.inducedByLevel);timelinePrev=cloneVal(snap.timelinePrev);resultPrev=cloneVal(snap.resultPrev);cardPrevMode=cloneVal(snap.cardPrevMode);const inp=$('#search');if(inp)inp.value=S.query||'';}"
    new_apply_snap = "function applySnapshot(snap){if(!snap||!snap.S)return;Object.assign(S,cloneVal(snap.S));beforeToday=cloneVal(snap.beforeToday);inducedByLevel=cloneVal(snap.inducedByLevel);timelinePrev=cloneVal(snap.timelinePrev);resultPrev=cloneVal(snap.resultPrev);cardPrevMode=cloneVal(snap.cardPrevMode);const inp=$('#search');if(inp)inp.value=S.query||'';if($('#from'))$('#from').value=S.from||'';if($('#to'))$('#to').value=S.to||'';}"
    assert old_apply_snap in html
    html = html.replace(old_apply_snap, new_apply_snap, 1)

    # 5. Atualizar groupNames e normalização de filtro de grupo (AST e SFT canônicos + PENDENTE apenas para ambíguos/incompatíveis)
    old_group_names = """const groupNames={'NAO_INFORMADO':'Grupo não informado','MAG':'MAG · Magistério','SAUDE':'Saúde','GAJ':'GAJ · Apoio Judiciário','FAP':'FAP · Fiscalização Agropecuária','TEC-ADM':'TEC-ADM · Técnicos Administrativos','ANS':'ANS · Nível Superior','ESPECIAL':'Grupo Especial','DPS':'DPS · Divulgação e Promoção','STF':'STF · Auditor Fiscal Tributário','OSPB':'OSPB · Orquestra Sinfônica','GPC':'GPC · Polícia Civil','SEI':'SEI · Informática','SAT':'SAT · Área Tecnológica','ACI':'ACI · Auditoria e Controle Interno','PPGG':'PPGG · Políticas Públicas e Gestão'};"""
    new_group_names = """const groupNames={'NAO_INFORMADO':'Grupo não informado','MAG':'MAG · Magistério','SSA':'SSA · Saúde','GAJ':'GAJ · Apoio Judiciário','FAP':'FAP · Fiscalização Agropecuária','AST':'AST · Técnicos Administrativos','PENDENTE:TEC. ADM':'TEC. ADM · Técnicos Administrativos (pendente/incompatível)','ANS':'ANS · Nível Superior','ESP':'ESP · Grupo Especial','DPS':'DPS · Divulgação e Promoção','SFT':'SFT · Fazenda · Auditor Fiscal','PENDENTE:STF':'STF · Auditor Fiscal Tributário (pendente/incompatível)','OSPB':'OSPB · Orquestra Sinfônica','GPC':'GPC · Polícia Civil','SEI':'SEI · Informática','SAT':'SAT · Área Tecnológica','ACI':'ACI · Auditoria e Controle Interno','PPGG':'PPGG · Políticas Públicas e Gestão','INT':'INT · Interiorização'};
const GROUP_ALIASES={'TEC-ADM':'AST','TEC. ADM':'AST','SAUDE':'SSA','ESPECIAL':'ESP','GAJ-1700':'GAJ','FAP-1300':'FAP','ANS-900':'ANS','DPS-1600':'DPS','FAZENDA':'SFT'};
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
 if(!data.backend?.autenticado&&!(data.rows||[]).length&&data.backend?.indicadores&&data.backend?.series){
  $('#listHeading').textContent='CONSULTA PÚBLICA';
  const pubDec=data.backend.indicadores.decisoes;
  $('#resultCount').textContent=`Modo público · indicadores agregados protegidos${pubDec!=null?` (${pubDec} decisões, limiar ≥ 5)`:''}`;
  $('#records').innerHTML='<div class="empty-small">Consulta pública ativa: os indicadores e gráficos exibem totais agregados protegidos (limiar mínimo de 5).<br>Use <b>Acesso gerencial</b> no topo para explorar resenhas, processos e conferir registros individuais.</div>';
  $('#pagination').textContent='Modo público';
  $('#prev').disabled=true;$('#next').disabled=true;
  details(null);
  return;
 }
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
 {k:'tempo',name:'Tempo de Serviço',color:'#ff973c'},
 {k:'outros',name:'Outros benefícios',color:'#7c5ce6'}
];
let tlChartMode='monthly', tlOffSeries=new Set(), lastTlRows=[];
function isPublicAgg(){
 return !data.backend?.autenticado&&!(data.rows||[]).length&&!!(data.backend?.indicadores&&data.backend?.series);
}
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
 const pubAgg=isPublicAgg();
 const dailyBtn=bar.querySelector('[data-dl-tl="daily"]');
 if(dailyBtn){
  dailyBtn.disabled=pubAgg;
  dailyBtn.title=pubAgg?'Recorte diário disponível após login gerencial (agregado público é mensal)':'Visualização diária';
  if(pubAgg&&tlChartMode==='daily'){
   tlChartMode='monthly';
   bar.querySelectorAll('[data-dl-tl]').forEach(x=>x.classList.toggle('active',x.dataset.dlTl==='monthly'));
  }
 }
 const pubFromYm=S.from?S.from.slice(0,7):'',pubToYm=S.to?S.to.slice(0,7):'';
 const pubMonths=pubAgg?(data.backend?.series?.por_data||[]).filter(m=>{
  const d=String(m.data||'');if(!/^\\d{4}-\\d{2}/.test(d)||!(Number(m.total||0)>0))return false;
  const ym=d.slice(0,7);
  if(pubFromYm&&ym<pubFromYm)return false;
  if(pubToYm&&ym>pubToYm)return false;
  return true;
 }):[];
 if(!pubAgg&&(tlChartMode==='daily'||!lastTlRows.length)){
  wrap.hidden=true;tl.style.display='';if(legOrig)legOrig.style.display='';
  return;
 }
 if(pubAgg&&!pubMonths.length){
  wrap.hidden=true;tl.style.display='';if(legOrig)legOrig.style.display='';
  $('#timeline').innerHTML='<div class="empty-small">Nenhum mês acima do limiar público (≥ 5) no período selecionado.<br><button type="button" class="empty-action" data-clear-all>Limpar filtros</button></div>';
  return;
 }
 tl.style.display='none';if(legOrig)legOrig.style.display='none';wrap.hidden=false;
 let months=[];
 if(pubAgg){
  months=pubMonths.map(m=>({
   ym:String(m.data).slice(0,7),
   vertical:S.view==='horizontal'||S.view==='tempo'||S.view==='outras'?0:(m.vertical??0),
   horizontal:S.view==='vertical'||S.view==='tempo'||S.view==='outras'?0:(m.horizontal??0),
   tempo:S.view==='vertical'||S.view==='horizontal'||S.view==='outras'?0:(m.tempo??0),
   outros:0,
   pubTotal:Number(m.total||0),
   pubSuppressed:m.vertical==null&&m.horizontal==null&&m.tempo==null&&Number(m.total||0)>0
  })).sort((a,b)=>a.ym.localeCompare(b.ym));
 }else{
  const byMonth={};
  lastTlRows.forEach(r=>{
   const d=String(r.date||'');if(d.length<7)return;
   const ym=d.slice(0,7);
   if(!byMonth[ym])byMonth[ym]={ym,vertical:0,horizontal:0,tempo:0,outros:0};
   if(r.axis==='tempo')byMonth[ym].tempo++;
   else if(r.axis==='outros')byMonth[ym].outros++;
   else if(r.axis==='progressao'&&r.modality==='Horizontal')byMonth[ym].horizontal++;
   else if(r.axis==='progressao'&&r.modality==='Vertical')byMonth[ym].vertical++;
   else byMonth[ym].outros++;
  });
  months=Object.values(byMonth).sort((a,b)=>a.ym.localeCompare(b.ym));
 }
 const active=TL_SERIES.filter(s=>!tlOffSeries.has(s.k));
 const subEl=$('#delicateTlSub');
 if(subEl)subEl.textContent=pubAgg?(tlChartMode==='lines'?'Tendência mensal pública (limiar ≥ 5) · dados individuais protegidos':'Agregação mensal pública (limiar ≥ 5) · dados individuais protegidos'):(tlChartMode==='lines'?'Tendência mensal por modalidade · clique em um mês para filtrar':'Composição mensal por modalidade · clique em um mês para filtrar');
 const W=620,H=168,padL=38,padR=14,padT=14,padB=24,plotW=W-padL-padR,plotH=H-padT-padB;
 const step=plotW/Math.max(1,months.length),barW=Math.min(34,Math.max(14,step*0.58));
 let svg=`<line x1="${padL}" y1="${padT}" x2="${W-padR}" y2="${padT}" stroke="#e5edf5"/>
  <line x1="${padL}" y1="${padT+plotH/2}" x2="${W-padR}" y2="${padT+plotH/2}" stroke="#e5edf5"/>
  <line x1="${padL}" y1="${padT+plotH}" x2="${W-padR}" y2="${padT+plotH}" stroke="#d5e3f1"/>`;
 if(tlChartMode==='lines'){
  const maxV=pubAgg
   ?Math.max(1,...months.flatMap(m=>[m.pubTotal||0,...active.map(s=>m[s.k]||0)]))
   :Math.max(1,...months.flatMap(m=>active.map(s=>m[s.k])));
  svg+=`<text x="${padL-6}" y="${padT+4}" font-size="9.5" fill="#405d79" text-anchor="end">${maxV}</text>
        <text x="${padL-6}" y="${padT+plotH/2+4}" font-size="9.5" fill="#405d79" text-anchor="end">${Math.round(maxV/2)}</text>
        <text x="${padL-6}" y="${padT+plotH+3}" font-size="9.5" fill="#405d79" text-anchor="end">0</text>`;
  if(pubAgg){
   const ptsTot=months.map((m,i)=>`${(padL+step*i+step/2).toFixed(1)},${(padT+plotH-(plotH*(m.pubTotal||0)/maxV)).toFixed(1)}`).join(' ');
   svg+=`<polyline fill="none" stroke="#94a3b8" stroke-dasharray="4 3" stroke-width="1.8" points="${ptsTot}"/>`;
  }
  active.forEach(s=>{
   const pts=months.map((m,i)=>`${(padL+step*i+step/2).toFixed(1)},${(padT+plotH-(plotH*m[s.k]/maxV)).toFixed(1)}`).join(' ');
   svg+=`<polyline fill="none" stroke="${s.color}" stroke-width="2.3" points="${pts}"/>`;
   months.forEach((m,i)=>{
    const cx=(padL+step*i+step/2).toFixed(1),cy=(padT+plotH-(plotH*m[s.k]/maxV)).toFixed(1);
    const lbl=MONTH_SHORT[Number(m.ym.slice(5,7))-1]+'/'+m.ym.slice(2,4);
    const totM=pubAgg?(m.pubTotal||0):(m.vertical+m.horizontal+m.tempo+m.outros);
    const tip=`${lbl} · ${s.name}: ${m[s.k]} | Total no mês: ${totM}`;
    svg+=`<circle cx="${cx}" cy="${cy}" r="4" fill="${s.color}" tabindex="0" role="button" aria-label="${esc(tip)}" data-dtip="${esc(tip)}" data-ym="${m.ym}"/>`;
   });
  });
 }else{
  const barVal=m=>m.pubSuppressed?(S.view==='geral'||S.view==='historico'?m.pubTotal:0):active.reduce((a,s)=>a+m[s.k],0);
  const maxT=Math.max(1,...months.map(barVal));
  svg+=`<text x="${padL-6}" y="${padT+4}" font-size="9.5" fill="#405d79" text-anchor="end">${maxT}</text>
        <text x="${padL-6}" y="${padT+plotH/2+4}" font-size="9.5" fill="#405d79" text-anchor="end">${Math.round(maxT/2)}</text>
        <text x="${padL-6}" y="${padT+plotH+3}" font-size="9.5" fill="#405d79" text-anchor="end">0</text>`;
  months.forEach((m,i)=>{
   let y=padT+plotH;const x=padL+step*i+(step-barW)/2;
   const lbl=MONTH_SHORT[Number(m.ym.slice(5,7))-1]+'/'+m.ym.slice(2,4);
   let rects='',tip='';
   if(m.pubSuppressed){
    const v=barVal(m);
    tip=`${lbl} · Total protegido: ${m.pubTotal} (detalhe por modalidade suprimido < 5)`;
    if(v>0){
     const bh=Math.max(3,plotH*v/maxT);y-=bh;
     rects+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${bh.toFixed(1)}" rx="1.5" fill="#94a3b8"/>`;
    }
   }else{
    const tot=m.vertical+m.horizontal+m.tempo+m.outros;
    tip=`${lbl} · Total: ${tot} (Vertical: ${m.vertical} · Horizontal: ${m.horizontal} · Tempo: ${m.tempo} · Outros: ${m.outros})`;
    active.forEach(s=>{
     if(!m[s.k])return;
     const bh=Math.max(3,plotH*m[s.k]/maxT);y-=bh;
     rects+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${bh.toFixed(1)}" rx="1.5" fill="${s.color}"/>`;
    });
   }
   svg+=`<g tabindex="0" role="button" aria-label="${esc(tip)}" data-dtip="${esc(tip)}" data-ym="${m.ym}">${rects}<rect x="${x.toFixed(1)}" y="${padT}" width="${barW.toFixed(1)}" height="${plotH}" fill="transparent"/></g>`;
  });
 }
 months.forEach((m,i)=>{
  const cx=(padL+step*i+step/2).toFixed(1),lbl=MONTH_SHORT[Number(m.ym.slice(5,7))-1];
  svg+=`<text x="${cx}" y="${H-6}" font-size="9.5" fill="#405d79" text-anchor="middle">${lbl}</text>`;
 });
 const totals=pubAgg
  ?{
    vertical:((data.backend.series.por_assunto||[]).find(a=>a.chave==='VERTICAL')?.total)??0,
    horizontal:((data.backend.series.por_assunto||[]).find(a=>a.chave==='HORIZONTAL')?.total)??0,
    tempo:((data.backend.series.por_assunto||[]).find(a=>a.chave==='TEMPO_SERVICO')?.total)??0,
    outros:0
   }
  :{vertical:lastTlRows.filter(r=>r.axis==='progressao'&&r.modality==='Vertical').length,horizontal:lastTlRows.filter(r=>r.axis==='progressao'&&r.modality==='Horizontal').length,tempo:lastTlRows.filter(r=>r.axis==='tempo').length,outros:lastTlRows.filter(r=>r.axis==='outros'||(r.axis==='progressao'&&r.modality!=='Vertical'&&r.modality!=='Horizontal')).length};
 wrap.innerHTML=`<svg class="delicate-tl-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolução mensal das publicações">${svg}</svg>
  <div class="delicate-tl-leg">${TL_SERIES.map(s=>`<button type="button" class="delicate-lg-btn ${tlOffSeries.has(s.k)?'is-off':''}" data-tl-ser="${s.k}" aria-pressed="${!tlOffSeries.has(s.k)}"><i class="delicate-lg-dot" style="background:${s.color}"></i>${s.name} (${totals[s.k]})</button>`).join('')}</div>
  <div class="delicate-tl-tip" id="delicateTlTip" role="status">${pubAgg?'Passe o mouse ou foque em um mês para ver o agregado público (limiar ≥ 5).':'Clique em um mês para filtrar o período · clique na legenda para isolar séries.'}</div>
  <div class="delicate-tl-note">Lacunas ou ausência de barra refletem falta de coleta no intervalo ou filtro aplicado — nunca equivalem a zero publicações confirmadas.</div>`;
 wrap.querySelectorAll('[data-tl-ser]').forEach(b=>b.addEventListener('click',()=>{
  const k=b.dataset.tlSer;
  if(tlOffSeries.has(k))tlOffSeries.delete(k);else if(tlOffSeries.size<TL_SERIES.length-1)tlOffSeries.add(k);
  renderDelicateTimeline(lastTlRows);
 }));
 wrap.querySelectorAll('[data-dtip]').forEach(el=>{
  const showTip=()=>{const t=$('#delicateTlTip');if(t)t.textContent=el.dataset.dtip;};
  const toggleMonth=()=>{
   showTip();
   const ym=el.dataset.ym;if(!ym)return;
   const [yy,mm]=ym.split('-').map(Number);
   const mStart=`${ym}-01`,mEnd=new Date(Date.UTC(yy,mm,0)).toISOString().slice(0,10);
   if(S.from===mStart&&S.to===mEnd){S.from='';S.to='';}else{S.from=mStart;S.to=mEnd;}
   S.page=0;timelinePrev=null;beforeToday=null;commitHistory();render();
  };
  el.addEventListener('mouseenter',showTip);el.addEventListener('focus',showTip);
  el.addEventListener('click',toggleMonth);
  el.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();toggleMonth();}});
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

    # 5c-bis. Paridade integral dos cartões, gráficos e filtros com a fonte única de cálculo (Etapa 4B, 0 cores novas)
    html = html.replace(
        "const catName=id=>data.categories.find(x=>x[0]===id)?.[1]||'Não informado';",
        "const catName=id=>id==='SEM_SUBCATEGORIA'?'Subcategoria pendente de conferência':(data.categories.find(x=>x[0]===id)?.[1]||'Não informado');",
        1,
    )

    old_sync_cats = """ const mNoCat=window.GEDIV_MODEL.dashboardModel(data,{...S,category:[],card:'',groupNames}).original;
 const tempoRows=mNoCat.filter(r=>r.axis==='tempo');
 $('#serviceFilters').innerHTML=data.categories.map(([id,label])=>{const count=tempoRows.filter(r=>r.category===id).length,active=S.category.includes(id);return `<button data-cat="${id}" class="${active?'active':''} ${count?'':'is-zero'}" aria-pressed="${active}" title="${esc(label)} (${count})"><span class="svc-main"><i></i><span>${esc(label)}</span></span><span class="svc-count">${count}</span></button>`;}).join('');"""
    new_sync_cats = """ const mNoCat=window.GEDIV_MODEL.dashboardModel(data,{...S,category:[],card:'',groupNames}).original;
 const tempoRows=mNoCat.filter(r=>r.axis==='tempo');
 const tsCats=data.categories.filter(([id])=>id!=='ABONO_PERMANENCIA');
 const semSubCnt=tempoRows.filter(r=>!r.category).length;
 const allSvcCats=semSubCnt||S.category.includes('SEM_SUBCATEGORIA')?tsCats.concat([['SEM_SUBCATEGORIA','Subcategoria pendente de conferência']]):tsCats;
 $('#serviceFilters').innerHTML=allSvcCats.map(([id,label])=>{const count=id==='SEM_SUBCATEGORIA'?semSubCnt:tempoRows.filter(r=>r.category===id).length,active=S.category.includes(id);return `<button data-cat="${id}" class="${active?'active':''} ${count?'':'is-zero'}" aria-pressed="${active}" title="${esc(label)} (${count})"><span class="svc-main"><i></i><span>${esc(label)}</span></span><span class="svc-count">${count}</span></button>`;}).join('');"""
    assert old_sync_cats in html
    html = html.replace(old_sync_cats, new_sync_cats, 1)

    old_kpis = """function kpis(m){
 const preliminary=S.validation==='pendente',total=m.decisions||0;
 const cards=[['resenhas','Resenhas',m.resenhas,'publicações distintas','■',''],['processes','Processos',m.processes,'processos identificados','■',''],['decisions',preliminary?'Registros extraídos':'Decisões',m.decisions,preliminary?'conferência pendente':'decisões conferidas','■',''],['deferidos',preliminary?'Deferidos · extraídos':'Deferidos',m.deferidos,`${pct(m.deferidos,total)} do total · ${preliminary?'a conferir':'conferidas'}`,'✓','green'],['indeferidos',preliminary?'Indeferidos · extraídos':'Indeferidos',m.indeferidos,`${pct(m.indeferidos,total)} do total · ${preliminary?'a conferir':'conferidas'}`,'×','red'],['refeitos','Refeitos',m.refeitos,'atos com alteração','<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>','amber'],['semEfeito','Sem efeito',m.semEfeito,'atos na amostra','<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>','red']];
 $('#kpis').innerHTML=cards.map(([id,label,value,sub,icon,color])=>{const active=(id==='deferidos'&&S.merit==='deferido')||(id==='indeferidos'&&S.merit==='indeferido')||S.card===id;return `<button class="kpi ${color} ${active?'active':''}" data-card="${id}" ${value==null?'disabled':''} title="${value==null?'Vinculação documental pendente':'Filtrar por '+esc(label)}"><span class="label">${esc(label)}</span><span class="marker" aria-hidden="true">${icon}</span><b class="val">${value==null?'—':value}</b><span class="sub">${value==null?'Vínculo ainda pendente':esc(sub)}</span></button>`;}).join('');
}"""
    new_kpis = """function kpis(m){
 if(isPublicAgg()){
  const bi=data.backend.indicadores||{},bs=data.backend.series||{},pa=bs.por_assunto||[];
  const byK=k=>pa.find(x=>x.chave===k)||{};
  let pRes=bi.resenhas,pProc=bi.processos,pDec=bi.decisoes,pDef=bi.deferidos,pInd=bi.indeferidos,pRef=bi.refeitos,pSe=bi.sem_efeito;
  if(S.view==='vertical'||S.view==='horizontal'||S.view==='tempo'){
   const item=byK(S.view==='vertical'?'VERTICAL':S.view==='horizontal'?'HORIZONTAL':'TEMPO_SERVICO');
   pRes=null;pProc=null;pDec=item.total??null;pDef=item.deferido??null;pInd=item.indeferido??null;pRef=null;pSe=null;
  }else if(S.view==='outras'){
   pRes=null;pProc=null;pDec=null;pDef=null;pInd=null;pRef=null;pSe=null;
  }else if(S.view==='hoje'){
   pRes=null;pProc=null;pDec=null;pDef=null;pInd=null;pRef=null;pSe=null;
  }
  const pubSub=v=>v==null?'Protegido (< 5) ou restrito':'agregado público (≥ 5)';
  const cards=[
   ['resenhas','Resenhas',pRes,pubSub(pRes),'■',''],
   ['processes','Processos',pProc,pubSub(pProc),'■',''],
   ['decisions','Decisões',pDec,pubSub(pDec),'■',''],
   ['deferidos','Deferidos',pDef,pDef!=null&&pDec?`${pct(pDef,pDec)} do total · público`:pubSub(pDef),'✓','green'],
   ['indeferidos','Indeferidos',pInd,pInd!=null&&pDec?`${pct(pInd,pDec)} do total · público`:pubSub(pInd),'×','red'],
   ['refeitos','Refeitos',pRef,pubSub(pRef),'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>','amber'],
   ['semEfeito','Sem efeito',pSe,pubSub(pSe),'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>','red']
  ];
  $('#kpis').innerHTML=cards.map(([id,label,value,sub,icon,color])=>`<button class="kpi ${color}" data-card="${id}" ${value==null?'disabled':'aria-disabled="true" style="cursor:default"'} title="Modo público: indicadores agregados protegidos"><span class="label">${esc(label)}</span><span class="marker" aria-hidden="true">${icon}</span><b class="val">${value==null?'—':value}</b><span class="sub">${esc(sub)}</span></button>`).join('');
  return;
 }
 const preliminary=S.validation==='pendente',total=m.decisions||0;
 const procSub=m.processes?`${m.processesDeferidos||0} D · ${m.processesIndeferidos||0} I${m.processesMistos?` · ${m.processesMistos} mistos`:''}${m.processesNaoInformado?` · ${m.processesNaoInformado} NI`:''}`:'processos identificados';
 const decSub=`${m.servers||0} serv. (${m.benefitedServers||0} benef.)${m.naoInformado?` · ${m.naoInformado} NI`:''} · ${preliminary?'não homologado':'conferidas'}`;
 const refSub=`${m.republicacoes||0} rep. · ${m.retificacoes||0} ret.${m.correcoes?` · ${m.correcoes} corr.`:''}`;
 const seSub=`${m.semEfeito||0} ato(s) · ${m.decisoesSemEfeito||0} dec. atingida(s)`;
 const cards=[['resenhas','Resenhas',m.resenhas,'publicações distintas','■',''],['processes','Processos',m.processes,procSub,'■',''],['decisions',preliminary?'Registros extraídos':'Decisões',m.decisions,decSub,'■',''],['deferidos',preliminary?'Deferidos · extraídos':'Deferidos',m.deferidos,`${pct(m.deferidos,total)} do total · ${preliminary?'a conferir':'conferidas'}`,'✓','green'],['indeferidos',preliminary?'Indeferidos · extraídos':'Indeferidos',m.indeferidos,`${pct(m.indeferidos,total)} do total · ${preliminary?'a conferir':'conferidas'}`,'×','red'],['refeitos','Refeitos',m.refeitos,refSub,'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>','amber'],['semEfeito','Sem efeito',m.semEfeito,seSub,'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>','red']];
 $('#kpis').innerHTML=cards.map(([id,label,value,sub,icon,color])=>{const active=(id==='deferidos'&&S.merit==='deferido')||(id==='indeferidos'&&S.merit==='indeferido')||S.card===id;return `<button class="kpi ${color} ${active?'active':''}" data-card="${id}" ${value==null?'disabled':''} title="${value==null?'Vinculação documental pendente':'Filtrar por '+esc(label)}"><span class="label">${esc(label)}</span><span class="marker" aria-hidden="true">${icon}</span><b class="val">${value==null?'—':value}</b><span class="sub">${value==null?'Vínculo ainda pendente':esc(sub)}</span></button>`;}).join('');
}"""
    assert old_kpis in html
    html = html.replace(old_kpis, new_kpis, 1)

    old_axis = """function axisChart(rows){
 let list=[], title='Publicações por assunto',subtitle='Clique na fatia ou na legenda para detalhar';
 if(S.group||S.category.length||S.axis==='outros'||S.view==='outras'){
  title=(S.axis==='outros'||S.view==='outras')?'Resultados de Outros benefícios':'Resultados da seleção';subtitle='Clique em deferidos ou indeferidos';
  list=[['Deferidos','deferido','#17a675'],['Indeferidos','indeferido','#e86167']].map(([label,key,color])=>({label,key,color,kind:'merit',value:rows.filter(r=>r.merit===key).length}));
 }else if(S.axis==='tempo'||S.view==='tempo'){
  title='Distribuição por serviço';subtitle='Participação dos serviços em Tempo de Serviço';
  let colors=['#f49b45','#d36a44','#e0ad40','#d2866d','#bf6858','#e8be79','#a879bb'];
  list=data.categories.map(([key,label],i)=>({key,label,color:colors[i],kind:'category',value:rows.filter(r=>r.category===key).length}));
 }else if((S.axis==='progressao'||S.view==='vertical'||S.view==='horizontal')&&S.modality){
  title='Distribuição por grupo';subtitle='Participação dos grupos na modalidade selecionada';
  let colors=['#2480f3','#16a788','#f49b45','#9b73d6','#dd6877','#3f9faa','#9a9d54','#7773bc','#e2b451','#b76e83','#368cc2','#64a770','#c77f47','#9c8dc2','#899eaf'];
  list=Object.entries(groupNames).map(([key,label],i)=>({key,label,color:colors[i%colors.length],kind:'group',value:rows.filter(r=>key==='NAO_INFORMADO'?!r.group:r.group===key).length})).filter(x=>x.value||x.key===S.group);
 }else{
  list=[['Vertical','vertical','#1265ef'],['Horizontal','horizontal','#13b88a'],['Tempo de Serviço','tempo','#ff973c'],['Outros benefícios','outros','#7c5ce6']].map(([label,key,color])=>({label,key,color,kind:'axis',value:rows.filter(r=>key==='tempo'?r.axis==='tempo':key==='outros'?r.axis==='outros':(r.modality||'').toLowerCase()===key).length}));
 }
 $('#axisChartTitle').textContent=title;$('#axisChartSubtitle').textContent=subtitle;
 let n=list.reduce((a,x)=>a+x.value,0),offset=0;
 let circles=n?list.filter(x=>x.value).map(x=>{let result=donutPath(x,x.value,n,offset);offset+=x.value;return result;}).join(''):'<circle cx="70" cy="70" r="52" fill="none" stroke="#e7eef5" stroke-width="26"></circle>';
 $('#axisChart').innerHTML=`<div class="interactive-donut"><svg viewBox="0 0 140 140" role="group" aria-label="${esc(title)}">${circles}</svg><div class="donut-label"><b>${data.meta.semBaseCarregada?'—':n}</b><span>${n===1?'decisão':'decisões'}</span></div></div><div class="axis-legend">${list.map(x=>`<button data-kind="${esc(x.kind)}" data-key="${esc(x.key)}" aria-label="Selecionar ${esc(x.label)}, ${x.value} decisões"><i style="background:${x.color}"></i><span>${esc(x.label)} <b>${data.meta.semBaseCarregada?'—':x.value}</b>${n?' · '+Math.round(100*x.value/n)+'%':''}</span></button>`).join('')||'<small>Nenhum registro nesta visão e filtros. A cobertura continua parcial.</small>'}</div>`;
}"""
    new_axis = """function axisChart(rows){
 if(isPublicAgg()){
  const bs=data.backend.series||{},bi=data.backend.indicadores||{};
  let list=[],title='Publicações por assunto',subtitle='Agregados públicos protegidos (limiar ≥ 5)';
  if(S.view==='tempo'||S.axis==='tempo'){
   title='Distribuição por serviço';subtitle='Serviços em Tempo de Serviço (limiar ≥ 5)';
   const colors=['#f49b45','#d36a44','#e0ad40','#d2866d','#bf6858','#e8be79','#a879bb','#94a3b8'];
   list=(bs.por_subcategoria||[]).map((x,i)=>({key:x.codigo,label:x.nome,color:colors[i%colors.length],kind:'category',value:Number(x.total||0)})).filter(x=>x.value>0);
  }else if(S.view==='vertical'||S.view==='horizontal'){
   title='Distribuição por grupo';subtitle='Participação dos grupos no agregado público (limiar ≥ 5)';
   const colors=['#2480f3','#16a788','#f49b45','#9b73d6','#dd6877','#3f9faa','#9a9d54','#7773bc','#e2b451','#b76e83'];
   const fld=S.view==='vertical'?'vertical':'horizontal';
   list=(bs.por_grupo||[]).map((g,i)=>({key:g.grupo,label:labelGroup(g.grupo),color:colors[i%colors.length],kind:'group',value:Number(g[fld]||0)})).filter(x=>x.value>0);
  }else if(S.view==='outras'||S.view==='hoje'){
   title=S.view==='outras'?'Outras publicações':'Recorte diário protegido';subtitle='Consulte após login gerencial para detalhamento nominal';
   list=[];
  }else{
   const pa=bs.por_assunto||[],valOf=k=>Number((pa.find(x=>x.chave===k)||{}).total||0);
   list=[['Vertical','vertical','#1265ef','VERTICAL'],['Horizontal','horizontal','#13b88a','HORIZONTAL'],['Tempo de Serviço','tempo','#ff973c','TEMPO_SERVICO']].map(([label,key,color,ck])=>({label,key,color,kind:'axis',value:valOf(ck)}));
  }
  $('#axisChartTitle').textContent=title;$('#axisChartSubtitle').textContent=subtitle;
  const sumList=list.reduce((a,x)=>a+x.value,0);
  const centerVal=(S.view==='geral'||S.view==='historico')&&bi.decisoes!=null?bi.decisoes:sumList;
  let offset=0;
  const circles=sumList?list.filter(x=>x.value).map(x=>{let r=donutPath(x,x.value,sumList,offset);offset+=x.value;return r;}).join(''):'<circle cx="70" cy="70" r="52" fill="none" stroke="#e7eef5" stroke-width="26"></circle>';
  $('#axisChart').innerHTML=`<div class="interactive-donut"><svg viewBox="0 0 140 140" role="group" aria-label="${esc(title)}">${circles}</svg><div class="donut-label"><b>${centerVal?centerVal:'—'}</b><span>${centerVal===1?'decisão':'decisões'}</span></div></div><div class="axis-legend">${list.map(x=>`<button data-kind="${esc(x.kind)}" data-key="${esc(x.key)}" aria-label="${esc(x.label)}, ${x.value} decisões"><i style="background:${x.color}"></i><span>${esc(x.label)} <b>${x.value}</b>${sumList?' · '+Math.round(100*x.value/sumList)+'%':''}</span></button>`).join('')||'<small>Detalhamento disponível após login gerencial.</small>'}</div>`;
  return;
 }
 let list=[], title='Publicações por assunto',subtitle='Clique na fatia ou na legenda para detalhar';
 if(S.group||S.category.length||S.axis==='outros'||S.view==='outras'){
  title=(S.axis==='outros'||S.view==='outras')?'Resultados de Outras publicações':'Resultados da seleção';subtitle='Clique em deferidos, indeferidos ou não informados';
  list=[['Deferidos','deferido','#17a675'],['Indeferidos','indeferido','#e86167']].map(([label,key,color])=>({label,key,color,kind:'merit',value:rows.filter(r=>r.merit===key).length}));
  const niVal=rows.filter(r=>r.merit!=='deferido'&&r.merit!=='indeferido').length;
  if(niVal>0)list.push({label:'Não informado',key:'outro',color:'#e0ad40',kind:'merit',value:niVal});
 }else if(S.axis==='tempo'||S.view==='tempo'){
  title='Distribuição por serviço';subtitle='Participação dos serviços em Tempo de Serviço';
  let colors=['#f49b45','#d36a44','#e0ad40','#d2866d','#bf6858','#e8be79','#a879bb','#94a3b8'];
  const tsCats=data.categories.filter(([k])=>k!=='ABONO_PERMANENCIA');
  list=tsCats.map(([key,label],i)=>({key,label,color:colors[i%colors.length],kind:'category',value:rows.filter(r=>r.category===key).length}));
  const semSub=rows.filter(r=>r.axis==='tempo'&&!r.category).length;
  if(semSub>0)list.push({key:'SEM_SUBCATEGORIA',label:'Subcategoria pendente',color:'#94a3b8',kind:'category',value:semSub});
 }else if((S.axis==='progressao'||S.view==='vertical'||S.view==='horizontal')&&S.modality){
  title='Distribuição por grupo';subtitle='Participação dos grupos na modalidade selecionada';
  let colors=['#2480f3','#16a788','#f49b45','#9b73d6','#dd6877','#3f9faa','#9a9d54','#7773bc','#e2b451','#b76e83','#368cc2','#64a770','#c77f47','#9c8dc2','#899eaf'];
  list=Object.entries(groupNames).map(([key,label],i)=>({key,label,color:colors[i%colors.length],kind:'group',value:rows.filter(r=>key==='NAO_INFORMADO'?!r.group:r.group===key).length})).filter(x=>x.value||x.key===S.group);
 }else{
  list=[['Vertical','vertical','#1265ef'],['Horizontal','horizontal','#13b88a'],['Tempo de Serviço','tempo','#ff973c']].map(([label,key,color])=>({label,key,color,kind:'axis',value:rows.filter(r=>key==='tempo'?r.axis==='tempo':(r.axis==='progressao'&&(r.modality||'').toLowerCase()===key)).length}));
  const semMod=rows.filter(r=>r.axis==='progressao'&&r.modality!=='Vertical'&&r.modality!=='Horizontal').length;
  if(semMod>0)list.push({label:'Modalidade pendente',key:'progressao',color:'#94a3b8',kind:'axis',value:semMod});
  const outVal=rows.filter(r=>r.axis==='outros').length;
  if(outVal>0)list.push({label:'Outros benefícios',key:'outros',color:'#7c5ce6',kind:'axis',value:outVal});
 }
 $('#axisChartTitle').textContent=title;$('#axisChartSubtitle').textContent=subtitle;
 let n=list.reduce((a,x)=>a+x.value,0),offset=0;
 let circles=n?list.filter(x=>x.value).map(x=>{let result=donutPath(x,x.value,n,offset);offset+=x.value;return result;}).join(''):'<circle cx="70" cy="70" r="52" fill="none" stroke="#e7eef5" stroke-width="26"></circle>';
 $('#axisChart').innerHTML=`<div class="interactive-donut"><svg viewBox="0 0 140 140" role="group" aria-label="${esc(title)}">${circles}</svg><div class="donut-label"><b>${data.meta.semBaseCarregada?'—':n}</b><span>${n===1?'decisão':'decisões'}</span></div></div><div class="axis-legend">${list.map(x=>`<button data-kind="${esc(x.kind)}" data-key="${esc(x.key)}" aria-label="Selecionar ${esc(x.label)}, ${x.value} decisões"><i style="background:${x.color}"></i><span>${esc(x.label)} <b>${data.meta.semBaseCarregada?'—':x.value}</b>${n?' · '+Math.round(100*x.value/n)+'%':''}</span></button>`).join('')||'<small>Nenhum registro nesta visão e filtros. A cobertura continua parcial.</small>'}</div>`;
}"""
    assert old_axis in html
    html = html.replace(old_axis, new_axis, 1)

    old_service_bars = """function serviceBars(rows){
 let tempo=rows.filter(r=>r.axis==='tempo'),totalTempo=tempo.length,max=Math.max(1,...data.categories.map(c=>tempo.filter(r=>r.category===c[0]).length)),isPct=metricMode.service==='pct',den=isPct?Math.max(1,totalTempo):max;
 $('#serviceBars').innerHTML=data.categories.map(([id,label])=>{let items=tempo.filter(r=>r.category===id),n=items.length,d=items.filter(r=>r.merit==='deferido').length,i=items.filter(r=>r.merit==='indeferido').length,txt=n?(isPct?`${pct(n,totalTempo)} (${Math.round(100*d/n)}% def.)`:`${d} def. · ${i} ind.`):'sem registros nesta visão';return `<div class="service-row ${S.category.includes(id)?'selected-row':''}"><button class="service-name" data-cat="${id}" title="Selecionar ${esc(label)}">${esc(label)}</button><button class="result-track" data-cat="${id}" aria-label="${esc(label)}: ${d} deferidos e ${i} indeferidos na amostra (${pct(n,totalTempo)})" title="${n} de ${totalTempo} (${pct(n,totalTempo)}) · ${d} def. · ${i} ind."><span class="part good" style="width:${d*100/den}%"></span><span class="part bad" style="width:${i*100/den}%"></span></button><span class="service-value ${n?'':'pending'}">${txt}</span></div>`;}).join('');
}"""
    new_service_bars = """function serviceBars(rows){
 if(isPublicAgg()){
  const bs=data.backend.series||{},subs=bs.por_subcategoria||[],isPct=metricMode.service==='pct';
  const totalTempo=subs.reduce((a,x)=>a+Number(x.total||0),0);
  const max=Math.max(1,...subs.map(x=>Number(x.total||0))),den=isPct?Math.max(1,totalTempo):max;
  $('#serviceBars').innerHTML=subs.map(x=>{
   const n=x.total,d=x.deferido,i=x.indeferido,hasN=n!=null&&n>0,hasDI=hasN&&d!=null&&i!=null;
   const txt=n==null?'suprimido (< 5)':n===0?'sem registros nesta visão':hasDI?(isPct?`${pct(n,totalTempo)} (${Math.round(100*d/n)}% def.)`:`${d} def. · ${i} ind.`):`${n} (D/I < 5)`;
   const bars=hasDI?`<span class="part good" style="width:${d*100/den}%"></span><span class="part bad" style="width:${i*100/den}%"></span>`:(hasN?`<span class="part" style="width:${n*100/den}%;background:#1265ef"></span>`:'');
   return `<div class="service-row"><button class="service-name" data-cat="${esc(x.codigo)}" disabled>${esc(x.nome)}</button><button class="result-track" data-cat="${esc(x.codigo)}" disabled aria-label="${esc(x.nome)}: ${esc(txt)}">${bars}</button><span class="service-value ${hasN?'':'pending'}">${txt}</span></div>`;
  }).join('');
  return;
 }
 let tempo=rows.filter(r=>r.axis==='tempo'),totalTempo=tempo.length,tsCats=data.categories.filter(([id])=>id!=='ABONO_PERMANENCIA');
 const semSubItems=tempo.filter(r=>!r.category);
 const catsVis=semSubItems.length||S.category.includes('SEM_SUBCATEGORIA')?tsCats.concat([['SEM_SUBCATEGORIA','Subcategoria pendente de conferência']]):tsCats;
 let max=Math.max(1,...catsVis.map(([id])=>(id==='SEM_SUBCATEGORIA'?semSubItems:tempo.filter(r=>r.category===id)).length)),isPct=metricMode.service==='pct',den=isPct?Math.max(1,totalTempo):max;
 $('#serviceBars').innerHTML=catsVis.map(([id,label])=>{let items=id==='SEM_SUBCATEGORIA'?semSubItems:tempo.filter(r=>r.category===id),n=items.length,d=items.filter(r=>r.merit==='deferido').length,i=items.filter(r=>r.merit==='indeferido').length,ni=n-d-i,txt=n?(isPct?`${pct(n,totalTempo)} (${Math.round(100*d/n)}% def.)`:`${d} def. · ${i} ind.${ni?` · ${ni} NI`:''}`):'sem registros nesta visão';return `<div class="service-row ${S.category.includes(id)?'selected-row':''}"><button class="service-name" data-cat="${id}" title="Selecionar ${esc(label)}">${esc(label)}</button><button class="result-track" data-cat="${id}" aria-label="${esc(label)}: ${d} deferidos, ${i} indeferidos e ${ni} não informados (${pct(n,totalTempo)})" title="${n} de ${totalTempo} (${pct(n,totalTempo)}) · ${d} def. · ${i} ind.${ni?` · ${ni} NI`:''}"><span class="part good" style="width:${d*100/den}%"></span><span class="part bad" style="width:${i*100/den}%"></span>${ni?`<span class="part" style="width:${ni*100/den}%;background:#e0ad40"></span>`:''}</button><span class="service-value ${n?'':'pending'}">${txt}</span></div>`;}).join('');
}"""
    assert old_service_bars in html
    html = html.replace(old_service_bars, new_service_bars, 1)

    old_group_chart = """function groupChart(rows){
 let progress=rows.filter(r=>r.axis==='progressao'),totalProg=progress.length,isPct=metricMode.group==='pct',entries=Object.entries(groupNames).map(([id,name])=>{let items=progress.filter(r=>(id==='NAO_INFORMADO'?!r.group:r.group===id));return {id,name,items,d:items.filter(r=>r.merit==='deferido').length,i:items.filter(r=>r.merit==='indeferido').length,n:items.length};});
 let max=Math.max(1,...entries.map(x=>x.n)),den=isPct?Math.max(1,totalProg):max,zeroCount=entries.filter(x=>!x.n).length,shown=showZeroGroups?entries:entries.filter(x=>x.n>0||S.group===x.id);
 const btn=$('#toggleZeroGroups');
 if(btn){btn.hidden=zeroCount===0;btn.textContent=showZeroGroups?'Ocultar zerados':`Mostrar zerados (${zeroCount})`;}
 $('#groupChart').innerHTML=shown.length?shown.map(x=>{const txt=x.n?(isPct?`${pct(x.n,totalProg)} (${Math.round(100*x.d/x.n)}% D)`:`${x.d} D · ${x.i} I`):'—';return `<button class="group-row ${S.group===x.id?'selected-row':''}" data-group="${esc(x.id)}" aria-label="${esc(x.name)}: ${x.d} deferidos e ${x.i} indeferidos na amostra (${pct(x.n,totalProg)})" title="${x.n} de ${totalProg} (${pct(x.n,totalProg)}) · ${x.d} D · ${x.i} I"><span>${esc(x.name)}</span><span class="result-track"><span class="part good" style="width:${x.d*100/den}%"></span><span class="part bad" style="width:${x.i*100/den}%"></span></span><b>${txt}</b></button>`;}).join(''):'<div class="empty-small">Nenhum grupo com registros neste recorte.</div>';
}"""
    new_group_chart = """function groupChart(rows){
 if(isPublicAgg()){
  const bs=data.backend.series||{},grps=bs.por_grupo||[],isPct=metricMode.group==='pct';
  const fld=S.view==='vertical'?'vertical':S.view==='horizontal'?'horizontal':'total';
  const entries=grps.map(g=>({id:g.grupo,name:labelGroup(g.grupo),n:g[fld],d:fld==='total'?g.deferido:null,i:fld==='total'?g.indeferido:null})).filter(x=>x.n!=null&&x.n>0);
  const totalProg=entries.reduce((a,x)=>a+x.n,0),max=Math.max(1,...entries.map(x=>x.n)),den=isPct?Math.max(1,totalProg):max;
  const btn=$('#toggleZeroGroups');if(btn)btn.hidden=true;
  $('#groupChart').innerHTML=entries.length?entries.map(x=>{
   const hasDI=x.d!=null&&x.i!=null;
   const txt=hasDI?(isPct?`${pct(x.n,totalProg)} (${Math.round(100*x.d/x.n)}% D)`:`${x.d} D · ${x.i} I`):(isPct?`${pct(x.n,totalProg)}`:`${x.n} (≥ 5)`);
   const bars=hasDI?`<span class="part good" style="width:${x.d*100/den}%"></span><span class="part bad" style="width:${x.i*100/den}%"></span>`:`<span class="part" style="width:${x.n*100/den}%;background:#1265ef"></span>`;
   return `<button class="group-row" data-group="${esc(x.id)}" disabled aria-label="${esc(x.name)}: ${esc(txt)}"><span>${esc(x.name)}</span><span class="result-track">${bars}</span><b>${txt}</b></button>`;
  }).join(''):'<div class="empty-small">Nenhum grupo acima do limiar público (≥ 5) neste recorte.</div>';
  return;
 }
 let progress=rows.filter(r=>r.axis==='progressao'),totalProg=progress.length,isPct=metricMode.group==='pct',entries=Object.entries(groupNames).map(([id,name])=>{let items=progress.filter(r=>(id==='NAO_INFORMADO'?!r.group:r.group===id)),d=items.filter(r=>r.merit==='deferido').length,i=items.filter(r=>r.merit==='indeferido').length;return {id,name,items,d,i,ni:items.length-d-i,n:items.length};});
 let max=Math.max(1,...entries.map(x=>x.n)),den=isPct?Math.max(1,totalProg):max,zeroCount=entries.filter(x=>!x.n).length,shown=showZeroGroups?entries:entries.filter(x=>x.n>0||S.group===x.id);
 const btn=$('#toggleZeroGroups');
 if(btn){btn.hidden=zeroCount===0;btn.textContent=showZeroGroups?'Ocultar zerados':`Mostrar zerados (${zeroCount})`;}
 $('#groupChart').innerHTML=shown.length?shown.map(x=>{const txt=x.n?(isPct?`${pct(x.n,totalProg)} (${Math.round(100*x.d/x.n)}% D)`:`${x.d} D · ${x.i} I${x.ni?` · ${x.ni} NI`:''}`):'—';return `<button class="group-row ${S.group===x.id?'selected-row':''}" data-group="${esc(x.id)}" aria-label="${esc(x.name)}: ${x.d} deferidos, ${x.i} indeferidos e ${x.ni} não informados (${pct(x.n,totalProg)})" title="${x.n} de ${totalProg} (${pct(x.n,totalProg)}) · ${x.d} D · ${x.i} I${x.ni?` · ${x.ni} NI`:''}"><span>${esc(x.name)}</span><span class="result-track"><span class="part good" style="width:${x.d*100/den}%"></span><span class="part bad" style="width:${x.i*100/den}%"></span>${x.ni?`<span class="part" style="width:${x.ni*100/den}%;background:#e0ad40"></span>`:''}</span><b>${txt}</b></button>`;}).join(''):'<div class="empty-small">Nenhum grupo com registros neste recorte.</div>';
}"""
    assert old_group_chart in html
    html = html.replace(old_group_chart, new_group_chart, 1)

    old_results_chart = """function resultsChart(rows){
 let all=[['Horizontal','horizontal'],['Vertical','vertical'],['Tempo de Serviço','tempo'],['Outros benefícios','outros']],max=Math.max(1,...all.map(([l,k])=>rows.filter(r=>k==='tempo'?r.axis==='tempo':k==='outros'?r.axis==='outros':(r.modality||'').toLowerCase()===k).length)),isPct=metricMode.results==='pct';
 $('#resultsChart').innerHTML=all.map(([label,key])=>{let rr=rows.filter(r=>key==='tempo'?r.axis==='tempo':key==='outros'?r.axis==='outros':(r.modality||'').toLowerCase()===key),d=rr.filter(r=>r.merit==='deferido').length,i=rr.filter(r=>r.merit==='indeferido').length,den=isPct?Math.max(1,rr.length):max,txt=rr.length?(isPct?`${pct(d,rr.length)} D · ${pct(i,rr.length)} I`:`${d} D · ${i} I`):'sem dados';return `<div class="result-line"><span>${label}</span><div class="result-track"><button class="part good" data-series="${key}" data-merit="deferido" style="width:${d*100/den}%" aria-label="${label}: ${d} deferidos (${pct(d,rr.length)})" title="${label}: ${d} deferidos (${pct(d,rr.length)})" ${d?'':'disabled'}></button><button class="part bad" data-series="${key}" data-merit="indeferido" style="width:${i*100/den}%" aria-label="${label}: ${i} indeferidos (${pct(i,rr.length)})" title="${label}: ${i} indeferidos (${pct(i,rr.length)})" ${i?'':'disabled'}></button></div><b>${txt}</b></div>`;}).join('')+'<div class="result-key"><span><i class="good"></i>Deferidos</span><span><i class="bad"></i>Indeferidos</span></div>';
}"""
    new_results_chart = """function resultsChart(rows){
 if(isPublicAgg()){
  const pa=data.backend.series?.por_assunto||[],isPct=metricMode.results==='pct';
  const rowsPub=[['Horizontal','HORIZONTAL'],['Vertical','VERTICAL'],['Tempo de Serviço','TEMPO_SERVICO']].map(([label,ck])=>{
   const it=pa.find(x=>x.chave===ck)||{};
   return {label,ck,total:it.total??0,d:it.deferido,i:it.indeferido};
  });
  const max=Math.max(1,...rowsPub.map(x=>x.total||0));
  $('#resultsChart').innerHTML=rowsPub.map(x=>{
   const hasN=x.total!=null&&x.total>0,hasDI=hasN&&x.d!=null&&x.i!=null,den=isPct?Math.max(1,x.total):max;
   const txt=!hasN?'sem dados':hasDI?(isPct?`${pct(x.d,x.total)} D · ${pct(x.i,x.total)} I`:`${x.d} D · ${x.i} I`):`${x.total} (D/I < 5)`;
   const bars=hasDI?`<button class="part good" disabled style="width:${x.d*100/den}%"></button><button class="part bad" disabled style="width:${x.i*100/den}%"></button>`:(hasN?`<button class="part" disabled style="width:${x.total*100/den}%;background:#1265ef"></button>`:'');
   return `<div class="result-line"><span>${x.label}</span><div class="result-track">${bars}</div><b>${txt}</b></div>`;
  }).join('')+'<div class="result-key"><span><i class="good"></i>Deferidos</span><span><i class="bad"></i>Indeferidos</span><span><i style="background:#1265ef"></i>Total protegido (D/I &lt; 5)</span></div>';
  return;
 }
 let all=[['Horizontal','horizontal'],['Vertical','vertical'],['Tempo de Serviço','tempo']];
 if(rows.some(r=>r.axis==='progressao'&&r.modality!=='Vertical'&&r.modality!=='Horizontal'))all.push(['Modalidade pendente','sem_modalidade']);
 if(rows.some(r=>r.axis==='outros')||S.view==='outras'||S.axis==='outros')all.push(['Outros benefícios','outros']);
 const matchRow=(r,k)=>k==='tempo'?r.axis==='tempo':k==='outros'?r.axis==='outros':k==='sem_modalidade'?(r.axis==='progressao'&&r.modality!=='Vertical'&&r.modality!=='Horizontal'):(r.axis==='progressao'&&(r.modality||'').toLowerCase()===k);
 let max=Math.max(1,...all.map(([l,k])=>rows.filter(r=>matchRow(r,k)).length)),isPct=metricMode.results==='pct',hasAnyNi=rows.some(r=>r.merit!=='deferido'&&r.merit!=='indeferido');
 $('#resultsChart').innerHTML=all.map(([label,key])=>{let rr=rows.filter(r=>matchRow(r,key)),d=rr.filter(r=>r.merit==='deferido').length,i=rr.filter(r=>r.merit==='indeferido').length,ni=rr.length-d-i,den=isPct?Math.max(1,rr.length):max,txt=rr.length?(isPct?`${pct(d,rr.length)} D · ${pct(i,rr.length)} I${ni?` · ${pct(ni,rr.length)} NI`:''}`:`${d} D · ${i} I${ni?` · ${ni} NI`:''}`):'sem dados';return `<div class="result-line"><span>${label}</span><div class="result-track"><button class="part good" data-series="${key}" data-merit="deferido" style="width:${d*100/den}%" aria-label="${label}: ${d} deferidos (${pct(d,rr.length)})" title="${label}: ${d} deferidos (${pct(d,rr.length)})" ${d?'':'disabled'}></button><button class="part bad" data-series="${key}" data-merit="indeferido" style="width:${i*100/den}%" aria-label="${label}: ${i} indeferidos (${pct(i,rr.length)})" title="${label}: ${i} indeferidos (${pct(i,rr.length)})" ${i?'':'disabled'}></button>${ni?`<button class="part" data-series="${key}" data-merit="outro" style="width:${ni*100/den}%;background:#e0ad40" aria-label="${label}: ${ni} não informados (${pct(ni,rr.length)})" title="${label}: ${ni} não informados (${pct(ni,rr.length)})"></button>`:''}</div><b>${txt}</b></div>`;}).join('')+`<div class="result-key"><span><i class="good"></i>Deferidos</span><span><i class="bad"></i>Indeferidos</span>${hasAnyNi?'<span><i style="background:#e0ad40"></i>Não informado</span>':''}</div>`;
}"""
    assert old_results_chart in html
    html = html.replace(old_results_chart, new_results_chart, 1)

    # 5c-ter. Permitir clique nos cartoes Refeitos / Sem efeito (em modo autenticado) e bloquear clique KPI em modo publico
    old_kpi_click = """ $('#kpis').addEventListener('click',e=>{
  let b=e.target.closest('[data-card]');if(!b||b.disabled)return;
  const id=b.dataset.card;
  if(id==='deferidos'||id==='indeferidos'){const target=id==='deferidos'?'deferido':'indeferido';S.merit=S.merit===target?'':target;S.card='';resultPrev=null;}
  else if(id==='processes'){
   if(S.card==='processes'){S.card='';if(cardPrevMode){S.mode=cardPrevMode;cardPrevMode=null;}}
   else{cardPrevMode=S.mode;S.card='processes';S.mode='processo';}
  }
  else if(id==='resenhas'){S.card='';cardPrevMode=null;S.mode='resenha';toast('Lista agrupada por resenha.');}
  else{S.card='';cardPrevMode=null;S.merit='';resultPrev=null;}
  S.page=0;S.selected='';commitHistory();render();
 });"""
    new_kpi_click = """ $('#kpis').addEventListener('click',e=>{
  if(isPublicAgg())return;
  let b=e.target.closest('[data-card]');if(!b||b.disabled)return;
  const id=b.dataset.card;
  if(id==='deferidos'||id==='indeferidos'){const target=id==='deferidos'?'deferido':'indeferido';S.merit=S.merit===target?'':target;S.card='';resultPrev=null;}
  else if(id==='processes'){
   if(S.card==='processes'){S.card='';if(cardPrevMode){S.mode=cardPrevMode;cardPrevMode=null;}}
   else{cardPrevMode=S.mode;S.card='processes';S.mode='processo';}
  }
  else if(id==='refeitos'||id==='semEfeito'){S.card=S.card===id?'':id;cardPrevMode=null;S.merit='';resultPrev=null;}
  else if(id==='resenhas'){S.card='';cardPrevMode=null;S.mode='resenha';toast('Lista agrupada por resenha.');}
  else{S.card='';cardPrevMode=null;S.merit='';resultPrev=null;}
  S.page=0;S.selected='';commitHistory();render();
 });"""
    assert old_kpi_click in html
    html = html.replace(old_kpi_click, new_kpi_click, 1)

    old_card_chip = " if(S.card==='processes')chips.push(['card','Com processo identificado']);"
    new_card_chip = " if(S.card==='processes')chips.push(['card','Com processo identificado']);else if(S.card==='refeitos')chips.push(['card','Atos refeitos / retificados']);else if(S.card==='semEfeito')chips.push(['card','Atos tornados sem efeito']);"
    assert old_card_chip in html
    html = html.replace(old_card_chip, new_card_chip, 1)

    # 5c-bis. Adaptar levelChart() para exibir agregados públicos protegidos (limiar >= 5) quando não autenticado
    old_level_start = """function levelChart(){
 const baseRows=window.GEDIV_MODEL.dashboardModel(data,{...S,level:'',groupNames}).rows;"""
    new_level_start = """function levelChart(){
 if(isPublicAgg()){
  const bs=data.backend.series||{},lvs=bs.por_nivel_vertical||[],res=bs.resumo_nivel_vertical||{},isPct=metricMode.level==='pct';
  const totalV=Number(res.total_vertical||0),max=Math.max(1,...lvs.map(x=>Number(x.total||0))),den=isPct?Math.max(1,totalV):max;
  $('#levelCardTitle').textContent='Progressões Verticais (A–F)';
  $('#levelCardSub').textContent='Distribuição pública por nível de destino (limiar ≥ 5)';
  $('#levelChart').innerHTML=lvs.map(lv=>{
   const n=lv.total,d=lv.deferido,i=lv.indeferido,hasN=n!=null&&n>0,hasDI=hasN&&d!=null&&i!=null;
   const lbl=lv.nivel==='NAO_IDENTIFICADO'?'Não identificado':`Nível ${lv.nivel}`;
   const txt=n==null?'suprimido (< 5)':n===0?'—':hasDI?(isPct?`${pct(n,totalV)} (${Math.round(100*d/n)}% D)`:`${d} D · ${i} I`):`${n} (≥ 5)`;
   const bars=hasDI?`<span class="part good" style="width:${d*100/den}%"></span><span class="part bad" style="width:${i*100/den}%"></span>`:(hasN?`<span class="part" style="width:${n*100/den}%;background:#1265ef"></span>`:'');
   return `<button class="group-row" disabled aria-label="${esc(lbl)}: ${esc(txt)}"><span>${esc(lbl)}</span><span class="result-track">${bars}</span><b>${txt}</b></button>`;
  }).join('');
  $('#levelReconcileNote').textContent=`${res.classificados??'—'} classif. + ${res.nao_identificados??'—'} NI · ${res.total_vertical??'—'} Verticais · ${res.total_horizontal??'—'} Horiz. (agregado público)`;
  return;
 }
 const baseRows=window.GEDIV_MODEL.dashboardModel(data,{...S,level:'',groupNames}).rows;"""
    assert old_level_start in html
    html = html.replace(old_level_start, new_level_start, 1)

    # 5d. Proteger exportXlsx() e exportCsv() no modo público para zero vazamento e explicitar escopo
    old_exports = """function exportXlsx(){let m=model(),summary=[['Visão',views[S.view][1]],['Filtros',filterText()],['Cobertura',data.meta.coverage],['Atualização',data.meta.automation],[],['Indicador','Valor'],...Object.entries(m.metrics)],list=[['Resenha / processo','Assunto','Resultado','Data','Quantidade'],...exportRows()];exp.download(exp.xlsx({'Resumo':summary,'Visão selecionada':list,'Decisões':decisionRows()}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-visao-selecionada.xlsx');toast('Planilha da visão selecionada gerada.');}
function exportCsv(){exp.download(exp.csv(decisionRows()),'text/csv;charset=utf-8','GEDIV-decisoes-filtradas.csv');toast('Lista filtrada gerada.');}"""
    new_exports = """function buildServerExportUrl(formato){
 const q=new URLSearchParams({formato,escopo:S.validation==='conferido'?'conferido':'pendente'});
 if(S.from)q.set('inicio',S.from);
 if(S.to)q.set('fim',S.to);
 if(S.axis==='progressao')q.set('eixo','PROGRESSAO');
 else if(S.axis==='tempo')q.set('eixo','TEMPO_SERVICO');
 if(S.modality==='Vertical')q.set('modalidade','VERTICAL');
 else if(S.modality==='Horizontal')q.set('modalidade','HORIZONTAL');
 if(S.group&&!S.group.startsWith('PENDENTE:'))q.set('grupo',S.group);
 const cats=(S.category||[]).filter(c=>/^TS-0[1-7]$/.test(c));
 if(cats.length)q.set('subcategoria',cats.join(','));
 if(S.merit==='deferido')q.set('resultado','DEFERIDO');
 else if(S.merit==='indeferido')q.set('resultado','INDEFERIDO');
 if(S.query)q.set('busca',S.query);
 if(S.card==='processes')q.set('cartao','processos');
 else if(S.card==='semEfeito')q.set('cartao','sem_efeito');
 else if(S.card)q.set('cartao',S.card);
 return '/api/exportar?'+q.toString();
}
async function serverAuditedExport(formato,fallbackFn){
 try{
  const r=await fetch(buildServerExportUrl(formato),{cache:'no-store',credentials:'same-origin',headers:window.GEDIV_AUTH.headers()});
  if(r.status===401||r.status===403){if(typeof handleAuthExpiry==='function')await handleAuthExpiry('Sessão expirada ou encerrada. Faça login novamente.');return;}
  if(!r.ok)throw new Error('HTTP '+r.status);
  const blob=await r.blob();
  const cd=r.headers.get('Content-Disposition')||'';
  const m=cd.match(/filename="?([^";]+)"?/i);
  const fname=m?m[1]:(`GEDIV-exportacao.${formato}`);
  const a=document.createElement('a');
  const objUrl=URL.createObjectURL(blob);
  a.href=objUrl;a.download=fname;
  document.body.appendChild(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(objUrl),2000);
  toast(`Exportação oficial (.${formato}) concluída e registrada na auditoria.`);
 }catch(err){
  if(typeof fallbackFn==='function')fallbackFn();
  else toast('Falha ao exportar do servidor: '+err.message);
 }
}
function exportXlsx(){
 let isAuth=!!data.backend?.autenticado,m=model();
 if(!isAuth&&isPublicAgg()){
  const bi=data.backend.indicadores||{},bs=data.backend.series||{};
  const pubSummary=[['Visão',views[S.view][1]],['Escopo','Público (somente agregados protegidos ≥ 5)'],['Filtros',filterText()],['Cobertura',data.meta.coverage],[],['Indicador','Valor (≥ 5)'],...Object.entries(bi).map(([k,v])=>[k,v==null?'Suprimido (< 5)':v])];
  const pubAssunto=[['Assunto','Total','Deferidos','Indeferidos'],...(bs.por_assunto||[]).map(x=>[x.rotulo||x.chave,x.total??'Suprimido (< 5)',x.deferido??'Suprimido (< 5)',x.indeferido??'Suprimido (< 5)'])];
  const pubMensal=[['Mês','Total','Vertical','Horizontal','Tempo de Serviço'],...(bs.por_data||[]).map(x=>[x.data,x.total??'Suprimido (< 5)',x.vertical??'Suprimido (< 5)',x.horizontal??'Suprimido (< 5)',x.tempo??'Suprimido (< 5)'])];
  exp.download(exp.xlsx({'Resumo público':pubSummary,'Por assunto':pubAssunto,'Série mensal':pubMensal}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-resumo-publico.xlsx');
  toast('Resumo agregado público gerado (dados individuais protegidos).');return;
 }
 let summary=[['Visão',views[S.view][1]],['Escopo',isAuth?m.label:'Público (somente agregados)'],['Filtros',filterText()],['Cobertura',data.meta.coverage],[],['Indicador','Valor'],...Object.entries(m.metrics)];
 if(!isAuth){
  exp.download(exp.xlsx({'Resumo':summary}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-resumo-publico.xlsx');
  toast('Resumo agregado gerado (dados individuais protegidos).');return;
 }
 const localFallback=()=>{
  let list=[['Resenha / processo','Assunto','Resultado','Data','Quantidade'],...exportRows()];
  exp.download(exp.xlsx({'Resumo':summary,'Visão selecionada':list,'Decisões':decisionRows()}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-visao-selecionada.xlsx');
  toast('Planilha da visão selecionada gerada.');
 };
 if(!isStaticHost()){serverAuditedExport('xlsx',localFallback);return;}
 localFallback();
}
function exportCsv(){
 if(!data.backend?.autenticado){toast('Lista individual (.csv) disponível apenas após login gerencial.');return;}
 const localFallback=()=>{exp.download(exp.csv(decisionRows()),'text/csv;charset=utf-8','GEDIV-decisoes-filtradas.csv');toast('Lista filtrada gerada.');};
 if(!isStaticHost()){serverAuditedExport('csv',localFallback);return;}
 localFallback();
}"""
    assert old_exports in html
    html = html.replace(old_exports, new_exports, 1)

    old_export_png = "function exportPng(){let m=model();exp.png({title:views[S.view][1],filters:filterText(),metrics:m.metrics,records:exportRows(),coverage:data.meta.coverage});toast('Resumo da visão gerado.');}"
    new_export_png = """function exportPng(){
 if(isPublicAgg()){
  const bi=data.backend.indicadores||{};
  const pubM={processes:bi.processos??null,resenhas:bi.resenhas??null,decisions:bi.decisoes??null,deferidos:bi.deferidos??null,indeferidos:bi.indeferidos??null,refeitos:bi.refeitos??null,semEfeito:bi.sem_efeito??null};
  exp.png({title:views[S.view][1]+' · Público',filters:'Consulta pública · agregados protegidos (limiar ≥ 5)',metrics:pubM,records:[],coverage:data.meta.coverage});
  toast('Resumo visual público gerado (dados individuais protegidos).');return;
 }
 let m=model();exp.png({title:views[S.view][1],filters:filterText(),metrics:m.metrics,records:exportRows(),coverage:data.meta.coverage});toast('Resumo da visão gerado.');
}"""
    assert old_export_png in html
    html = html.replace(old_export_png, new_export_png, 1)

    old_print_fn = " function buildPrintReport(){let m=model();$('#printReport').innerHTML='<h3>Registros da visão selecionada</h3><p>'+esc(filterText())+'</p><table><thead><tr><th>Data</th><th>Resenha</th><th>Processo</th><th>Servidor</th><th>Grupo</th><th>Assunto</th><th>Nível (A–F)</th><th>Resultado</th></tr></thead><tbody>'+m.rows.map(r=>'<tr><td>'+esc(dt(r.date))+'</td><td>'+esc(r.resenha)+'</td><td>'+esc(r.process||'Não transcrito')+'</td><td>'+esc(r.server)+'</td><td>'+esc(r.axis==='progressao'?labelGroup(r.group):'—')+'</td><td>'+esc(labelRow(r))+'</td><td>'+esc(r.levelTo?`${r.levelLabel} (${r.levelTransition})`:(r.levelLabel||'—'))+'</td><td>'+esc(r.merit)+'</td></tr>').join('')+'</tbody></table>';}"
    new_print_fn = """ function buildPrintReport(){
  if(isPublicAgg()){
   const pa=data.backend.series?.por_assunto||[],fmtP=v=>v==null?'Suprimido (< 5)':String(v);
   $('#printReport').innerHTML='<h3>Resumo público protegido (limiar ≥ 5)</h3><p>'+esc(data.meta.coverage||'')+'</p><table><thead><tr><th>Assunto</th><th>Total</th><th>Deferidos</th><th>Indeferidos</th></tr></thead><tbody>'+pa.map(x=>'<tr><td>'+esc(x.rotulo||x.chave)+'</td><td>'+esc(fmtP(x.total))+'</td><td>'+esc(fmtP(x.deferido))+'</td><td>'+esc(fmtP(x.indeferido))+'</td></tr>').join('')+'</tbody></table>';
   return;
  }
  let m=model();$('#printReport').innerHTML='<h3>Registros da visão selecionada</h3><p>'+esc(filterText())+'</p><table><thead><tr><th>Data</th><th>Resenha</th><th>Processo</th><th>Servidor</th><th>Grupo</th><th>Assunto</th><th>Nível (A–F)</th><th>Resultado</th></tr></thead><tbody>'+m.rows.map(r=>'<tr><td>'+esc(dt(r.date))+'</td><td>'+esc(r.resenha)+'</td><td>'+esc(r.process||'Não transcrito')+'</td><td>'+esc(r.server)+'</td><td>'+esc(r.axis==='progressao'?labelGroup(r.group):'—')+'</td><td>'+esc(labelRow(r))+'</td><td>'+esc(r.levelTo?`${r.levelLabel} (${r.levelTransition})`:(r.levelLabel||'—'))+'</td><td>'+esc(r.merit)+'</td></tr>').join('')+'</tbody></table>';
 }"""
    assert old_print_fn in html
    html = html.replace(old_print_fn, new_print_fn, 1)

    # 5d-bis. Resumo tabular público em openFullTableModal() + UX de datas, filtros honestos no público, pieSelect e Voltar determinístico
    old_full_modal_start = """function openFullTableModal(){
 const allRows=model().rows;"""
    new_full_modal_start = """function openFullTableModal(){
 if(isPublicAgg()){
  const bs=data.backend.series||{},bi=data.backend.indicadores||{};
  const fmtP=v=>v==null?'Suprimido (< 5)':String(v);
  const tbAss=(bs.por_assunto||[]).map(x=>`<tr><td><b>${esc(x.rotulo||x.chave)}</b></td><td>${esc(fmtP(x.total))}</td><td>${esc(fmtP(x.deferido))}</td><td>${esc(fmtP(x.indeferido))}</td></tr>`).join('');
  const tbGrp=(bs.por_grupo||[]).map(x=>`<tr><td>${esc(labelGroup(x.grupo))}</td><td>${esc(fmtP(x.total))}</td><td>${esc(fmtP(x.vertical))}</td><td>${esc(fmtP(x.horizontal))}</td></tr>`).join('');
  const tbSub=(bs.por_subcategoria||[]).map(x=>`<tr><td>${esc(x.codigo)} · ${esc(x.nome)}</td><td>${esc(fmtP(x.total))}</td><td>${esc(fmtP(x.deferido))}</td><td>${esc(fmtP(x.indeferido))}</td></tr>`).join('');
  const tbMes=(bs.por_data||[]).map(x=>`<tr><td class="nowrap">${esc(x.data)}</td><td>${esc(fmtP(x.total))}</td><td>${esc(fmtP(x.vertical))}</td><td>${esc(fmtP(x.horizontal))}</td><td>${esc(fmtP(x.tempo))}</td></tr>`).join('');
  const body=`<div class="reconcile-note" style="margin-top:0;margin-bottom:12px"><b>Consulta pública (agregados protegidos ≥ 5):</b> total de <b>${esc(fmtP(bi.decisoes))}</b> decisões conferidas em <b>${esc(fmtP(bi.resenhas))}</b> resenhas e <b>${esc(fmtP(bi.processos))}</b> processos. Registros nominais estão disponíveis apenas após login gerencial.</div>
  <h3 style="margin:10px 0 6px;font-size:13px">Distribuição por assunto</h3>
  <div class="table-scroll"><table class="dialog-table"><thead><tr><th>Assunto</th><th>Total</th><th>Deferidos</th><th>Indeferidos</th></tr></thead><tbody>${tbAss||'<tr><td colspan="4">Sem agregados públicos.</td></tr>'}</tbody></table></div>
  <h3 style="margin:14px 0 6px;font-size:13px">Progressão por grupo (≥ 5)</h3>
  <div class="table-scroll"><table class="dialog-table"><thead><tr><th>Grupo</th><th>Total</th><th>Vertical</th><th>Horizontal</th></tr></thead><tbody>${tbGrp||'<tr><td colspan="4">Nenhum grupo acima do limiar público.</td></tr>'}</tbody></table></div>
  <h3 style="margin:14px 0 6px;font-size:13px">Tempo de Serviço (TS-01 a TS-07)</h3>
  <div class="table-scroll"><table class="dialog-table"><thead><tr><th>Serviço</th><th>Total</th><th>Deferidos</th><th>Indeferidos</th></tr></thead><tbody>${tbSub||'<tr><td colspan="4">Sem dados.</td></tr>'}</tbody></table></div>
  <h3 style="margin:14px 0 6px;font-size:13px">Série mensal</h3>
  <div class="table-scroll"><table class="dialog-table"><thead><tr><th>Mês</th><th>Total</th><th>Vertical</th><th>Horizontal</th><th>Tempo</th></tr></thead><tbody>${tbMes||'<tr><td colspan="5">Sem série mensal.</td></tr>'}</tbody></table></div>`;
  openDialog('Resumo tabular público (agregados protegidos)',body,{wide:true});
  return;
 }
 const allRows=model().rows;"""
    assert old_full_modal_start in html
    html = html.replace(old_full_modal_start, new_full_modal_start, 1)

    old_sync_dates_warn = """ const badDates=!!(S.from&&S.to&&S.from>S.to);
 const warn=$('#dateWarning');
 warn.hidden=!badDates;
 if(badDates)warn.innerHTML='<span>Data inicial maior que a final.</span><button type="button" id="swapDates">Inverter</button>';"""
    new_sync_dates_warn = """ const pubMode=isPublicAgg(),pubTip='Disponível após login gerencial';
 ['#group','#merit','#search','#byResenha','#byProcess'].forEach(sel=>{const el=$(sel);if(el){el.disabled=pubMode;if(pubMode)el.title=pubTip;else el.removeAttribute('title');}});
 $$('#serviceFilters button').forEach(b=>{b.disabled=pubMode;if(pubMode)b.title=pubTip;});
 $$('#datePresets button').forEach(b=>{const dailyOnly=b.dataset.preset==='7d'||b.dataset.preset==='30d';b.disabled=pubMode&&dailyOnly;if(pubMode&&dailyOnly)b.title='Recorte diário disponível após login gerencial (agregado público é mensal)';else b.removeAttribute('title');});
 const badDates=!!(S.from&&S.to&&S.from>S.to);
 const outOfRange=!badDates&&!!minDate&&!!maxDate&&((S.from&&S.from>maxDate)||(S.to&&S.to<minDate));
 const warn=$('#dateWarning');
 warn.hidden=!badDates&&!outOfRange;
 if(badDates)warn.innerHTML='<span>Data inicial maior que a final.</span><button type="button" id="swapDates">Inverter</button>';
 else if(outOfRange)warn.innerHTML=`<span>Período fora da cobertura (${dt(minDate)} a ${dt(maxDate)}).</span><button type="button" id="clampDates">Ajustar à base</button>`;"""
    assert old_sync_dates_warn in html
    html = html.replace(old_sync_dates_warn, new_sync_dates_warn, 1)

    old_show_pending_bind = """ $('#showPending').addEventListener('click',()=>{if(S.validation!=='pendente'){S.validation='pendente';S.card='';S.page=0;S.selected='';commitHistory();render();}openFullTableModal();});"""
    new_show_pending_bind = """ $('#showPending').addEventListener('click',()=>{if(!data.backend?.autenticado){openLoginModal();return;}if(S.validation!=='pendente'){S.validation='pendente';S.card='';S.page=0;S.selected='';commitHistory();render();}openFullTableModal();});"""
    assert old_show_pending_bind in html
    html = html.replace(old_show_pending_bind, new_show_pending_bind, 1)

    old_date_warn_bind = """ $('#dateWarning').addEventListener('click',e=>{if(e.target.closest('#swapDates')){[S.from,S.to]=[S.to,S.from];S.page=0;timelinePrev=null;commitHistory();render();}});"""
    new_date_warn_bind = """ $('#dateWarning').addEventListener('click',e=>{
  if(e.target.closest('#swapDates')){[S.from,S.to]=[S.to,S.from];S.page=0;timelinePrev=null;commitHistory();render();}
  else if(e.target.closest('#clampDates')&&minDate&&maxDate){S.from=minDate;S.to=maxDate;S.page=0;timelinePrev=null;commitHistory();render();}
 });
 function applyDraftDates(){
  S.from=$('#from').value||'';S.to=$('#to').value||'';
  S.card='';S.page=0;timelinePrev=null;beforeToday=null;
  commitHistory();render();
 }
 $('#applyDates')?.addEventListener('click',applyDraftDates);
 $('#cancelDates')?.addEventListener('click',()=>{$('#from').value=S.from||'';$('#to').value=S.to||'';toast('Alteração de período descartada.');});
 $('#clearDates')?.addEventListener('click',()=>{S.from='';S.to='';$('#from').value='';$('#to').value='';S.page=0;timelinePrev=null;beforeToday=null;commitHistory();render();});
 ['#from','#to'].forEach(sel=>$(sel)?.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();applyDraftDates();}}));"""
    assert old_date_warn_bind in html
    html = html.replace(old_date_warn_bind, new_date_warn_bind, 1)

    old_filter_loop = """ for(const id of ['axis','modality','group','merit','from','to'])$('#'+id).addEventListener('change',e=>{
  S[id]=e.target.value;S.card='';S.page=0;
  if(id==='axis'||id==='modality'||id==='group'){S.level='';inducedByLevel=null;}
  if(id==='axis'){S.category=[];S.modality='';S.group='';timelinePrev=null;resultPrev=null;if(S.axis==='tempo'&&(S.view==='vertical'||S.view==='horizontal'||S.view==='outras'))S.view='geral';else if(S.axis==='progressao'&&(S.view==='tempo'||S.view==='outras'))S.view='geral';else if(S.axis==='outros'&&(S.view==='vertical'||S.view==='horizontal'||S.view==='tempo'))S.view='geral';}
  if(id==='modality'){timelinePrev=null;resultPrev=null;if(S.modality){S.axis='progressao';S.category=[];if(S.view==='tempo'||S.view==='outras')S.view='geral';else if(S.view==='vertical'&&S.modality==='Horizontal')S.view='horizontal';else if(S.view==='horizontal'&&S.modality==='Vertical')S.view='vertical';}}
  if(id==='group'&&S.group){S.axis='progressao';S.category=[];if(S.view==='tempo'||S.view==='outras')S.view='geral';}
  if(id==='merit')resultPrev=null;
  if(id==='from'||id==='to'){timelinePrev=null;beforeToday=null;}
  commitHistory();render();
 });"""
    new_filter_loop = """ for(const id of ['axis','modality','group','merit'])$('#'+id).addEventListener('change',e=>{
  if(isPublicAgg()&&(id==='axis'||id==='modality')){
   const v=e.target.value;
   if(id==='axis'){nav(v==='tempo'?'tempo':v==='outros'?'outras':'geral');return;}
   if(id==='modality'){nav(v==='Vertical'?'vertical':v==='Horizontal'?'horizontal':'geral');return;}
  }
  S[id]=e.target.value;S.card='';S.page=0;
  if(id==='axis'||id==='modality'||id==='group'){S.level='';inducedByLevel=null;}
  if(id==='axis'){S.category=[];S.modality='';S.group='';timelinePrev=null;resultPrev=null;if(S.axis==='tempo'&&(S.view==='vertical'||S.view==='horizontal'||S.view==='outras'))S.view='geral';else if(S.axis==='progressao'&&(S.view==='tempo'||S.view==='outras'))S.view='geral';else if(S.axis==='outros'&&(S.view==='vertical'||S.view==='horizontal'||S.view==='tempo'))S.view='geral';}
  if(id==='modality'){timelinePrev=null;resultPrev=null;if(S.modality){S.axis='progressao';S.category=[];if(S.view==='tempo'||S.view==='outras')S.view='geral';else if(S.view==='vertical'&&S.modality==='Horizontal')S.view='horizontal';else if(S.view==='horizontal'&&S.modality==='Vertical')S.view='vertical';}}
  if(id==='group'&&S.group){S.axis='progressao';S.category=[];if(S.view==='tempo'||S.view==='outras')S.view='geral';}
  if(id==='merit')resultPrev=null;
  commitHistory();render();
 });"""
    assert old_filter_loop in html
    html = html.replace(old_filter_loop, new_filter_loop, 1)

    old_pie_select = """ function pieSelect(b){
  let kind=b.dataset.kind,key=b.dataset.key;
  if(kind==='axis'){nav(key==='outros'?'outras':key);return;}"""
    new_pie_select = """ function pieSelect(b){
  let kind=b.dataset.kind,key=b.dataset.key;
  if(kind==='axis'){
   if(key==='progressao'){S.axis='progressao';S.modality='';S.view='geral';S.card='';S.page=0;commitHistory();render();return;}
   nav(key==='outros'?'outras':key);return;
  }
  if(isPublicAgg()){toast('Detalhamento por grupo ou serviço disponível após login gerencial.');return;}"""
    assert old_pie_select in html
    html = html.replace(old_pie_select, new_pie_select, 1)

    old_back_bind = """ $('#backView').addEventListener('click',()=>{
  if(H.index<=0)return;
  try{if(typeof history.state?.gedivIdx==='number'&&history.state.gedivIdx>0){history.back();return;}}catch{}
  H.index--;applySnapshot(H.entries[H.index]);render();
 });"""
    new_back_bind = """ $('#backView').addEventListener('click',()=>{
  if(H.index<=0)return;
  H.index--;
  const snap=H.entries[H.index];
  applySnapshot(snap);
  try{history.replaceState({gedivIdx:H.index,snap},'',buildHashUrl());}catch{}
  render();
 });"""
    assert old_back_bind in html
    html = html.replace(old_back_bind, new_back_bind, 1)

    old_esc_bind = """ document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#downloadMenu').hidden){e.preventDefault();closeDownloadMenu(true);}});"""
    new_esc_bind = """ document.addEventListener('keydown',e=>{
  if(e.key!=='Escape')return;
  if(!$('#downloadMenu').hidden){e.preventDefault();closeDownloadMenu(true);}
  const am=$('#delicateAcctMenu');
  if(am&&!am.hidden){e.preventDefault();am.hidden=true;$('#delicateAcctBtn')?.setAttribute('aria-expanded','false');$('#delicateAcctBtn')?.focus();}
 });"""
    assert old_esc_bind in html
    html = html.replace(old_esc_bind, new_esc_bind, 1)

    old_hint_line = """ $('#dateRangeHint').textContent=minDate&&maxDate?`Base disponível: ${dt(minDate)} a ${dt(maxDate)}`:'';"""
    new_hint_line = """ $('#dateRangeHint').textContent=minDate&&maxDate?(isPublicAgg()?`Base pública mensal: ${minDate.slice(5,7)}/${minDate.slice(0,4)} a ${maxDate.slice(5,7)}/${maxDate.slice(0,4)} (limiar ≥ 5)`:`Base disponível: ${dt(minDate)} a ${dt(maxDate)}`):'';"""
    assert old_hint_line in html
    html = html.replace(old_hint_line, new_hint_line, 1)

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
  ${r.preliminaryReview?`<div class="prelim-note"><b>Nota preliminar:</b> ${esc(r.preliminaryReview)}</div>`:''}
  ${isAuth&&/^[0-9a-f]{20}$/.test(r.act||r.resenha_id||'')?`<div id="docActAuditBox" class="reconcile-note" style="margin-top:10px">Consultando histórico do ato (${esc(r.act||r.resenha_id)})…</div>`:''}`;
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
 const actId=r.act||r.resenha_id||'';
 if(isAuth&&/^[0-9a-f]{20}$/.test(actId))loadActAuditBox(actId,r);
}
async function loadActAuditBox(actId,r){
 const box=$('#docActAuditBox');if(!box)return;
 try{
  const resp=await fetch('/api/ato/'+encodeURIComponent(actId),{cache:'no-store',credentials:'same-origin',headers:window.GEDIV_AUTH.headers({Accept:'application/json'})});
  if(resp.status===401||resp.status===403){await handleAuthExpiry('Sessão expirada ou encerrada. Faça login novamente.');return;}
  if(!resp.ok)throw new Error('HTTP '+resp.status);
  const d=await resp.json();
  const corrList=d.correcoes||[],confList=d.conflitos||[],trilhaList=(d.trilha||[]).slice(0,10),decs=d.decisoes||[];
  box.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">
    <b>Histórico documental do ato (${esc(actId)}) · ${decs.length} decisão(ões)</b>
    <span style="display:flex;gap:6px;flex-wrap:wrap">
     <button type="button" id="docReviewWholeActBtn" class="sel-btn-sec" style="min-height:26px;padding:3px 8px;font-size:11px">Conferir ato completo</button>
     <button type="button" id="docCorrectActClassBtn" class="sel-btn-sec" style="min-height:26px;padding:3px 8px;font-size:11px">Corrigir classificação do ato</button>
    </span>
   </div>
   <div style="font-size:11px;line-height:1.45">
    <div><b>Correções de campos (${corrList.length}):</b> ${corrList.length?corrList.map(c=>`<code>${esc(c.campo)}</code>: ${esc(c.valor_anterior)} → <b>${esc(c.valor_corrigido)}</b> (${esc(c.autor)} · ${esc(String(c.momento||'').slice(0,16).replace('T',' '))})`).join(' | '):'nenhuma correção registrada.'}</div>
    <div style="margin-top:4px"><b>Conflitos abertos (${confList.length}):</b> ${confList.length?confList.map(c=>`#${esc(c.id)} <code>${esc(c.campo)}</code> (${esc(c.valor_vigente)} vs ${esc(c.valor_proposto)})`).join(', ')+' · <button type="button" id="docOpenConflictsBtn" class="pdf-link" style="border:0;background:none;padding:0">Resolver conflitos →</button>':'nenhum conflito aberto neste ato.'}</div>
    <div style="margin-top:4px"><b>Trilha de auditoria (${trilhaList.length}):</b> ${trilhaList.length?trilhaList.map(t=>`<span><b>${esc(t.acao)}</b> por ${esc(t.autor)} em ${esc(String(t.momento||'').slice(0,16).replace('T',' '))}${t.justificativa?` (<i>${esc(t.justificativa)}</i>)`:''}</span>`).join(' · '):'nenhum evento de revisão registrado.'}</div>
   </div>`;
  $('#docReviewWholeActBtn')?.addEventListener('click',()=>{$('#docModal').close();openReviewModal('ato',[{...r,id:actId}]);});
  $('#docCorrectActClassBtn')?.addEventListener('click',()=>{$('#docModal').close();openReviewModal('ato_classificacao',[{...r,id:actId,ato:d.ato}]);});
  $('#docOpenConflictsBtn')?.addEventListener('click',()=>{$('#docModal').close();openConflictsDialog();});
 }catch(err){box.textContent='Não foi possível carregar o histórico do ato: '+err.message;}
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
    new_refresh = """async function handleAuthExpiry(msg){
 window.GEDIV_AUTH.clear();
 ['#reviewDialog','#conflictsDialog','#auditDialog','#batchDialog','#docModal'].forEach(sel=>{const d=$(sel);if(d?.open)d.close();});
 await refreshData();
 S.validation='conferido';S.page=0;S.selected='';renderMeta();render();
 const notice=msg||'Sessão expirada ou encerrada. Faça login novamente.';
 $('#connectionState').textContent=notice;
 toast(notice);
}
async function refreshData(){
 if(isStaticHost()){toast('Publicação estática no GitHub Pages: os dados são atualizados por novo lote publicado.');return;}
 const button=$('#refreshData'),label=button.textContent,revision=data.dashboard?.revision,wasAuth=!!data.backend?.autenticado;
 button.disabled=true;button.textContent='Sincronizando…';
 try{
  const next=await window.GEDIV_FETCH_DATA();
  enrichVerticalLevels(next.rows);
  Object.assign(data,next);
  if(wasAuth&&!data.backend?.autenticado){
   window.GEDIV_AUTH.clear();
   S.validation='conferido';S.page=0;S.selected='';render();
   $('#connectionState').textContent='Sessão expirada ou encerrada. Faça login novamente.';
   toast('Sessão expirada ou encerrada. Faça login novamente.');
   return;
  }
  if(!['pendente','conferido','rejeitado'].includes(S.validation)||(!data.backend?.autenticado&&S.validation!=='conferido')){
   S.validation=data.dashboard?.defaultScope||'conferido';
  }
  S.page=0;S.selected='';render();
  $('#connectionState').textContent='Base sincronizada · '+data.rows.length+' registro(s) carregado(s) · '+(data.meta?.pendentes||0)+' em conferência · '+(revision===data.dashboard.revision?'sem alterações':'dados atualizados');
 }catch(error){$('#connectionState').textContent='Falha ao sincronizar. A base anterior de '+data.rows.length+' registros foi mantida. '+error.message;}
 finally{button.disabled=false;button.textContent=label;}
}
async function openConflictsDialog(){
 if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}
 const dlg=$('#conflictsDialog'),sumBox=$('#conflictsSummaryBox'),wrap=$('#conflictsTableWrap'),st=$('#conflictsStatus');
 st.textContent='';st.classList.remove('is-error');
 if(!dlg.open){
  sumBox.textContent='Carregando conflitos abertos e diagnóstico de integridade…';
  wrap.innerHTML='';
  dlg.showModal();
 }
 try{
  const r=await fetch('/api/conflitos',{cache:'no-store',credentials:'same-origin',headers:window.GEDIV_AUTH.headers({Accept:'application/json'})});
  if(r.status===401||r.status===403){await handleAuthExpiry('Sessão expirada ou encerrada. Faça login novamente.');return;}
  if(!r.ok)throw new Error('HTTP '+r.status);
  const d=await r.json();
  const confs=d.conflitos||[],orfaos=d.vinculos_orfaos||[],desat=Number(d.classificacoes_desatualizadas)||0;
  sumBox.innerHTML=`<b>Diagnóstico de reconciliação:</b> <b>${confs.length}</b> conflito(s) aberto(s) · <b>${orfaos.length}</b> vínculo(s) órfão(s) · <b>${desat}</b> classificação(ões) desatualizada(s).`;
  if(!confs.length){
   wrap.innerHTML='<div class="empty-small">Nenhum conflito aberto na base no momento.</div>';
   return;
  }
  wrap.innerHTML=`<table class="dialog-table is-cards-sm"><thead><tr><th>ID</th><th>Alvo</th><th>Campo</th><th>Valor vigente</th><th>Valor proposto</th><th>Origem</th><th>Ação auditada</th></tr></thead><tbody>${confs.map(c=>`<tr><td class="nowrap" data-label="ID">#${esc(c.id)}</td><td class="nowrap" data-label="Alvo">${esc(c.alvo_tipo)} · <code>${esc(String(c.alvo_id||'').slice(0,12))}</code></td><td class="nowrap" data-label="Campo"><code>${esc(c.campo)}</code></td><td data-label="Vigente"><b>${esc(c.valor_vigente)}</b></td><td data-label="Proposto"><b>${esc(c.valor_proposto)}</b></td><td class="nowrap" data-label="Origem">${esc(c.origem||'releitura')}</td><td class="nowrap" data-label="Ação"><button type="button" class="sel-btn-sec" style="min-height:26px;padding:3px 8px;margin-right:4px" data-resolve-conflict="${esc(c.id)}" data-decision="MANTER">Manter vigente</button><button type="button" class="sel-btn-pri" style="min-height:26px;padding:3px 8px;flex:none" data-resolve-conflict="${esc(c.id)}" data-decision="ACEITAR">Aceitar proposto</button></td></tr>`).join('')}</tbody></table>`;
  $$('#conflictsTableWrap [data-resolve-conflict]').forEach(btn=>btn.addEventListener('click',async()=>{
   const cId=Number(btn.dataset.resolveConflict),dec=btn.dataset.decision;
   const just=($('#conflictJustificationInput')?.value||'').trim();
   const confFonte=!!$('#conflictConfirmSourceInput')?.checked;
   st.classList.remove('is-error');
   if(just.length<5){st.textContent='Informe a justificativa técnica (mínimo 5 caracteres) antes de resolver o conflito.';st.classList.add('is-error');return;}
   if(!confFonte){st.textContent='Confirme a consulta ao PDF oficial (confirma_fonte) para resolver o conflito.';st.classList.add('is-error');return;}
   btn.disabled=true;st.textContent='Registrando resolução do conflito #'+cId+'…';
   try{
    const usr=window.GEDIV_AUTH.user();
    const resp=await fetch('/api/revisao',{method:'POST',credentials:'same-origin',headers:window.GEDIV_AUTH.headers({'Content-Type':'application/json'}),body:JSON.stringify({alvo:'conflito',id:cId,decisao:dec,responsavel:usr?`${usr.nome} (${usr.usuario})`:'Revisor GEDIV',justificativa:just,confirma_fonte:confFonte})});
    if(resp.status===401){await handleAuthExpiry('Sessão expirada ou encerrada. Faça login novamente.');return;}
    const jr=await resp.json().catch(()=>({}));
    if(!resp.ok)throw new Error(jr.erro||'Falha ao resolver conflito.');
    toast('Conflito #'+cId+' resolvido ('+dec+') e registrado em auditoria.');
    await openConflictsDialog();
    await refreshData();
   }catch(err){st.textContent=err.message;st.classList.add('is-error');btn.disabled=false;}
  }));
 }catch(err){sumBox.textContent='Não foi possível carregar os conflitos: '+err.message;}
}
async function openAuditDialog(){
 if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}
 const dlg=$('#auditDialog'),note=$('#auditScopeNote'),wrap=$('#auditTableWrap'),admBox=$('#auditAdminActions'),pubSt=$('#publishSnapshotStatus');
 note.textContent='Carregando trilha de auditoria…';wrap.innerHTML='';
 if(pubSt)pubSt.textContent='';
 if(admBox)admBox.hidden=!data.backend?.ehAdmin;
 if(!dlg.open)dlg.showModal();
 try{
  const r=await fetch('/api/auditoria',{cache:'no-store',credentials:'same-origin',headers:window.GEDIV_AUTH.headers({Accept:'application/json'})});
  if(r.status===401){await handleAuthExpiry('Sessão expirada ou encerrada. Faça login novamente.');return;}
  const d=await r.json().catch(()=>({}));
  if(!r.ok){note.textContent=d.erro||('Acesso negado à auditoria (HTTP '+r.status+').');return;}
  const trilha=d.trilha||[];
  note.innerHTML=d.escopo==='global'?`<b>Escopo global (Administração):</b> exibindo ${trilha.length} evento(s) auditado(s) de todas as contas.`:`<b>Escopo próprio (Gerência):</b> exibindo ${trilha.length} evento(s) realizados exclusivamente pela sua conta nominal.`;
  if(!trilha.length){wrap.innerHTML='<div class="empty-small">Nenhum evento de auditoria encontrado neste escopo.</div>';return;}
  wrap.innerHTML=`<table class="dialog-table is-cards-sm"><thead><tr><th class="nowrap">Momento</th><th>Autor</th><th class="nowrap">Ação</th><th class="nowrap">Alvo</th><th>Justificativa / Detalhe</th></tr></thead><tbody>${trilha.map(t=>`<tr><td class="nowrap" data-label="Momento">${esc(String(t.momento||'').slice(0,19).replace('T',' '))}</td><td data-label="Autor"><b>${esc(t.autor||'—')}</b></td><td class="nowrap" data-label="Ação"><span class="badge t">${esc(t.acao)}</span></td><td class="nowrap" data-label="Alvo">${esc(t.alvo_tipo||'')} · <code>${esc(String(t.alvo_id||'').slice(0,18))}</code></td><td data-label="Justificativa">${esc(t.justificativa||'—')}</td></tr>`).join('')}</tbody></table>`;
 }catch(err){note.textContent='Falha ao carregar auditoria: '+err.message;}
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
 if($('#revActClassBox'))$('#revActClassBox').hidden=true;
 if(targetType==='evento'){
  $('#reviewDialogTitle').textContent='Vincular ou revisar evento modificador';
  $('#revContextBox').innerHTML=`<b>Evento:</b> ${esc(first.type)} em ${dt(first.date)} (pág. ${esc(first.page||'—')})<br>${esc((first.description||'').slice(0,220))}`;
  $('#revDecision').innerHTML='<option value="VINCULAR">VINCULAR a ato original</option><option value="REJEITAR">REJEITAR evento</option><option value="REABRIR">REABRIR evento</option>';
  $('#revEventBox').hidden=false;
  $('#revOriginalActId').value=first.act||first.suggestedAct||'';
  $('#revCorrectionsDetails').hidden=true;
  $('#revConfirmLinkRow').hidden=true;
 }else if(targetType==='ato_classificacao'){
  $('#reviewDialogTitle').textContent=`Corrigir classificação do ato · ${first.resenha||first.id}`;
  $('#revContextBox').innerHTML=`<b>Ato ${esc(first.id)}</b> · Resenha ${esc(first.resenha||'')} (${dt(first.date)}, pág. ${esc(first.page||'—')})`;
  $('#revDecision').innerHTML='<option value="CORRIGIR_ATO">CORRIGIR CLASSIFICAÇÃO DO ATO</option>';
  $('#revEventBox').hidden=true;
  $('#revCorrectionsDetails').hidden=true;
  $('#revConfirmLinkRow').hidden=true;
  if($('#revActClassBox')){
   $('#revActClassBox').hidden=false;
   $('#revActEixo').value=first.axis==='tempo'?'TEMPO_SERVICO':'PROGRESSAO';
   $('#revActModalidade').value=first.modality==='Vertical'?'VERTICAL':first.modality==='Horizontal'?'HORIZONTAL':'';
   $('#revActGrupo').value=(first.group&&!String(first.group).startsWith('PENDENTE:'))?first.group:'';
   $('#revActSubcat').value=(first.category&&/^TS-0[1-7]$/.test(first.category))?first.category:'';
  }
 }else if(targetType==='ato'){
  $('#reviewDialogTitle').textContent=`Revisar ato completo · ${first.resenha||first.id}`;
  $('#revContextBox').innerHTML=`<b>Ato ${esc(first.id)}</b> · Resenha ${esc(first.resenha||'')} (${dt(first.date)}, pág. ${esc(first.page||'—')}) · Vínculo GEDIV: <b>${esc(mentionLabel(first.sourceMention))}</b>`;
  $('#revDecision').innerHTML='<option value="CONFERIR">CONFERIR todas as decisões do ato</option><option value="REJEITAR">REJEITAR ato</option><option value="REABRIR">REABRIR ato</option>';
  $('#revEventBox').hidden=true;
  $('#revCorrectionsDetails').hidden=true;
  $('#revConfirmLinkRow').hidden=false;
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
   if($('#revCorrCargo'))$('#revCorrCargo').value=first.cargo||'';
   if($('#revCorrLotacao'))$('#revCorrLotacao').value=first.lotacao||'';
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
     <button type="button" role="menuitem" id="delicateConflictsAct" hidden><span>⚖ Conflitos de reconciliação</span></button>
     <button type="button" role="menuitem" id="delicateAuditAct" hidden><span>📋 Trilha de auditoria</span></button>
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
   $('#delicateConflictsAct').addEventListener('click',()=>{$('#delicateAcctMenu').hidden=true;openConflictsDialog();});
   $('#delicateAuditAct').addEventListener('click',()=>{$('#delicateAcctMenu').hidden=true;openAuditDialog();});
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
 $('#closeLoginTop')?.addEventListener('click',()=>{$('#loginPass').value='';$('#loginStatus').textContent='';$('#loginDialog').close();});
 $('#closeLoginBtn')?.addEventListener('click',()=>{$('#loginPass').value='';$('#loginStatus').textContent='';$('#loginDialog').close();});
 $('#closeConflictsTop')?.addEventListener('click',()=>$('#conflictsDialog').close());
 $('#closeConflictsBtn')?.addEventListener('click',()=>$('#conflictsDialog').close());
 $('#refreshConflictsBtn')?.addEventListener('click',()=>openConflictsDialog());
 $('#closeAuditTop')?.addEventListener('click',()=>$('#auditDialog').close());
 $('#closeAuditBtn')?.addEventListener('click',()=>$('#auditDialog').close());
 $('#refreshAuditBtn')?.addEventListener('click',()=>openAuditDialog());
 $('#publishPublicSnapshotBtn')?.addEventListener('click',async()=>{
  const btn=$('#publishPublicSnapshotBtn'),st=$('#publishSnapshotStatus');
  btn.disabled=true;if(st)st.textContent='Publicando snapshot…';
  try{
   const r=await fetch('/api/admin/snapshot-publico',{method:'POST',credentials:'same-origin',headers:window.GEDIV_AUTH.headers({'Content-Type':'application/json'}),body:'{}'});
   if(r.status===401){await handleAuthExpiry('Sessão expirada ou encerrada. Faça login novamente.');return;}
   const d=await r.json().catch(()=>({}));
   if(!r.ok)throw new Error(d.erro||'HTTP '+r.status);
   await openAuditDialog();
   if(st)st.textContent='Snapshot público publicado ('+String(d.gerado_em||'').slice(0,19).replace('T',' ')+').';
   toast('Snapshot público atualizado com sucesso.');
  }catch(err){if(st)st.textContent='Falha: '+err.message;}
  finally{btn.disabled=false;}
 });
 $('#loginForm')?.addEventListener('submit',async e=>{
  e.preventDefault();
  const st=$('#loginStatus'),btn=$('#submitLoginBtn');
  st.classList.remove('is-error');st.textContent='Autenticando…';btn.disabled=true;
  try{
   const manualTok=$('#loginTokenInput').value.trim();
   if(manualTok){
    window.GEDIV_AUTH.set(manualTok,{usuario:'token_legado',nome:'Credencial técnica legada',papel:'gerencia'});
   }else{
    const usuario=$('#loginUser').value.trim(),senha=$('#loginPass').value;
    if(!usuario||!senha)throw new Error('Informe usuário e senha ou cole o token técnico.');
    const r=await fetch('/api/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({usuario,senha,modo_cookie:true})});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(d.erro||'Credenciais inválidas.');
    window.GEDIV_AUTH.setSession({usuario:d.usuario,nome:d.nome,papel:d.papel||'gerencia'});
   }
   await refreshData();
   if(!data.backend?.autenticado){window.GEDIV_AUTH.clear();throw new Error('Credencial não autorizada pelo servidor.');}
   Object.assign(S,{validation:data.rows.some(r=>r.validation==='conferido')?'conferido':'pendente',view:'geral',axis:'',modality:'',group:'',level:'',category:[],merit:'',query:'',from:'',to:'',card:'',page:0,selected:''});
   $('#search').value='';
   try{history.replaceState(null,'',location.pathname+location.search);}catch{}
   initHistory();renderMeta();render();
   $('#loginPass').value='';$('#loginTokenInput').value='';
   $('#loginDialog').close();
   toast(data.backend?.ehAdmin?'Sessão administrativa autenticada.':'Sessão gerencial autenticada.');
  }catch(err){st.textContent=err.message;st.classList.add('is-error');}
  finally{btn.disabled=false;}
 });
 $('#logoutBtn')?.addEventListener('click',async()=>{
  try{await fetch('/api/logout',{method:'POST',credentials:'same-origin',headers:window.GEDIV_AUTH.headers({'Content-Type':'application/json'}),body:'{}'});}catch{}
  window.GEDIV_AUTH.clear();
  await refreshData();
  Object.assign(S,{validation:'conferido',view:'geral',axis:'',modality:'',group:'',level:'',category:[],merit:'',query:'',from:'',to:'',card:'',page:0,selected:''});
  $('#search').value='';
  try{history.replaceState(null,'',location.pathname+location.search);}catch{}
  initHistory();renderMeta();render();
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
   }else if(alvo==='ato'){
    payload.id=rawIds[0];
   }else if(alvo==='ato_classificacao'){
    payload.id=rawIds[0];
    const corrAto={eixo:$('#revActEixo').value};
    if($('#revActModalidade').value)corrAto.modalidade=$('#revActModalidade').value;
    if($('#revActGrupo').value.trim())corrAto.grupo=$('#revActGrupo').value.trim().toUpperCase();
    if($('#revActSubcat').value)corrAto.subcategoria=$('#revActSubcat').value;
    payload.correcoes=corrAto;
   }else{
    payload.ids=rawIds;
    if(rawIds.length===1&&!$('#revCorrectionsDetails').hidden){
     const corr={};
     if($('#revCorrProcess').value.trim())corr.processo=$('#revCorrProcess').value.trim();
     if($('#revCorrRegistration').value.trim())corr.matricula=$('#revCorrRegistration').value.trim();
     if($('#revCorrServer').value.trim())corr.servidor=$('#revCorrServer').value.trim();
     if($('#revCorrCargo')?.value.trim())corr.cargo=$('#revCorrCargo').value.trim();
     if($('#revCorrLotacao')?.value.trim())corr.lotacao=$('#revCorrLotacao').value.trim();
     if($('#revCorrResult').value)corr.resultado=$('#revCorrResult').value;
     if($('#revCorrClassFrom').value.trim())corr.classe_anterior=$('#revCorrClassFrom').value.trim().toUpperCase();
     if($('#revCorrClassTo').value.trim())corr.classe_posterior=$('#revCorrClassTo').value.trim().toUpperCase();
     if(Object.keys(corr).length)payload.correcoes=corr;
    }
   }
   const r=await fetch('/api/revisao',{method:'POST',credentials:'same-origin',headers:window.GEDIV_AUTH.headers({'Content-Type':'application/json'}),body:JSON.stringify(payload)});
   if(r.status===401){await handleAuthExpiry('Sessão expirada ou encerrada. Faça login novamente.');return;}
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
 const mu=$('#delicateMenuUser'),mm=$('#delicateMenuMeta'),la=$('#delicateLoginAct'),lo=$('#delicateLogoutAct'),ba=$('#delicateBatchAct'),ca=$('#delicateConflictsAct'),aa=$('#delicateAuditAct');
 if(mu)mu.textContent=isAuth?(usr?`${usr.nome} (${usr.usuario})`:'Sessão autenticada'):'Visitante (Público)';
 if(mm)mm.textContent=isAuth?`${Number(meta.edicoes)||0} edições · perfil ${isAdm?'Administração':'Gerência'}`:'Apenas indicadores agregados';
 if(la)la.hidden=isAuth;if(lo)lo.hidden=!isAuth;if(ba)ba.hidden=!isAdm;if(ca)ca.hidden=!isAuth;if(aa)aa.hidden=!isAuth;
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
    assert not re.search(r'"registration"\s*:\s*"\d+', html), "Matrícula residual encontrada no HTML!"
    assert not re.search(r"[A-Za-z0-9.-]*\.chatgpt\.site", html, re.I), "URL privada chatgpt.site encontrada!"
    assert not re.search(r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+|/home/(?!\[)[A-Za-z0-9._-]+", html, re.I), "Caminho local encontrado!"
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html), "E-mail encontrado no HTML!"
    assert not re.search(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Gediv(?:Homolog|Admin)\d{4}[!])", html), "Token ou credencial encontrado no HTML!"

    dest_unificado.parent.mkdir(parents=True, exist_ok=True)
    dest_unificado.write_text(html, encoding="utf-8", newline="\n")
    if destino_html is None:
        dest_paleta.write_text(
            json.dumps({"total": len(orig_colors), "cores_hex": sorted(orig_colors)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"Paleta salva ({len(orig_colors)} cores HEX): {dest_paleta}")
    print(f"Salvo ({len(html):,} bytes): {dest_unificado}")
    print(f"Verificação de paleta: {len(new_colors)} cores HEX (0 cores novas).")
    return dest_unificado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstrói o painel unificado GEDIV sem dados embutidos.")
    parser.add_argument(
        "--origem",
        type=pathlib.Path,
        default=None,
        help="Caminho opcional para o HTML base (padrão: observatorio/web/unificado/modelo-base-sanitizado.html).",
    )
    parser.add_argument(
        "--saida",
        type=pathlib.Path,
        default=None,
        help="Caminho opcional de saída para o HTML unificado gerado.",
    )
    args = parser.parse_args(argv)
    construir(args.origem, args.saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
