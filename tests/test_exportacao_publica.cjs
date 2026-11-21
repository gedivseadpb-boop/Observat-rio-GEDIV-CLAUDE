'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {criar}=require('../painel-publico/xlsx.js');

test('XLSX abre como ZIP independente e não contém fórmulas ou vínculos externos',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'gediv-xlsx-'));
  try {
    const file=path.join(dir,'teste.xlsx');
    fs.writeFileSync(file,criar([['Eixo','Faixa'],['Tempo de Serviço','5–9'],['<>&"','=1+1']]));
    const script=`import sys,zipfile,xml.etree.ElementTree as E
with zipfile.ZipFile(sys.argv[1]) as z:
 assert z.testzip() is None
 assert len(z.namelist())==5
 root=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
 ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
 values=[t.text for t in root.findall('.//m:t',ns)]
 assert values==['Eixo','Faixa','Tempo de Serviço','5–9','<>&"','=1+1']
 assert not root.findall('.//m:f',ns)
 assert not any('externalLink' in n for n in z.namelist())
`;
    execFileSync(process.env.PYTHON || 'python',['-c',script,file],{stdio:'pipe'});
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});

test('rejeita tabela inválida e suporta tabela vazia real',()=>{
  assert.throws(()=>criar({linhas:[]}),TypeError);
  assert.throws(()=>criar(['sem tabela']),TypeError);
  assert.ok(criar([]) instanceof Uint8Array);
});
