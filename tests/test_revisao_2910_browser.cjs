'use strict';
/* CI isolado usa apenas a candidata pública empacotada; nunca SQLite/acervo. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');
const source=process.env.CANDIDATE_DIR,out=process.env.BROWSER_EVIDENCE;
if(!source||!out)throw Error('Informe CANDIDATE_DIR e BROWSER_EVIDENCE.');
fs.mkdirSync(out,{recursive:true});
(async()=>{const server=spawn('python',['-m','http.server','4191','--bind','127.0.0.1','--directory',source],{stdio:'ignore'});let browser;const results=[];
 try{
  for(let n=0;n<40;n++){try{if((await fetch('http://127.0.0.1:4191/')).ok)break}catch{}await new Promise(r=>setTimeout(r,100))}
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/google-chrome'});
  for(const width of [1440,390]){
   const ctx=await browser.newContext({viewport:{width,height:960},locale:'pt-BR',timezoneId:'America/Sao_Paulo',acceptDownloads:true});const p=await ctx.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(8000);
   await p.goto('http://127.0.0.1:4191/');await p.locator('#reportRoot[aria-busy=false]').waitFor();
   assert.equal(await p.locator('[data-card=decisions] .val').innerText(),'210–214');
   await p.screenshot({path:path.join(out,'geral-'+width+'.png'),fullPage:true});
   const dims=await p.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,id:e.id,cl:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).filter(e=>e.right>innerWidth+1&&e.width>0).slice(0,15)}));
   console.log('Reflow',JSON.stringify(dims));assert.ok(dims.scroll<=dims.width+1,JSON.stringify(dims));
   if(width<700)await p.locator('#expand').click();
   await p.locator('#group').selectOption('GAJ-1700');assert.equal(await p.locator('[data-card=decisions] .val').innerText(),'25–29');
   await p.locator('#from').fill('2026-11-01');await p.locator('#from').dispatchEvent('change');await p.locator('#to').fill('2026-11-30');await p.locator('#to').dispatchEvent('change');assert.equal(await p.locator('[data-card=decisions] .val').innerText(),'25–29');
   if(width<700)await p.locator('#collapse').click();
   for(const [id,ext,signature]of [['downloadCsv','csv',null],['downloadXlsx','xlsx','504b0304'],['downloadPng','png','89504e47']]){
    await p.locator('#downloadToggle').click();const d=p.waitForEvent('download');await p.locator('#'+id).click();const file=path.join(out,'GAJ-'+width+'.'+ext);await(await d).saveAs(file);const bytes=fs.readFileSync(file);assert.ok(bytes.length>100);if(signature)assert.equal(bytes.subarray(0,4).toString('hex'),signature);else{assert.match(bytes.toString(),/25–29/);assert.doesNotMatch(bytes.toString(),/Polícia Civil/)}await p.locator('#downloadToggle').click();
   }
   // PDF é o comando de impressão original, preservado. Captura a mesma saída para leitura.
   await p.locator('#downloadToggle').click();await p.evaluate(()=>window.print=()=>{});await p.locator('#downloadPdf').click();assert.match(await p.locator('#printReport').textContent(),/25–29/);await p.pdf({path:path.join(out,'GAJ-'+width+'.pdf'),printBackground:true});
   for(const view of ['vertical','horizontal','tempo','outras','hoje','historico','geral']){await p.locator('[data-view='+view+']').click();assert.ok(await p.locator('#viewTitle').innerText());await p.screenshot({path:path.join(out,view+'-'+width+'.png'),fullPage:true});}
   assert.deepEqual(errors,[]);results.push({width,passed:true,checks:'dados, recorte, datas nativas, CSV/XLSX/PNG/PDF, sete visões, reflow, execução JS'});await ctx.close();
  }
 }finally{await browser?.close();server.kill();fs.writeFileSync(path.join(out,'resultados.json'),JSON.stringify({results},null,2))}
 console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1});
