/* Relatório PDF local, sem rede, código executável ou dados individuais.
   PDF 1.4, páginas A4 paisagem, Helvetica/WinAnsi, tabela paginada. */
(function (root) {
  'use strict';
  const replacements = { '→': '->', '↗': '->', '↓': '', '↑': '', '✓': '', '✕': '', '◇': '' };
  const winAnsi = { '€': 128, '‚': 130, 'ƒ': 131, '„': 132, '…': 133, '†': 134, '‡': 135, 'ˆ': 136, '‰': 137, 'Š': 138, '‹': 139, 'Œ': 140, 'Ž': 142, '‘': 145, '’': 146, '“': 147, '”': 148, '•': 149, '–': 150, '—': 151, '˜': 152, '™': 153, 'š': 154, '›': 155, 'œ': 156, 'ž': 158, 'Ÿ': 159 };
  const printable = text => String(text ?? '').normalize('NFC').replace(/[→↗↓↑✓✕◇]/g, c => replacements[c]).replace(/[\x00-\x1f]/g, ' ');
  function bytes(text) { return Uint8Array.from([...text].map(c => c.charCodeAt(0))); }
  function literal(value) {
    return [...printable(value)].map(c => {
      const n = winAnsi[c] || (c.charCodeAt(0) <= 255 ? c.charCodeAt(0) : 63);
      const v = String.fromCharCode(n);
      return /[\\()]/.test(v) ? '\\' + v : v;
    }).join('');
  }
  function wrap(text, width, size) {
    const limit = Math.max(5, Math.floor(width / (size * .56))), lines = [];
    let line = '';
    for (const word of printable(text).split(/\s+/)) {
      if (line && line.length + word.length + 1 > limit) { lines.push(line); line = ''; }
      let rest = word;
      while (rest.length > limit) { if (line) { lines.push(line); line = ''; } lines.push(rest.slice(0, limit)); rest = rest.slice(limit); }
      if (rest) line += (line ? ' ' : '') + rest;
    }
    if (line || !lines.length) lines.push(line);
    return lines;
  }
  function criar({ titulo = 'Painel Diário Oficial | GEDIV', metadados = [], cabecalho = [], linhas = [] } = {}) {
    if (!Array.isArray(metadados) || !Array.isArray(cabecalho) || !Array.isArray(linhas) || linhas.some(r => !Array.isArray(r) || r.length !== cabecalho.length)) throw new TypeError('Tabela PDF inválida');
    if (cabecalho.length > 12 || cabecalho.length < 1) throw new TypeError('Informe de 1 a 12 colunas');
    const W = 842, H = 595, margin = 28, totalWidth = W - 2 * margin;
    const ratios = cabecalho.length === 9 ? [65, 85, 65, 85, 125, 65, 75, 65, 156] : cabecalho.map(() => 1);
    const ratioTotal = ratios.reduce((a, b) => a + b, 0), widths = ratios.map(v => totalWidth * v / ratioTotal);
    const pages = []; let stream = '', y = H - margin, pageNumber = 0;
    const text = (value, x, top, size = 8, bold = false) => { stream += 'BT /' + (bold ? 'F2' : 'F1') + ' ' + size + ' Tf 1 0 0 1 ' + x.toFixed(2) + ' ' + (top - size).toFixed(2) + ' Tm (' + literal(value) + ') Tj ET\n'; };
    const finish = () => { text('GEDIV · Agregados públicos protegidos · Não substitui a publicação oficial', margin, 22, 7); text('Página ' + pageNumber, W - 78, 22, 7); pages.push(stream); };
    const start = () => { pageNumber++; stream = '0.08 0.19 0.32 rg 0.75 0.81 0.87 RG 0.4 w\n'; y = H - margin; text(titulo, margin, y, 17, true); y -= 27; };
    const drawRow = (row, header = false) => {
      const size = header ? 7 : 7.5, lineHeight = 10, cells = row.map((v, i) => wrap(v, widths[i] - 10, size));
      const maxLines = Math.max(...cells.map(c => c.length));
      // Uma célula grande continua em páginas seguintes, sem truncar registros.
      let offset = 0;
      while (offset < maxLines) {
        let space = Math.floor((y - margin - 16) / lineHeight) - 1;
        if (space < 1) { finish(); start(); if (!header) drawRow(cabecalho, true); space = Math.floor((y - margin - 16) / lineHeight) - 1; }
        if (offset === 0 && maxLines < 35 && maxLines > space) { finish(); start(); if (!header) drawRow(cabecalho, true); space = Math.floor((y - margin - 16) / lineHeight) - 1; }
        const count = Math.min(maxLines - offset, Math.max(1, space)), height = count * lineHeight + 10;
        if (header) stream += '0.92 0.95 0.99 rg ' + margin + ' ' + (y - height).toFixed(2) + ' ' + totalWidth + ' ' + height + ' re f 0.08 0.19 0.32 rg\n';
        let x = margin;
        cells.forEach((lines, i) => { stream += x.toFixed(2) + ' ' + (y - height).toFixed(2) + ' ' + widths[i].toFixed(2) + ' ' + height + ' re S\n'; lines.slice(offset, offset + count).forEach((line, k) => text(line, x + 5, y - 5 - k * lineHeight, size, header)); x += widths[i]; });
        y -= height; offset += count;
        if (offset < maxLines) { finish(); start(); if (!header) drawRow(cabecalho, true); }
      }
    };
    start();
    for (const entry of metadados) {
      for (const line of wrap(Array.isArray(entry) ? entry.join(': ') : entry, totalWidth, 8)) {
        if (y < margin + 45) { finish(); start(); }
        text(line, margin, y, 8); y -= 12;
      }
      y -= 3;
    }
    y -= 10; drawRow(cabecalho, true);
    if (linhas.length) linhas.forEach(row => drawRow(row));
    else { y -= 15; text('Sem agregado publicável neste recorte; isso não equivale a zero publicações.', margin, y); }
    finish();
    const objects = [];
    objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
    objects[2] = '<< /Type /Pages /Count ' + pages.length + ' /Kids [' + pages.map((_, i) => (5 + i * 2) + ' 0 R').join(' ') + '] >>';
    objects[3] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>';
    objects[4] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>';
    pages.forEach((content, i) => { const id = 5 + i * 2; objects[id] = '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' + W + ' ' + H + '] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ' + (id + 1) + ' 0 R >>'; objects[id + 1] = '<< /Length ' + content.length + ' >>\nstream\n' + content + 'endstream'; });
    let output = '%PDF-1.4\n%\xE2\xE3\xCF\xD3\n'; const offsets = [0];
    for (let i = 1; i < objects.length; i++) { offsets[i] = output.length; output += i + ' 0 obj\n' + objects[i] + '\nendobj\n'; }
    const xref = output.length;
    output += 'xref\n0 ' + objects.length + '\n0000000000 65535 f \n' + offsets.slice(1).map(n => String(n).padStart(10, '0') + ' 00000 n \n').join('') + 'trailer\n<< /Size ' + objects.length + ' /Root 1 0 R >>\nstartxref\n' + xref + '\n%%EOF\n';
    return bytes(output);
  }
  function baixar(report, nome = 'GEDIV_agregados_publicos.pdf') {
    const url = URL.createObjectURL(new Blob([criar(report)], { type: 'application/pdf' })), a = document.createElement('a');
    a.href = url; a.download = nome; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const api = { criar, baixar };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.GEDIVPDF = api;
})(typeof window !== 'undefined' ? window : globalThis);
