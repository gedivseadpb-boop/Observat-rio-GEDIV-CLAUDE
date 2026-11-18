'use strict';
/* Tarefas guiadas avaliadas heuristicamente em navegador, sem participantes reais. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'); const path=require('node:path');
const base=process.env.BASE_URL||'http://127.0.0.1:4175/';
const out=process.env.EVIDENCE_DIR||'/workspace/gediv-evidencias/clareza/tarefas';
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const b=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium'});const results=[];
 try{for(const theme of ['light','dark']){
  const ctx=await b.newContext({viewport:{width:390,height:844},locale:'pt-BR',timezoneId:'America/Sao_Paulo',colorScheme:theme,acceptDownloads:true,reducedMotion:'reduce'});const p=await ctx.newPage();p.setDefaultTimeout(10000);
  await p.goto(base);await p.waitForSelector('#pagina[aria-busy=false]');
  await p.locator('#periodoRapido').click();assert.equal(await p.locator('#gedivCalendario').evaluate(e=>e.open),true);
  await p.locator('#gedivCalInicio').fill('2026-10-01');await p.locator('#gedivCalFim').fill('2026-11-30');await p.locator('#gedivCalAplicar').click();
  assert.match(await p.locator('#filtrosAtivos').innerText(),/01\/10\/2026.*30\/11\/2026/);
  results.push({theme,task:'Encontrar e escolher um período pela ação principal',ok:true});
  await p.locator('#verTotais').click();assert.equal(await p.evaluate(()=>document.activeElement.className),'exec-kpi-section');assert.equal(await p.locator('.exec-kpi-value').first().innerText(),'175–199');
  await p.screenshot({path:path.join(out,theme+'-totais-no-celular.png')});
  results.push({theme,task:'Encontrar totais e a unidade de contagem em um clique',ok:true});
  await p.locator('#abas a[href^="#tempo"]').click();assert.equal(await p.locator('#tituloPagina').innerText(),'Tempo de Serviço');assert.equal(await p.locator('#listaServicos input').count(),7);
  await p.locator('#abrirMenu').click();await p.locator('#listaServicos input[value="TS-01"]').check();await p.locator('button[form="filtros"]').click();assert.equal(await p.locator('.exec-kpi-value').first().innerText(),'—');
  await p.locator('#voltarConsulta').click();await p.waitForFunction(()=>!document.querySelector('[name=servico][value="TS-01"]').checked);assert.equal(await p.locator('#tituloPagina').innerText(),'Tempo de Serviço');
  results.push({theme,task:'Escolher serviço e voltar mantendo o período',ok:true});
  await p.locator('#outrasSecoes > summary').click();await p.locator('#abas a[href^="#cobertura"]').click();await p.locator('#pesquisarConsulta').click();assert.equal(await p.evaluate(()=>document.activeElement.id),'buscaLista');assert.match(await p.locator('#filtrosAtivos').innerText(),/Tempo de Serviço/);await p.locator('#chipsFiltro [data-remover-filtro="eixo"]').click();await p.locator('#buscaLista').fill('GAJ');await p.waitForFunction(()=>document.querySelectorAll('.query-item').length===1);assert.match(await p.locator('.query-item').innerText(),/GAJ/);
  results.push({theme,task:'Reconhecer pesquisa e encontrar agregado público por grupo',ok:true});
  assert.equal(await p.locator('#abas a[aria-current=page]').count(),1);
  await p.locator('#opcoesExportacao > summary').click();const [dl]=await Promise.all([p.waitForEvent('download'),p.locator('#exportarCsv').click()]);await dl.saveAs(path.join(out,theme+'-mobile.csv'));assert.match(fs.readFileSync(path.join(out,theme+'-mobile.csv'),'utf8'),/01\/10\/2026/);
  results.push({theme,task:'Reconhecer exportação no celular e baixar o recorte',ok:true});
  await ctx.close();
 }}finally{await b.close();fs.writeFileSync(path.join(out,'resultados.json'),JSON.stringify({method:'Avaliação heurística por tarefas em navegador real; sem participantes reais.',results},null,2));}
 console.log(JSON.stringify({passed:results.length,failed:0,out}));
})().catch(e=>{console.error(e);process.exitCode=1});
