'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(__dirname,'..','painel-publico');
const snapshot=JSON.parse(fs.readFileSync(path.join(root,'dados.json'),'utf8'));
const tick=()=>new Promise(r=>setTimeout(r,20));
async function app(t,{hash='',response}={}){
  const errors=[],downloads=[];let incoming=response||(()=>({ok:true,json:async()=>structuredClone(snapshot)}));
  const console=new VirtualConsole();console.on('jsdomError',e=>errors.push(e));
  const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{url:'https://preview.invalid/'+hash,runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:console});
  const w=dom.window;
  w.TextEncoder=TextEncoder;
  w.matchMedia=()=>({matches:false});w.fetch=async()=>incoming();
  w.URL.createObjectURL=blob=>{downloads.push(blob);return 'blob:public-test';};w.URL.revokeObjectURL=()=>{};
  w.HTMLAnchorElement.prototype.click=function(){};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
  w.print=()=>{};
  ['xlsx.js','pdf.js','modelo.js','app.js'].forEach(p=>w.eval(fs.readFileSync(path.join(root,p),'utf8')));
  await tick();
  t.after(()=>{dom.window.close();assert.deepEqual(errors.map(e=>e.message),[]);});
  const $=id=>w.document.getElementById(id);
  const change=(id,value)=>{$(id).value=value;$(id).dispatchEvent(new w.Event('change',{bubbles:true}));};
  const apply=()=>{$('filtros').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));};
  return {w,$,change,apply,downloads,setResponse:fn=>{incoming=fn;}};
}
test('interface carrega projeção real, sete KPIs e seis agregados sem resenhas fictícias',async t=>{
  const {$}=await app(t);
  assert.equal($('erro').hidden,true);
  assert.equal($('indicadores').children.length,7);
  assert.match($('indicadores').textContent,/210–214/);
  assert.equal($('pagina').getAttribute('aria-busy'),'false');
  assert.ok($('pagina').querySelector('svg'));
  assert.match($('pagina').textContent,/19/);
  assert.match($('pagina').textContent,/884/);
});
test('filtros aguardam aplicar e sincronizam cartão, tabela, exportação e impressão',async t=>{
  const a=await app(t);a.change('grupo','GAJ');
  assert.match(a.$('indicadores').textContent,/210–214/);
  a.apply();assert.match(a.$('indicadores').textContent,/25–29/);
  assert.equal(a.$('pagina').querySelectorAll('.records tbody tr').length,1);
  assert.match(a.$('impressao').textContent,/GAJ/);
  a.$('exportarXlsx').click();assert.equal(a.downloads.length,1);
  const bytes=await new Promise(r=>{const f=new a.w.FileReader();f.onload=()=>r(new Uint8Array(f.result));f.readAsArrayBuffer(a.downloads[0]);});
  assert.equal(bytes[0],0x50);assert.equal(bytes[1],0x4b);
  assert.ok(Buffer.from(bytes).includes(Buffer.from('25–29')));
  a.$('limpar').click();assert.match(a.$('indicadores').textContent,/210–214/);
});
test('recorte diário mostra indisponibilidade e não atribui total mensal ao dia',async t=>{
  const a=await app(t);a.change('inicio','2026-11-14');a.change('fim','2026-11-14');a.apply();
  assert.equal(a.$('restricaoRecorte').hidden,false);
  assert.match(a.$('restricaoRecorte').textContent,/dados diários/);
  assert.ok(!a.$('indicadores').textContent.includes('210–214'));
  assert.ok(!a.$('impressao').textContent.includes('210–214'));
  assert.equal(a.$('pagina').querySelectorAll('svg .chart-hit').length,0);
});
test('navegação cobre todas as áreas e conserva contexto; TS mantém sete serviços',async t=>{
  const a=await app(t);
  for(const name of ['progressao','tempo','dia','historico','alteracoes','outras','cobertura','pendencias','gerencial','geral']){
    a.w.location.hash=name;await tick();assert.ok(a.$('tituloPagina'));assert.ok(!a.$('pagina').textContent.includes('NaN'));
    if(name==='tempo'){assert.equal(a.$('listaServicos').children.length,7);assert.match(a.$('indicadores').textContent,/15–19/);}
    if(name==='gerencial'){assert.match(a.$('pagina').textContent,/NÃO HABILITADA/);assert.equal(a.$('pagina').querySelectorAll('input[type=password]').length,0);}
  }
});
test('paginação, todos os registros, detalhe e retorno não descartam filtros',async t=>{
  const a=await app(t);
  a.$('pagina').querySelector('[data-paginar="tabela:proxima"]').click();
  assert.equal(a.$('pagina').querySelectorAll('.records tbody tr').length,1);
  a.$('pagina').querySelector('[data-ver-todos]').click();
  assert.equal(a.$('pagina').querySelectorAll('.records tbody tr').length,6);
  a.$('pagina').querySelector('[data-detalhe]').click();assert.equal(a.$('detalhe').open,true);
  assert.match(a.$('corpoDetalhe').textContent,/Versão das regras/);
  a.$('fecharDetalhe').click();assert.equal(a.$('detalhe').open,false);
  assert.equal(a.$('pagina').querySelectorAll('.records tbody tr').length,6);
});
test('falha de atualização remove valores anteriores, bloqueia exports e permite recuperação',async t=>{
  const a=await app(t);a.setResponse(()=>({ok:false,status:503}));a.$('atualizar').click();await tick();
  assert.equal(a.$('erro').hidden,false);assert.ok(!a.$('indicadores').textContent.includes('210–214'));
  assert.equal(a.$('exportarXlsx').disabled,true);assert.equal(a.$('impressao').innerHTML,'');
  a.setResponse(()=>({ok:true,json:async()=>structuredClone(snapshot)}));a.$('tentarNovamente').click();await tick();
  assert.equal(a.$('erro').hidden,true);assert.match(a.$('indicadores').textContent,/210–214/);
});
test('JSON inválido e campos privados falham de forma fechada',async t=>{
  const a=await app(t,{response:()=>({ok:true,json:async()=>{throw new SyntaxError('Inválido');}})});
  assert.equal(a.$('erro').hidden,false);
  const d=structuredClone(snapshot);d.celulas[0].servidor='MARCADOR PRIVADO FICTICIO';
  a.setResponse(()=>({ok:true,json:async()=>d}));a.$('tentarNovamente').click();await tick();
  assert.equal(a.$('erro').hidden,false);assert.ok(!a.w.document.body.textContent.includes('MARCADOR PRIVADO FICTICIO'));
});
test('zero conferido é explícito e recorte não divulgado continua desconhecido',async t=>{
  const a=await app(t);a.change('situacao','conferido');a.apply();
  assert.equal(a.$('indicadores').children[2].querySelector('strong').textContent,'0');
  a.$('limpar').click();a.change('eixo','TEMPO_SERVICO');a.apply();
  assert.match(a.$('indicadores').textContent,/15–19/);
  const check=a.$('listaServicos').querySelector('input');check.checked=true;check.dispatchEvent(new a.w.Event('change',{bubbles:true}));a.apply();
  assert.equal(a.$('indicadores').children[2].querySelector('strong').textContent,'—');
});
