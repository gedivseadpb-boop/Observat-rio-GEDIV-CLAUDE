"""Gera e valida o pacote estático 100% sintético do Painel Unificado GEDIV para GitHub Pages.

- Usa o painel real `observatorio/web/unificado/index.html` (Delicadeza Visual · 240 cores HEX).
- Gera base SQLite temporária descartável com dados 100% SINTÉTICOS (ano 2099, matrículas 950.xxx-x,
  nomes fictícios) sem tocar nos bancos originais e sem depender das rotas Python `/api/*`.
- Desabilita de forma clara e honesta funções que exigem backend (login gerencial real, conferência,
  auditoria, conflitos e alterações), sem simular segurança por senha em JavaScript.
- Valida o artefato gerado contra vazamento de PII, credenciais, arquivos não autorizados e cores novas.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from observatorio.nucleo.banco import Banco  # noqa: E402
from observatorio.operacao import previa_sintetica  # noqa: E402
from observatorio.painel import adaptador, indicadores  # noqa: E402

HTML_ORIGEM = RAIZ / "observatorio" / "web" / "unificado" / "index.html"
PALETA_JSON = RAIZ / "observatorio" / "web" / "unificado" / "paleta-aprovada.json"


def gerar_dados_sinteticos_publicos() -> dict:
    """Constrói um payload JSON 100% sintético para demonstração estática (sem backend e sem dados reais),
    reutilizando a fonte única canônica `observatorio.operacao.previa_sintetica`."""
    with tempfile.TemporaryDirectory(prefix="gediv-pages-sint-") as tmp:
        banco = Banco(Path(tmp) / "sintetico.sqlite3")
        try:
            previa_sintetica.popular_banco_sintetico_canonico(banco)

            # Projetar os dados sintéticos (conferidos + pendentes + rejeitados + eventos + outras publicações)
            perfil = indicadores.GERENCIA_PERFIL
            p_conf = indicadores.painel(banco, {"escopo": "conferido"}, perfil, proteger_publico=False)
            p_pend = indicadores.painel(banco, {"escopo": "pendente"}, perfil, proteger_publico=False)
            outras = indicadores.outras_publicacoes(banco, perfil)
            rej_rows = []
            for r in banco.con.execute(
                "SELECT d.id, d.ato_id, d.sha256, d.pagina, d.processo, d.servidor, d.matricula, d.lotacao, "
                "d.cargo, d.detalhe, d.resultado, d.trecho, d.validacao, d.revisor, d.revisado_em, d.justificativa, "
                "a.numero AS resenha, a.sufixo, a.tipo, a.data_publicacao AS data, a.data_expediente, a.vinculo, "
                "a.natureza, a.eixo, a.modalidade, a.condicao, a.grupo, a.grupo_expressao, a.subcategoria, "
                "a.pendencias, a.chave_logica, a.gerencia AS gerencia_painel, "
                "SUBSTR(a.texto,1,1200) AS texto_identificacao, l.numero_edicao, l.data_edicao, 0 AS conflito_aberto "
                "FROM decisao d JOIN ato a ON a.id = d.ato_id JOIN leitura l ON l.sha256 = d.sha256 "
                "WHERE a.gerencia = 'GEDIV' AND d.validacao = 'REJEITADO'"
            ).fetchall():
                lr = dict(r)
                lr.pop("texto_identificacao", None)
                lr["detalhe"] = json.loads(lr["detalhe"] or "{}")
                lr["pendencias"] = json.loads(lr["pendencias"] or "[]")
                lr["url_oficial"] = None
                lr["pdf_no_acervo"] = None
                rej_rows.append(lr)
            combinado = {
                **p_conf,
                "linhas": list(p_pend.get("linhas") or []) + list(p_conf.get("linhas") or []),
                "indicadores_conferido": p_conf.get("indicadores") or {},
                "eventos_detalhados_conferido": (p_conf.get("series") or {}).get("eventos_detalhados") or {},
            }
            snap = adaptador.projetar_para_dashboard_2910(combinado, outras, rej_rows)

            # Sanitização explícita para demonstração estática pública (ZERO credenciais, ZERO /api/pdf, ZERO campos internos)
            for row in snap["rows"] + snap.get("otherPublications", []):
                row["url"] = ""
                row["urlOficial"] = ""
                row["pdfNoAcervo"] = ""
                row["preliminaryReview"] = ""
                row.pop("revisor", None)
                row.pop("revisadoEm", None)
                row.pop("justificativa", None)
            for ev in snap.get("events", []):
                ev["url"] = ""
                ev["pdfNoAcervo"] = ""

            snap["backend"] = {
                "perfil": "demonstracao_estatica",
                "autenticado": False,
                "ehAdmin": False,
                "modoDemonstracaoEstatica": True,
                "versaoRegras": snap["backend"].get("versaoRegras"),
                "incompatibilidadeVersaoRegras": False,
                "versaoRegrasDiagnostico": {"compativel": True, "incompativel": False},
                "indicadores": p_conf.get("indicadores") or {},
                "apoio": {
                    "eventos_de_alteracao": p_conf["apoio"].get("eventos_de_alteracao"),
                    "eventos_sem_vinculo": p_conf["apoio"].get("eventos_sem_vinculo"),
                    "eventos_fora_do_acervo": p_conf["apoio"].get("eventos_fora_do_acervo"),
                    "decisoes_conferidas": p_conf["apoio"].get("decisoes_conferidas"),
                    "decisoes_pendentes": p_conf["apoio"].get("decisoes_pendentes"),
                    "decisoes_rejeitadas": p_conf["apoio"].get("decisoes_rejeitadas"),
                },
                "series": p_conf.get("series") or {},
                "resenhas": [],
            }
            snap["meta"]["version"] = "Painel Diário Oficial | GEDIV · Demonstração Estática (Dados Sintéticos)"
            snap["meta"]["coverage"] = (
                "Demonstração pública gratuita no GitHub Pages com 6 edições 100% sintéticas (Jun–Nov/2026). "
                "Nenhum dado real de servidor público."
            )
            snap["meta"]["automation"] = "Prévia estática somente leitura no GitHub Pages · sem rotas /api/*."
            snap["meta"]["personal"] = (
                "Demonstração estática com dados exclusivamente sintéticos. "
                "Login gerencial verdadeiro, conferência documental, auditoria e alterações de registros exigem servidor backend."
            )
            snap["dashboard"]["defaultScope"] = "conferido"
            return snap
        finally:
            banco.fechar()


def adaptar_html_estatico(html_orig: str) -> str:
    """Adapta `observatorio/web/unificado/index.html` para operar estaticamente no GitHub Pages.

    Preserva todas as 7 abas, cartões, gráficos, calendário, filtros, navegação e as 240 cores HEX (0 cores novas).
    Desabilita claramente funções que exigem backend (sem simular login/senha no JavaScript).
    """
    html = html_orig

    # 1. Favicon inline neutro (evita 404 de /favicon.ico no console do navegador, sem duplicar se já presente)
    if '<link rel="icon"' not in html:
        html = html.replace(
            '<meta name="color-scheme" content="light">',
            '<meta name="color-scheme" content="light"><link rel="icon" href="data:,">',
            1,
        )

    # 2. Carregamento estático direto de ./dados-sinteticos-publicos.json (zero chamadas /api/*)
    old_ready = """window.GEDIV_READY=(async()=>{
 let d=window.GEDIV_BOOTSTRAP;
 if(location.protocol!=='file:'&&!location.hostname.endsWith('github.io')){
  try{d=await window.GEDIV_FETCH_DATA();}catch(err){console.warn('Usando esqueleto inicial:',err);}
 }
 window.GEDIV_DATA=d;
 return d;
})();"""
    new_ready = """window.GEDIV_STATIC_DEMO=true;
