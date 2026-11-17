'use strict';
/* Nova interface (painel-v2): navegação, páginas distintas, estados honestos, privacidade, exportação e
   desativação reversível. Usa a MESMA projeção pública do painel atual; nada aqui altera painel-publico/. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');
const raiz = path.resolve(__dirname, '..');
const v2 = path.join(raiz, 'painel-v2'), atual = path.join(raiz, 'painel-publico');
const projecao = JSON.parse(fs.readFileSync(path.join(atual, 'dados.json'), 'utf8'));
const espera = (ms = 30) => new Promise(r => setTimeout(r, ms));

async function abrir(t, { hash = '#/inicio', dados = () => structuredClone(projecao), estado = { ativo: true }, falhaDados = false } = {}) {
  const erros = [], downloads = [];
  const consola = new VirtualConsole(); consola.on('jsdomError', e => erros.push(e));
  const dom = new JSDOM(fs.readFileSync(path.join(v2, 'index.html'), 'utf8'), { url: 'https://preview.invalid/painel-v2/' + hash, runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole: consola });
  const w = dom.window;
  w.TextEncoder = TextEncoder;
  w.matchMedia = () => ({ matches: false });
  w.fetch = async url => {
    if (String(url).includes('estado-site')) return estado === null ? { ok: false, status: 404, json: async () => ({}) } : { ok: true, json: async () => estado };
    if (falhaDados) return { ok: false, status: 503, json: async () => ({}) };
    return { ok: true, json: async () => dados() };
  };
  w.URL.createObjectURL = blob => { downloads.push(blob); return 'blob:teste'; };
  w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = function () {};
  w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  w.HTMLDialogElement.prototype.close = function () { this.open = false; };
  w.print = () => {};
  w.scrollTo = () => {};
  [[atual, 'modelo.js'], [atual, 'xlsx.js'], [atual, 'pdf.js'], [v2, 'graficos.js'], [v2, 'app.js']].forEach(([d, f]) => w.eval(fs.readFileSync(path.join(d, f), 'utf8')));
  await espera(60);
  t.after(() => { w.close(); assert.deepEqual(erros.map(e => e.message), []); });
  const ir = async h => { w.location.hash = h; w.dispatchEvent(new w.HashChangeEvent('hashchange')); await espera(); };
  const texto = () => w.document.getElementById('pagina').textContent;
  return { w, $: id => w.document.getElementById(id), ir, texto, downloads };
}

test('o painel atual não é tocado: painel-v2 só referencia os recursos compartilhados por caminho relativo', () => {
  const html = fs.readFileSync(path.join(v2, 'index.html'), 'utf8');
  assert.match(html, /content="\.\.\/painel-publico\/dados\.json"/);
  ['modelo.js', 'xlsx.js', 'pdf.js'].forEach(f => assert.ok(html.includes('../painel-publico/' + f)));
  assert.equal(fs.existsSync(path.join(v2, 'dados.json')), false, 'nenhuma segunda cópia da base');
});

test('Visão geral mostra cobertura, três indicadores sustentados e indicadores pendentes separados', async t => {
  const { texto, w } = await abrir(t);
  const p = texto();
  assert.match(p, /O que esta base cobre/);
  assert.match(p, /01\/10\/2026 a 14\/11\/2026/);
  assert.match(p, /Edições do Diário Oficial\s*19/); assert.match(p, /Páginas lidas\s*884/);
  assert.equal(w.document.querySelectorAll('.kpis .kpi').length, 3);
  assert.match(w.document.querySelector('.kpis').textContent, /210–214/);
  assert.match(w.document.querySelector('.kpis').textContent, /Zero confirmado/);
  assert.match(p, /Outros indicadores — aguardando dados/);
  assert.match(p, /Deferidos e indeferidos/);
  assert.ok(w.document.querySelectorAll('#pagina svg').length >= 2);
});

test('Visão geral, Progressão e Tempo de Serviço têm conteúdos diferentes (não a mesma tela com outro título)', async t => {
  const { texto, ir } = await abrir(t);
  const inicio = texto();
  await ir('#/progressao'); const prog = texto();
  await ir('#/tempo'); const tempo = texto();
  assert.notEqual(inicio, prog); assert.notEqual(prog, tempo);
  assert.match(prog, /Horizontal × Vertical/); assert.match(prog, /Por grupo ocupacional \(PCCR\)/);
  assert.doesNotMatch(prog, /Os sete serviços/);
  assert.match(tempo, /Os sete serviços/); assert.doesNotMatch(tempo, /Horizontal × Vertical/);
});

test('Tempo de Serviço sempre lista os sete serviços e distingue ausência de zero', async t => {
  const { w, $ } = await abrir(t, { hash: '#/tempo' });
  const cartoes = w.document.querySelectorAll('.servico');
  assert.equal(cartoes.length, 7);
  assert.deepEqual([...cartoes].map(c => c.querySelector('.servico-codigo').textContent), ['TS-01', 'TS-02', 'TS-03', 'TS-04', 'TS-05', 'TS-06', 'TS-07']);
  assert.ok([...cartoes].every(c => /Sem agregado publicável/.test(c.textContent)));
  assert.ok([...cartoes].every(c => !/\b0 decisões/.test(c.textContent)), 'ausência não vira zero');
  assert.match($('pagina').textContent, /Nenhum gráfico foi desenhado com números estimados/);
});

test('filtros vão para o endereço, sincronizam a página, aparecem como chips e podem ser limpos', async t => {
  const { w, $, ir, texto } = await abrir(t, { hash: '#/progressao' });
  await ir('#/progressao?mod=HORIZONTAL&grupo=GAJ&mes=2026-11');
  assert.equal($('filtroGrupo').value, 'GAJ'); assert.equal($('filtroMes').value, '2026-11');
  assert.match(w.document.querySelector('.filtros-ativos').textContent, /Modalidade: Horizontal/);
  assert.match(w.document.querySelector('.kpis').textContent, /25–29/);
  assert.match($('trilha').textContent, /Progressão Funcional.*Horizontal.*Apoio Judiciário/);
  $('limparFiltros').click(); w.dispatchEvent(new w.HashChangeEvent('hashchange')); await espera();
  assert.equal(w.location.hash, '#/progressao');
  assert.match(texto(), /190–194/);
});

test('valores inválidos no endereço são ignorados, sem recorte fictício', async t => {
  const { $ } = await abrir(t, { hash: '#/progressao?grupo=XYZ&mes=2025-01&mod=DIAGONAL' });
  assert.equal($('filtroGrupo').value, ''); assert.equal($('filtroMes').value, '');
  assert.match($('pagina').textContent, /Sem filtros/);
});

test('agregado nunca é chamado de ficha, resenha ou processo', async t => {
  const { w, $ } = await abrir(t);
  assert.doesNotMatch($('pagina').textContent, /ficha completa|Abrir ficha/i);
  w.document.querySelector('#pagina table button').click(); await espera();
  assert.equal($('dialogo').open, true);
  assert.equal($('dialogoTitulo').textContent, 'Entender este agregado');
  assert.match($('dialogoCorpo').textContent, /Não é uma resenha, um processo nem uma ficha individual/);
});

test('Publicações do dia: data dentro do período não ganha total diário falso; fora do período é dito', async t => {
  const { texto, ir } = await abrir(t, { hash: '#/dia?dia=2026-11-05' });
  assert.match(texto(), /Não há como dizer quantas decisões saíram no dia 05\/11\/2026/);
  assert.match(texto(), /Ver novembro de 2026/);
  await ir('#/dia?dia=2026-03-10');
  assert.match(texto(), /fora do período lido/);
  assert.doesNotMatch(texto(), /0 publicações/);
});

test('área gerencial é indisponível de verdade: sem formulário de senha nem dado individual', async t => {
  const { w, texto } = await abrir(t, { hash: '#/gerencial' });
  assert.match(texto(), /Indisponível nesta versão pública/);
  assert.equal(w.document.querySelectorAll('#pagina input, #pagina form').length, 0);
});

test('todas as rotas abrem sem erro e com título próprio', async t => {
  const { w, ir } = await abrir(t);
  const titulos = new Set();
  for (const r of ['inicio', 'progressao', 'tempo', 'edicoes', 'dia', 'historico', 'alteracoes', 'outras', 'ajuda', 'gerencial']) {
    await ir('#/' + r);
    titulos.add(w.document.getElementById('tituloPagina').textContent);
    assert.equal(w.document.querySelector('#menuPrincipal a[aria-current="page"]').dataset.rota, r);
  }
  assert.equal(titulos.size, 10);
});

test('falha de carga não mostra números antigos e permite tentar de novo', async t => {
  let falhar = true;
  const { $, w } = await abrir(t, { falhaDados: false, dados: () => { if (falhar) throw new Error('rede'); return structuredClone(projecao); } });
  assert.equal($('falha').hidden, false);
  assert.equal($('pagina').children.length, 0);
  assert.equal(w.document.querySelectorAll('.exportar button').length, 0);
  falhar = false; $('tentarDeNovo').click(); await espera(60);
  assert.equal($('falha').hidden, true);
  assert.match($('pagina').textContent, /210–214/);
});

test('projeção fora do contrato público é recusada pelo mesmo validador do painel atual', async t => {
  const { $ } = await abrir(t, { dados: () => ({ ...structuredClone(projecao), celulas: [{ ...projecao.celulas[0], nome: 'PESSOA' }] }) });
  assert.equal($('falha').hidden, false);
  assert.equal($('pagina').children.length, 0);
});

test('exportações levam o recorte, a cobertura e o aviso de faixas, sem campos individuais', async t => {
  const { w, downloads } = await abrir(t, { hash: '#/progressao?mod=VERTICAL' });
  const [csv, xlsx, pdf] = [...w.document.querySelectorAll('.exportar button')];
  csv.click(); xlsx.click(); pdf.click();
  assert.equal(downloads.length, 3);
  const texto = await new Promise(r => { const f = new w.FileReader(); f.onload = () => r(f.result); f.readAsText(downloads[0]); });
  assert.match(texto, /Recorte: Progressão Funcional · Vertical/);
  assert.match(texto, /Cobertura: 01\/10\/2026 a 14\/11\/2026/);
  assert.match(texto, /Faixas não são contagens exatas/);
  assert.doesNotMatch(texto, /matr[ií]cula|processo n|SAD-PSE/i);
  assert.ok(texto.split('\r\n').slice(7).every(l => /Vertical/.test(l)), 'só linhas do recorte filtrado');
});

test('desativação reversível: com ativo=false o painel mostra só o aviso; o arquivo ausente mantém o site ativo', async t => {
  const des = await abrir(t, { estado: { ativo: false, mensagem: 'Manutenção programada.', desde: '17/11/2026' } });
  assert.equal(des.$('desativado').hidden, false);
  assert.match(des.$('desativado').textContent, /Manutenção programada\./);
  assert.equal(des.$('pagina').children.length, 0);
  const ausente = await abrir(t, { estado: null });
  assert.equal(ausente.$('desativado').hidden, true);
  assert.match(ausente.$('pagina').textContent, /210–214/);
});

test('mensagem de desativação é texto, nunca HTML', async t => {
  const { $ } = await abrir(t, { estado: { ativo: false, mensagem: '<img src=x onerror=alert(1)>' } });
  assert.equal($('desativado').querySelectorAll('img').length, 0);
  assert.match($('desativado').textContent, /<img/);
});

test('o pacote da nova interface não contém dados pessoais nem números fixos da base', () => {
  const codigo = ['index.html', 'app.js', 'graficos.js', 'estilo.css'].map(f => fs.readFileSync(path.join(v2, f), 'utf8')).join('\n');
  assert.doesNotMatch(codigo, /SAD-PSE-\d|\d{3}\.\d{3}-\d|\d{6}-\d/);
  ['210–214', '190–194', '884'].forEach(n => assert.ok(!codigo.includes(n), 'número da base fixo no código: ' + n));
});
