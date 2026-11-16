/* Exportação OOXML local: somente células textuais da projeção pública filtrada.
   Sem fórmulas, conexão externa, biblioteca remota ou dados do banco privado. */
(function (raiz) {
  'use strict';
  const encoder = new TextEncoder();
  const xml = v => String(v ?? '').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
  function coluna(n) { let r = ''; do { r = String.fromCharCode(65 + n % 26) + r; n = Math.floor(n / 26) - 1; } while (n >= 0); return r; }
  const tabelaCrc = Array.from({length: 256}, (_, n) => { let c = n; for (let k=0;k<8;k++) c = c & 1 ? 0xedb88320 ^ c >>> 1 : c >>> 1; return c >>> 0; });
  function crc32(bytes) { let c = 0xffffffff; for (const b of bytes) c = tabelaCrc[(c ^ b) & 255] ^ c >>> 8; return (c ^ 0xffffffff) >>> 0; }
  function juntar(partes) { const r = new Uint8Array(partes.reduce((n,p)=>n+p.length,0)); let o = 0; for (const p of partes) {r.set(p,o);o+=p.length;} return r; }
  function zip(arquivos) {
    const locais = [], centrais = []; let offset = 0;
    for (const [nome, texto] of arquivos) {
      const n=encoder.encode(nome), b=encoder.encode(texto), crc=crc32(b), l=new Uint8Array(30+n.length), v=new DataView(l.buffer);
      v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x0800,true);v.setUint16(12,33,true);v.setUint32(14,crc,true);v.setUint32(18,b.length,true);v.setUint32(22,b.length,true);v.setUint16(26,n.length,true);l.set(n,30);
      const c=new Uint8Array(46+n.length), d=new DataView(c.buffer);
      d.setUint32(0,0x02014b50,true);d.setUint16(4,20,true);d.setUint16(6,20,true);d.setUint16(8,0x0800,true);d.setUint16(14,33,true);d.setUint32(16,crc,true);d.setUint32(20,b.length,true);d.setUint32(24,b.length,true);d.setUint16(28,n.length,true);d.setUint32(42,offset,true);c.set(n,46);
      locais.push(l,b);centrais.push(c);offset+=l.length+b.length;
    }
    const central=juntar(centrais), end=new Uint8Array(22), e=new DataView(end.buffer);
    e.setUint32(0,0x06054b50,true);e.setUint16(8,arquivos.length,true);e.setUint16(10,arquivos.length,true);e.setUint32(12,central.length,true);e.setUint32(16,offset,true);
    return juntar([...locais,central,end]);
  }
  function criar(linhas) {
    if (!Array.isArray(linhas) || linhas.some(r=>!Array.isArray(r))) throw new TypeError('A exportação exige uma tabela de linhas.');
    const linhasXml=linhas.map((r,i)=>'<row r="'+(i+1)+'">'+r.map((v,j)=>'<c r="'+coluna(j)+(i+1)+'" t="inlineStr"><is><t xml:space="preserve">'+xml(v)+'</t></is></c>').join('')+'</row>').join('');
    const prefixo='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
    return zip([
      ['[Content_Types].xml',prefixo+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'],
      ['_rels/.rels',prefixo+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'],
      ['xl/workbook.xml',prefixo+'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="GEDIV agregados" sheetId="1" r:id="rId1"/></sheets></workbook>'],
      ['xl/_rels/workbook.xml.rels',prefixo+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'],
      ['xl/worksheets/sheet1.xml',prefixo+'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+linhasXml+'</sheetData></worksheet>']
    ]);
  }
  function baixar(linhas, nome='gediv-agregados.xlsx') {
    const url=URL.createObjectURL(new Blob([criar(linhas)],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
    const a=document.createElement('a');a.href=url;a.download=nome;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  const api={criar,baixar};raiz.GEDIVXLSX=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
