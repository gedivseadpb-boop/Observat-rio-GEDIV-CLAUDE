'use strict';
/* Capturas e regressão visual reais do pacote público. PHASE=antes congela baseline sem alterar a UI. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');
const BASE_URL=process.env.BASE_URL||'http://127.0.0.1:4175/';
const PHASE=process.env.PHASE||'depois';
const DIR=process.env.EVIDENCE_DIR||'/workspace/gediv-evidencias/clareza';
const OUT=path.join(DIR,PHASE);
const ROUTES=['geral','progressao','tempo','dia','historico','alteracoes','outras','cobertura','pendencias','gerencial'];
fs.mkdirSync(OUT,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true});
 const results=[],errors=[],pages=[];
 const check=async(name,fn)=>{try{const details=await fn();results.push({name,ok:true,details});console.log('PASS',name);}catch(e){results.push({name,ok:false,error:e.message});console.log('FAIL',name,e.message);}};
 const ready=async p=>{await p.waitForFunction(()=>document.querySelector('#pagina')?.getAttribute('aria-busy')==='false');};
 const shot=async(p,name,element)=>{if(element)await element.screenshot({path:path.join(OUT,name+'.png')});else{await p.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await p.screenshot({path:path.join(OUT,name+'-inteira.png'),fullPage:true});await p.screenshot({path:path.join(OUT,name+'-tela.png')});}};
 const create=async(theme,width)=>{const ctx=await browser.newContext({viewport:{width,height:960},colorScheme:theme==='escuro'?'dark':'light',timezoneId:'America/Sao_Paulo',locale:'pt-BR',acceptDownloads:true});const p=await ctx.newPage();p.setDefaultTimeout(10000);p.on('pageerror',e=>errors.push({theme,width,message:e.message}));await p.goto(BASE_URL+'#geral');await ready(p);pages.push({ctx,p,theme,width});return p;};
 const menu=async(p,width)=>{if(width<780)await p.locator('#abrirMenu').click();};
 for(const theme of ['claro','escuro'])for(const width of [1440,390]){
  const p=await create(theme,width),stem=theme+'-'+width;
  await check(stem+'-geral',async()=>{await shot(p,stem+'-geral');return {theme:await p.locator('html').getAttribute('data-theme'),width:await p.evaluate(()=>({inner:innerWidth,scroll:document.documentElement.scrollWidth}))};});
  await check(stem+'-tabela',async()=>{await shot(p,stem+'-tabela',p.locator('.records'));});
  await check(stem+'-calendario',async()=>{await menu(p,width);await p.locator('#abrirCalendario').click();await p.locator('#gedivCalendario:visible').waitFor();await p.locator('#gedivCalInicio').fill('2026-10-01');await p.locator('#gedivCalFim').fill('2026-11-30');await p.locator('#gedivCalInicio').focus();await p.screenshot({path:path.join(OUT,stem+'-calendario-tela.png')});await shot(p,stem+'-calendario',p.locator('#gedivCalendario'));await p.locator('.gediv-cal-actions [data-cal-close]').click();if(width<780)await p.keyboard.press('Escape');});
  await check(stem+'-filtro-GAJ',async()=>{await menu(p,width);await p.locator('#grupo').selectOption('GAJ');await p.locator('button[form="filtros"]').click();await shot(p,stem+'-filtro-GAJ');});
  await check(stem+'-modal',async()=>{await p.locator('.records [data-detalhe]').first().click();await p.screenshot({path:path.join(OUT,stem+'-modal-tela.png')});await shot(p,stem+'-modal',p.locator('#detalhe'));await p.locator('#fecharDetalhe').click();});
  await check(stem+'-menu',async()=>{if(width<780){await p.locator('#abrirMenu').click();await p.screenshot({path:path.join(OUT,stem+'-menu-expandido.png')});await p.keyboard.press('Escape');await p.screenshot({path:path.join(OUT,stem+'-menu-recolhido.png')});}else{await p.locator('#recolherMenu').click();await shot(p,stem+'-menu-recolhido');await p.locator('#expandirMenuTrilho').click();}});
  if(width===1440)for(const route of ROUTES){await check(theme+'-rota-'+route,async()=>{await p.goto(BASE_URL+'#'+route);await ready(p);await shot(p,theme+'-rota-'+route);assert.ok(!(await p.locator('#pagina').innerText()).includes('NaN'));const semantic=await p.evaluate(()=>{const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);const duplicates=ids.filter((id,i)=>ids.indexOf(id)!==i);const unnamed=[...document.querySelectorAll('input:not([type=hidden]),select,textarea')].filter(e=>e.getClientRects().length&&!e.labels?.length&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')).map(e=>e.id||e.tagName);return {duplicates,unnamed};});assert.deepEqual(semantic.duplicates,[]);assert.deepEqual(semantic.unnamed,[]);return {title:await p.locator('#tituloPagina').innerText(),...semantic};});}
  await p.context().close();
 }
 if(PHASE!=='antes'){
  for(const theme of ['claro','escuro']){
   const p=await create(theme,1440);
   await check(theme+'-teclado-foco',async()=>{
    await p.keyboard.press('Tab');const focus=await p.evaluate(()=>{const el=document.activeElement,s=getComputedStyle(el);return {tag:el.tagName,text:el.textContent.trim(),outline:s.outlineStyle,width:s.outlineWidth,shadow:s.boxShadow};});assert.ok(focus.tag!=='BODY');assert.ok(focus.outline!=='none'||focus.shadow!=='none');await p.screenshot({path:path.join(OUT,theme+'-foco-teclado.png')});
    await p.locator('#abrirCalendario').focus();await p.keyboard.press('Enter');await p.locator('#gedivCalendario:visible').waitFor();assert.equal(await p.evaluate(()=>document.activeElement.id),'gedivCalInicio');await p.keyboard.press('Escape');assert.equal(await p.evaluate(()=>document.activeElement.id),'abrirCalendario');
    await p.locator('.donut-legend [data-serie="VERTICAL"]').first().focus();await p.keyboard.press('Enter');assert.equal(await p.locator('#modalidade').inputValue(),'VERTICAL');await p.locator('.records [data-detalhe]').first().focus();await p.keyboard.press('Enter');assert.equal(await p.locator('#detalhe').evaluate(e=>e.open),true);await p.keyboard.press('Escape');return focus;
   });
   await check(theme+'-alvos-principais',async()=>{
    const targets=await p.evaluate(()=>['#abrirCalendario','#limpar','button[form="filtros"]','#tema'].map(sel=>{const e=document.querySelector(sel),r=e.getBoundingClientRect();return {selector:sel,width:r.width,height:r.height};}));
    await p.locator('#abrirCalendario').click();const apply=await p.locator('#gedivCalAplicar').boundingBox();targets.push({selector:'#gedivCalAplicar',width:apply.width,height:apply.height});await p.keyboard.press('Escape');for(const target of targets)assert.ok(target.width>=43.5&&target.height>=43.5,JSON.stringify(target));return targets;
   });
   await check(theme+'-estado-vazio',async()=>{await p.locator('#limpar').click();await p.locator('#grupo').selectOption('FAP');await p.locator('button[form="filtros"]').click();assert.equal(await p.locator('.exec-kpi-card .exec-kpi-value').first().innerText(),'—');await shot(p,theme+'-estado-vazio');});
   await check(theme+'-erro-recuperacao',async()=>{await p.route('**/dados.json',r=>r.fulfill({status:503,body:'Indisponível'}));await p.locator('#atualizar').click();await p.locator('#erro:visible').waitFor();assert.equal(await p.locator('#exportarCsv').isDisabled(),true);assert.ok(!(await p.locator('#indicadores').innerText()).includes('210–214'));await shot(p,theme+'-estado-erro');await p.unroute('**/dados.json');await p.locator('#tentarNovamente').click();await ready(p);assert.equal(await p.locator('#erro').isVisible(),false);});
   await p.context().close();
   const zoomContext=await browser.newContext({viewport:{width:720,height:480},deviceScaleFactor:2,colorScheme:theme==='escuro'?'dark':'light',timezoneId:'America/Sao_Paulo',locale:'pt-BR'}),z=await zoomContext.newPage();z.setDefaultTimeout(10000);z.on('pageerror',e=>errors.push({theme,width:720,message:e.message}));
   await check(theme+'-zoom200-reflow-equivalente',async()=>{await z.goto(BASE_URL+'#geral');await ready(z);const dims=await z.evaluate(()=>({cssWidth:innerWidth,scroll:document.documentElement.scrollWidth,pixelRatio:devicePixelRatio}));assert.equal(dims.cssWidth,720);assert.equal(dims.pixelRatio,2);assert.ok(dims.scroll<=721);await shot(z,theme+'-zoom200-reflow');return {method:'Equivalência de reflow: janela1440px a200% representada por720CSSpx e DPR2; não opera zoom nativo do Chrome.',...dims};});await zoomContext.close();
  }
  for(const theme of ['claro','escuro'])for(const width of [320,390,768,1280,1440]){
   const p=await create(theme,width);await check(theme+'-reflow-'+width,async()=>{await p.waitForFunction(()=>document.documentElement.scrollWidth<=innerWidth+1);const dims=await p.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));await shot(p,theme+'-reflow-'+width);assert.ok(dims.scroll<=dims.viewport+1);return dims;});await p.context().close();
  }
 }
 await browser.close();
 const files=fs.readdirSync(OUT).filter(n=>n.endsWith('.png')).map(name=>({name,sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(OUT,name))).digest('hex')}));
 const report={baseUrl:BASE_URL,phase:PHASE,checkedAt:new Date().toISOString(),results,errors,files};fs.writeFileSync(path.join(OUT,'resultados.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({phase:PHASE,passed:results.filter(x=>x.ok).length,failed:results.filter(x=>!x.ok).length,errors:errors.length,captures:files.length,out:OUT}));if(results.some(x=>!x.ok)||errors.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
