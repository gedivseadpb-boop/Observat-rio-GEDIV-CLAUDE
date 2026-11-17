'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {criar}=require('../painel-publico/pdf.js');
const M=require('../painel-publico/modelo.js');
const d=require('../painel-publico/dados.json');
test('PDF tem objetos, offsets, Unicode português e páginas consistentes',()=>{
 const rows=M.cellsToRows(d.celulas,d.catalogo);
 const pdf=Buffer.from(criar({metadados:[['Situação','Provisório · não verificado']],cabecalho:rows[0],linhas:rows.slice(1)}));
 const text=pdf.toString('latin1');
 assert.ok(text.startsWith('%PDF-1.4'));assert.ok(text.endsWith('%%EOF\n'));
 const xref=Number(text.match(/startxref\n(\d+)/)[1]);assert.equal(text.slice(xref,xref+4),'xref');
 const entries=text.slice(xref).split('\n').filter(l=>/^\d{10} 00000 n/.test(l));
 entries.forEach((line,i)=>assert.ok(text.slice(Number(line.slice(0,10))).startsWith((i+1)+' 0 obj')));
 assert.ok(!text.includes('/JavaScript'));assert.ok(!text.includes('/URI'));
 assert.ok(text.includes('/WinAnsiEncoding'));
});
test('PDF pagina tabelas longas sem truncar a última linha',()=>{
 const linhas=Array.from({length:400},(_,i)=>['Linha fictícia '+i,'Faixa 5–9']);
 const text=Buffer.from(criar({cabecalho:['Categoria','Faixa'],linhas})).toString('latin1');
 assert.ok(text.includes('Linha fictícia 399'));assert.ok(Number(text.match(/\/Count (\d+)/)[1])>1);
 assert.throws(()=>criar({cabecalho:['A'],linhas:[['A','B']]}),TypeError);
});