window.GEDIV_FETCH_DATA=async()=>{
 const r=await fetch('./dados-sinteticos-publicos.json',{cache:'no-store',headers:{Accept:'application/json'}});
 if(!r.ok)throw new Error('HTTP '+r.status);
 return window.GEDIV_MODEL.acceptSnapshot(await r.json());
};
window.GEDIV_READY=(async()=>{
 let d=window.GEDIV_BOOTSTRAP;
 try{d=await window.GEDIV_FETCH_DATA();}catch(err){console.warn('Falha ao carregar dados sintéticos estáticos:',err);}
 window.GEDIV_DATA=d;
 return d;
})();"""
    assert old_ready in html, "Bloco window.GEDIV_READY esperado não encontrado"
    html = html.replace(old_ready, new_ready, 1)

    # 3. Forçar isStaticHost()=true no pacote estático e definir aviso honesto para funções que exigem backend
    old_static_host = "const isStaticHost=()=>location.hostname.endsWith('github.io')||location.protocol==='file:';"
    new_static_host = (
        "const isStaticHost=()=>true;\n"
        "const isStaticDemo=()=>!!(window.GEDIV_STATIC_DEMO||data.backend?.modoDemonstracaoEstatica);"
    )
    assert old_static_host in html, "isStaticHost esperado não encontrado"
    html = html.replace(old_static_host, new_static_host, 1)

    # 4. Em isPublicAgg(): no modo demonstração estática sintética, as rows sintéticas estão disponíveis para os controles
    old_pub_agg = """function isPublicAgg(){
 return !data.backend?.autenticado&&!(data.rows||[]).length&&!!(data.backend?.indicadores&&data.backend?.series);
}"""
    assert old_pub_agg in html  # já retorna false quando data.rows tem registros sintéticos

    # 5. Desabilitar de forma clara e honesta login falso, revisão, conflitos, auditoria e lotes (sem senha em JS)
    old_open_login = """ function openLoginModal(){
  $('#loginStatus').textContent='';$('#loginStatus').classList.remove('is-error');$('#loginDialog').showModal();
 }"""
    new_open_login = """ function openStaticBackendNotice(acao){
  const titulo=acao?`${acao} — recurso exclusivo com backend`:'Demonstração estática no GitHub Pages';
  const body=`<div class="reconcile-note" style="margin-top:0"><b>Prévia pública gratuita com dados 100% sintéticos (somente leitura).</b></div>
  <p>Esta publicação estática no <b>GitHub Pages</b> permite navegar livremente pelas <b>7 abas</b>, cartões, gráficos, calendário, filtros, tabela ampliada e exportações sobre uma base fictícia descartável.</p>
  <p><b>Funções desabilitadas nesta demonstração (exigem servidor backend Python/SQLite):</b></p>
  <ul><li><b>Login gerencial verdadeiro</b> (contas nominais e cookie <code>HttpOnly</code> — não há senha simulada em JavaScript);</li>
  <li><b>Conferência documental e alterações de registros</b> (<code>POST /api/revisao</code>);</li>
  <li><b>Resolução de conflitos (D2)</b> e <b>trilha de auditoria institucional (D3)</b>;</li>
  <li><b>Recebimento administrativo de lotes</b> e leitura de PDFs privados.</li></ul>`;
  openDialog(titulo,body);
 }
 function openLoginModal(){
  openStaticBackendNotice('Acesso gerencial');
 }"""
    assert old_open_login in html, "openLoginModal esperado não encontrado"
    html = html.replace(old_open_login, new_open_login, 1)

    # 6. Impedir abertura de modais de backend (revisão, conflitos, auditoria, lote) e exportação via /api
    for old_guard, new_guard in (
        (
            "function openReviewModal(targetType,items){\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
            "function openReviewModal(targetType,items){\n if(isStaticDemo()){openStaticBackendNotice('Conferência documental');return;}\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
        ),
        (
            "async function openConflictsDialog(){\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
            "async function openConflictsDialog(){\n if(isStaticDemo()){openStaticBackendNotice('Conflitos de reconciliação');return;}\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
        ),
        (
            "async function openAuditDialog(){\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
            "async function openAuditDialog(){\n if(isStaticDemo()){openStaticBackendNotice('Trilha de auditoria');return;}\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
        ),
        (
            " $('#showPending').addEventListener('click',()=>{if(!data.backend?.autenticado){openLoginModal();return;}if(S.validation!=='pendente'){S.validation='pendente';S.card='';S.page=0;S.selected='';commitHistory();render();}openFullTableModal();});",
            " $('#showPending').addEventListener('click',()=>{if(!isStaticDemo()&&!data.backend?.autenticado){openLoginModal();return;}if(S.validation!=='pendente'){S.validation='pendente';S.card='';S.page=0;S.selected='';commitHistory();render();}openFullTableModal();});",
        ),
    ):
        assert old_guard in html, f"Guarda esperada não encontrada: {old_guard[:60]}"
        html = html.replace(old_guard, new_guard, 1)

    # 7. Permitir exportação local CSV/XLSX dos dados 100% SINTÉTICOS no modo estático (sem /api/exportar)
    old_exp_csv = """function exportCsv(){
 if(!data.backend?.autenticado){toast('Lista individual (.csv) disponível apenas após login gerencial.');return;}
 const localFallback=()=>{exp.download(exp.csv(decisionRows()),'text/csv;charset=utf-8','GEDIV-decisoes-filtradas.csv');toast('Lista filtrada gerada.');};
 if(!isStaticHost()){serverAuditedExport('csv',localFallback);return;}
 localFallback();
}"""
    new_exp_csv = """function exportCsv(){
 if(!isStaticDemo()&&!data.backend?.autenticado){toast('Lista individual (.csv) disponível apenas após login gerencial.');return;}
 const fname=isStaticDemo()?'GEDIV-demonstracao-sintetica.csv':'GEDIV-decisoes-filtradas.csv';
 exp.download(exp.csv(decisionRows()),'text/csv;charset=utf-8',fname);
 toast(isStaticDemo()?'CSV da demonstração sintética gerado.':'Lista filtrada gerada.');
}"""
    assert old_exp_csv in html, "exportCsv esperado não encontrado"
    html = html.replace(old_exp_csv, new_exp_csv, 1)

    old_exp_xlsx_guard = """ if(!isAuth){
  exp.download(exp.xlsx({'Resumo':summary}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-resumo-publico.xlsx');
  toast('Resumo agregado gerado (dados individuais protegidos).');return;
 }"""
    new_exp_xlsx_guard = """ if(!isAuth&&!isStaticDemo()){
  exp.download(exp.xlsx({'Resumo':summary}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-resumo-publico.xlsx');
  toast('Resumo agregado gerado (dados individuais protegidos).');return;
 }"""
    assert old_exp_xlsx_guard in html, "exportXlsx guard esperado não encontrado"
    html = html.replace(old_exp_xlsx_guard, new_exp_xlsx_guard, 1)

    # 8. Em renderMeta(): exibir rótulo honesto de Demonstração Estática Sintética, manter seletor de escopo sintético visível e desabilitar ações de backend
    old_rm_chrome = """ const dDot=$('#delicateDot'),dLbl=$('#delicateAcctLabel'),dTag=$('#delicateRoleTag');
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
    new_rm_chrome = """ const dDot=$('#delicateDot'),dLbl=$('#delicateAcctLabel'),dTag=$('#delicateRoleTag');
 if(dDot)dDot.classList.toggle('is-pub',true);
 if(dLbl)dLbl.textContent='Demonstração estática';
 if(dTag)dTag.textContent='Sintético';
 const mu=$('#delicateMenuUser'),mm=$('#delicateMenuMeta'),la=$('#delicateLoginAct'),lo=$('#delicateLogoutAct'),ba=$('#delicateBatchAct'),ca=$('#delicateConflictsAct'),aa=$('#delicateAuditAct');
 if(mu)mu.textContent='Demonstração estática (Somente leitura)';
 if(mm)mm.textContent='GitHub Pages · dados 100% sintéticos';
 if(la)la.hidden=true;if(lo)lo.hidden=true;if(ba)ba.hidden=true;if(ca)ca.hidden=true;if(aa)aa.hidden=true;
 const pendDemo=data.rows.filter(r=>r.validation==='pendente').length,confDemo=data.rows.filter(r=>r.validation==='conferido').length,rejDemo=data.rows.filter(r=>r.validation==='rejeitado').length;
 $('#receivedTotal').textContent=data.rows.length+' registros sintéticos na demonstração';
 $('#receivedMetaPill').textContent=`${pendDemo} em conferência · ${rejDemo} rejeitados`;
 $('#receivedValidation').textContent=`${pendDemo} em conferência · ${confDemo} conferidos · ${rejDemo} rejeitados`;
 $('#validationScope').innerHTML=`<option value="conferido">Conferidos (${confDemo})</option><option value="pendente">Em conferência (${pendDemo})</option><option value="rejeitado">Rejeitados (${rejDemo})</option>`;
 $('#validationScope').value=S.validation;
 const proxyScope=$('#delicateScopeProxy');
 if(proxyScope){proxyScope.hidden=false;proxyScope.innerHTML=$('#validationScope').innerHTML;proxyScope.value=S.validation;}
 const expHead=$('#exportScopeHead');
 if(expHead){const mRec=typeof model==='function'?model():{original:[]};expHead.textContent=`Demonstração sintética · ${views[S.view]?.[1]||'Visão'} (${mRec.original.length})`;}
 const bt=$('#bannerTitle'),bx=$('#bannerText'),edC=Number(meta.edicoes)||0,scopeLbl=S.validation==='pendente'?'fila pendente (sintética)':S.validation==='rejeitado'?'rejeitados (sintéticos)':'conferidos (sintéticos)';
 if(bt)bt.textContent=`Demonstração estática no GitHub Pages (${edC} edições · 100% sintético) · ${scopeLbl}`;
 if(bx)bx.textContent='Prévia pública gratuita somente leitura. Login gerencial, conferência documental, auditoria e alterações exigem backend.';"""
    assert old_rm_chrome in html, "Bloco renderMeta chrome esperado não encontrado"
    html = html.replace(old_rm_chrome, new_rm_chrome, 1)

    # 9. Sincronizar exportScopeHead também em sync()
    html = html.replace(
        "$('#exportScopeHead').textContent=isA?`Recorte: ${views[S.view]?.[1]||'Visão'} · ${mE.original.length} registro(s)`:'Modo público: apenas indicadores agregados';",
        "$('#exportScopeHead').textContent=`Demonstração sintética · ${views[S.view]?.[1]||'Visão'} (${mE.original.length})`;",
        1,
    )

    # 10. Garantir preservação estrita da paleta (240 cores HEX, 0 cores novas)
    orig_colors = {c.lower() for c in json.loads(PALETA_JSON.read_text(encoding="utf-8"))["cores_hex"]}
    hex_re = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    new_colors = {c.lower() for c in hex_re.findall(html)}
    added = new_colors - orig_colors
    assert not added, f"Cores novas detectadas na prévia estática: {added}"
    return html


def validar_pacote_estatico(pasta: Path) -> None:
    """Validação fechada do artefato público antes de qualquer publicação no GitHub Pages."""
    arquivos = sorted(p.relative_to(pasta).as_posix() for p in pasta.rglob("*") if p.is_file())
    permitidos = {".nojekyll", "dados-sinteticos-publicos.json", "index.html"}
    assert set(arquivos) == permitidos, f"Arquivos fora da lista autorizada: {arquivos}"

    html = (pasta / "index.html").read_text(encoding="utf-8")
    dados_txt = (pasta / "dados-sinteticos-publicos.json").read_text(encoding="utf-8")
    dados = json.loads(dados_txt)

    # Proibições absolutas de privacidade e segurança
    for rotulo, texto in (("index.html", html), ("dados-sinteticos-publicos.json", dados_txt)):
        assert not re.search(r"SAD-PSE-202\d/\d+", texto), f"Processo real (202x) detectado em {rotulo}"
        assert not re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", texto), f"CPF detectado em {rotulo}"
        assert not re.search(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|PreviaGediv2026!|previa\.gediv)", texto), f"Segredo/credencial em {rotulo}"
        assert not re.search(r"C:[\\/]+Users[\\/]+", texto, re.I), f"Caminho local Windows em {rotulo}"

    assert not re.search(r"/api/pdf/", dados_txt), "Rota /api/pdf/ encontrada no JSON público!"
    assert dados["backend"]["autenticado"] is False, "JSON estático nunca pode vir marcado como autenticado!"
    assert dados["backend"]["ehAdmin"] is False, "JSON estático nunca pode ter ehAdmin=True!"
    assert dados["backend"]["modoDemonstracaoEstatica"] is True
    assert len(dados["rows"]) > 0, "JSON sintético sem registros!"
    for r in dados["rows"]:
        assert str(r.get("process") or "").startswith("SAD-PSE-2099/"), f"Processo não sintético: {r.get('process')}"
        assert str(r.get("registration") or "").startswith("950."), f"Matrícula não sintética: {r.get('registration')}"
        assert "FICTICIO" in str(r.get("server") or "").upper(), f"Nome não sintético: {r.get('server')}"

    assert html.count("\r\n") == 0, "CRLF detectado em index.html"
    assert "./dados-sinteticos-publicos.json" in html
    assert "openStaticBackendNotice" in html

    # Garantir reconciliação matemática exata das 5 situações de Progressão Vertical A–F
    res_nv = (dados.get("backend") or {}).get("series", {}).get("resumo_nivel_vertical") or {}
    assert res_nv.get("total_vertical", 0) > 0, "Sem progressões verticais na demonstração sintética"
    for campo_sit in ("classificados", "indeferidos", "nao_determinados", "inconsistentes", "nao_aplica"):
        assert res_nv.get(campo_sit, 0) > 0, f"Situação vertical ausente na prévia sintética: {campo_sit}"
    soma_5 = (
        res_nv["classificados"]
        + res_nv["indeferidos"]
        + res_nv["nao_determinados"]
        + res_nv["inconsistentes"]
        + res_nv["nao_aplica"]
    )
    assert soma_5 == res_nv["total_vertical"], f"Partição vertical divergente: {soma_5} != {res_nv['total_vertical']}"
    assert (
        res_nv["indeferidos"] + res_nv["nao_determinados"] + res_nv["inconsistentes"] + res_nv["nao_aplica"]
        == res_nv["nao_identificados"]
    ), "Soma das 4 categorias sem nível diverge de nao_identificados"


def construir_pacote(saida: Path) -> Path:
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True, exist_ok=True)
    snap = gerar_dados_sinteticos_publicos()
    html = adaptar_html_estatico(HTML_ORIGEM.read_text(encoding="utf-8"))
    (saida / ".nojekyll").write_text("", encoding="utf-8", newline="\n")
    (saida / "index.html").write_text(html, encoding="utf-8", newline="\n")
    (saida / "dados-sinteticos-publicos.json").write_text(
        json.dumps(snap, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validar_pacote_estatico(saida)
    print(f"Pacote estático validado com sucesso em: {saida}")
    print(f"  index.html: {(saida / 'index.html').stat().st_size:,} bytes (240 cores HEX, 0 cores novas)")
    print(f"  dados-sinteticos-publicos.json: {(saida / 'dados-sinteticos-publicos.json').stat().st_size:,} bytes "
          f"({len(snap['rows'])} linhas sintéticas, {len(snap['events'])} eventos, {len(snap['otherPublications'])} outras)")
    return saida


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", type=Path, help="Diretório de saída do pacote estático público (GitHub Pages)")
    ap.add_argument("--banco-local", type=Path, help="Diretório de dados SQLite local sintético canônico para homologação")
    args = ap.parse_args(argv)
    if not args.saida and not args.banco_local:
        ap.error("Informe --saida PASTA_ESTATICA e/ou --banco-local PASTA_DADOS_SINTETICOS")
    if args.saida:
        construir_pacote(args.saida)
    if args.banco_local:
        res = previa_sintetica.criar_base_local_sintetica(args.banco_local, publicar_snapshot=True)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
