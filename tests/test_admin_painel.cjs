'use strict';
/* Painel do admin (/admin-painel): página estática SEM dados; login e dados só pelo servidor gerencial.
   Servidor simulado com dados SINTÉTICOS. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');
const pasta = path.resolve(__dirname, '..', 'painel-v2', 'admin-painel');
const espera = (ms = 40) => new Promise(r => setTimeout(r, ms));
const resposta = (status, corpo) => ({ ok: status < 400, status, json: async () => corpo, headers: { get: () => null }, blob: async () => new Blob(['x']) });

const PAINEL = {
  apoio: { decisoes_pendentes: 2, decisoes_conferidas: 5, decisoes_rejeitadas: 0, conflitos_abertos: 0 },
  resenhas: [{ ato_id: 'a'.repeat(20), resenha: '900/2026', data: '2026-10-15', pagina: 1, eixo: 'TEMPO_SERVICO', modalidade: null, grupo: 'TS-06', subcategoria: null, decisoes: 2, vinculo: 'EXPRESSO', conflito_aberto: false }],
};

async function abrir(t, { config = { api: 'https://api.exemplo.invalid' }, guardada = null, servidor } = {}) {
  const erros = [], chamadas = [];
  const consola = new VirtualConsole(); consola.on('jsdomError', e => erros.push(e));
  const dom = new JSDOM(fs.readFileSync(path.join(pasta, 'index.html'), 'utf8'), { url: 'https://preview.invalid/painel-v2/admin-painel/', runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole: consola });
  const w = dom.window;
  if (guardada) w.sessionStorage.setItem('gediv-admin-sessao', JSON.stringify(guardada));
  w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  w.HTMLDialogElement.prototype.close = function () { this.open = false; };
  w.fetch = async (url, opcoes = {}) => {
    url = String(url);
    if (url.endsWith('config.json')) return resposta(200, config);
    chamadas.push({ url, metodo: opcoes.method || 'GET', auth: (opcoes.headers || {}).Authorization, corpo: opcoes.body ? JSON.parse(opcoes.body) : undefined });
    return (servidor || (() => resposta(404, { erro: 'rota inexistente' })))(url, opcoes);
  };
  w.eval(fs.readFileSync(path.join(pasta, 'admin.js'), 'utf8'));
  await espera(80);
  t.after(() => { w.close(); assert.deepEqual(erros.map(e => e.message), []); });
  return { w, $: id => w.document.getElementById(id), chamadas };
}

function servidorFicticio() {
  return (url, opcoes) => {
    const rota = url.replace('https://api.exemplo.invalid', '');
    const auth = (opcoes.headers || {}).Authorization;
    if (rota === '/api/login') {
      const c = JSON.parse(opcoes.body);
      return c.usuario === 'teste.admin' && c.senha === 'senha-correta-1'
        ? resposta(200, { token: 'tok-1', usuario: 'teste.admin', nome: 'Pessoa de Teste (teste.admin)', expira_em: '2099-01-01T00:00:00+00:00' })
        : resposta(401, { erro: 'usuário ou senha inválidos, ou acesso bloqueado temporariamente' });
    }
    if (auth !== 'Bearer tok-1') return resposta(401, { erro: 'sessão inexistente ou expirada' });
    if (rota === '/api/sessao') return resposta(200, { usuario: 'teste.admin', nome: 'Pessoa de Teste (teste.admin)', expira_em: '2099-01-01T00:00:00+00:00' });
    if (rota.startsWith('/api/painel')) return resposta(200, PAINEL);
    if (rota === '/api/logout') return resposta(200, { ok: true });
    return resposta(404, { erro: 'rota inexistente' });
  };
}

test('arquivos estáticos do admin não contêm dados, senhas nem endereço de servidor', () => {
  const tudo = fs.readdirSync(pasta).map(f => fs.readFileSync(path.join(pasta, f), 'utf8')).join('\n');
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(pasta, 'config.json'), 'utf8')), { api: '' });
  assert.doesNotMatch(tudo, /dados\.json|\d{3}\.\d{3}-\d|matr[ií]cula\s*[:=]\s*\d/i);
  assert.doesNotMatch(tudo, /senha\s*[:=]\s*['"][^'"]+['"]/i, 'nenhuma senha embutida');
  assert.doesNotMatch(tudo, /innerHTML|outerHTML|insertAdjacentHTML|document\.write/);
  assert.match(fs.readFileSync(path.join(pasta, 'index.html'), 'utf8'), /noindex/);
});

test('sem servidor configurado: aviso claro e formulário desligado, sem nenhuma chamada', async t => {
  const { $, chamadas } = await abrir(t, { config: { api: '' } });
  assert.match($('aviso').textContent, /ainda não foi configurado/);
  assert.equal($('entrar').disabled, true);
  assert.equal(chamadas.length, 0);
});

test('endereço de API inseguro (http fora do próprio computador) é recusado', async t => {
  const { $, chamadas } = await abrir(t, { config: { api: 'http://servidor.exemplo.invalid' } });
  assert.match($('aviso').textContent, /ainda não foi configurado/);
  assert.equal(chamadas.length, 0);
});

test('login errado mostra mensagem genérica e não guarda nada', async t => {
  const { w, $ } = await abrir(t, { servidor: servidorFicticio() });
  assert.equal($('telaLogin').hidden, false);
  $('usuario').value = 'teste.admin'; $('senha').value = 'errada-errada';
  $('formLogin').dispatchEvent(new w.Event('submit', { cancelable: true })); await espera();
  assert.match($('erroLogin').textContent, /inválidos/);
  assert.equal($('senha').value, '');
  assert.equal(w.sessionStorage.getItem('gediv-admin-sessao'), null);
  assert.equal($('telaApp').hidden, true);
});

test('login certo abre a fila com o token no cabeçalho; sair apaga a sessão', async t => {
  const { w, $, chamadas } = await abrir(t, { servidor: servidorFicticio() });
  $('usuario').value = 'teste.admin'; $('senha').value = 'senha-correta-1';
  $('formLogin').dispatchEvent(new w.Event('submit', { cancelable: true })); await espera(80);
  assert.equal($('telaApp').hidden, false);
  assert.match($('quemEsta').textContent, /Pessoa de Teste/);
  assert.match($('area').textContent, /Resenha 900\/2026/);
  assert.doesNotMatch($('area').textContent, /\bnull\b|undefined|NaN/);
  const painel = chamadas.find(c => c.url.includes('/api/painel'));
  assert.equal(painel.auth, 'Bearer tok-1');
  assert.equal($('senha').value, '');
  $('sair').click(); await espera(60);
  assert.equal(w.sessionStorage.getItem('gediv-admin-sessao'), null);
  assert.equal($('telaLogin').hidden, false);
  assert.ok(chamadas.some(c => c.url.endsWith('/api/logout') && c.metodo === 'POST'));
});

test('sessão guardada expirada volta ao login com aviso', async t => {
  const { w, $ } = await abrir(t, { guardada: { token: 'velho', nome: 'X' }, servidor: servidorFicticio() });
  assert.equal($('telaLogin').hidden, false);
  assert.match($('erroLogin').textContent, /sessão terminou/);
  assert.equal(w.sessionStorage.getItem('gediv-admin-sessao'), null);
});
