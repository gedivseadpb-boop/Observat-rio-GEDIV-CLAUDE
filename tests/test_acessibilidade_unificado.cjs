'use strict';
/**
 * Verificação automatizada de acessibilidade estrutural e semântica do Painel Unificado GEDIV
 * (`observatorio/web/unificado/index.html`) — executável no CI via `npm test` (jsdom, sem navegador).
 */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = path.join(__dirname, '..');
const htmlPath = path.join(root, 'observatorio', 'web', 'unificado', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

function parseDom() {
  return new JSDOM(html);
}

test('Painel Unificado: documento possui idioma pt-BR, título e marcos semânticos', () => {
  const dom = parseDom();
  try {
    const doc = dom.window.document;
    assert.equal(doc.documentElement.getAttribute('lang'), 'pt-BR');
    assert.ok(doc.title && doc.title.trim().length > 5, 'Título do documento ausente');
    assert.ok(doc.querySelector('header'), 'Landmark <header> ausente');
    assert.ok(doc.querySelector('main'), 'Landmark <main> ausente');
    assert.ok(doc.querySelector('aside'), 'Landmark <aside> ausente');
    assert.ok(doc.querySelector('h1'), 'Cabeçalho principal <h1> ausente');
  } finally {
    dom.window.close();
  }
});

test('Painel Unificado: todos os <dialog> possuem aria-labelledby válido apontando para título existente', () => {
  const dom = parseDom();
  try {
    const doc = dom.window.document;
    const dialogs = [...doc.querySelectorAll('dialog')];
    assert.ok(dialogs.length >= 5, `Esperava >= 5 diálogos, encontrados ${dialogs.length}`);
    for (const dlg of dialogs) {
      const refId = dlg.getAttribute('aria-labelledby');
      assert.ok(refId, `Dialog #${dlg.id || '(sem id)'} sem aria-labelledby`);
      // docModalTitle é preenchido dinamicamente ao abrir openDocModal; demais existem estaticamente
      if (dlg.id !== 'docModal') {
        assert.ok(doc.getElementById(refId), `aria-labelledby="${refId}" em #${dlg.id} não aponta para elemento existente`);
      }
    }
  } finally {
    dom.window.close();
  }
});

test('Painel Unificado: todos os campos de formulário (input/select/textarea) possuem rótulo acessível', () => {
  const dom = parseDom();
  try {
    const doc = dom.window.document;
    const fields = [...doc.querySelectorAll('input, select, textarea')].filter(
      (el) => (el.getAttribute('type') || '').toLowerCase() !== 'hidden'
    );
    assert.ok(fields.length >= 15, `Poucos campos de formulário encontrados: ${fields.length}`);
    for (const el of fields) {
      const hasAria = Boolean(el.getAttribute('aria-label') || el.getAttribute('aria-labelledby'));
      const insideLabel = Boolean(el.closest('label'));
      const explicitLabel = Boolean(el.id && doc.querySelector(`label[for="${el.id}"]`));
      assert.ok(
        hasAria || insideLabel || explicitLabel,
        `Campo sem rótulo acessível: <${el.tagName.toLowerCase()} id="${el.id || ''}" type="${el.getAttribute('type') || ''}">`
      );
    }
  } finally {
    dom.window.close();
  }
});

test('Painel Unificado: ausência de tabindex positivo e presença de indicadores :focus-visible no CSS', () => {
  const dom = parseDom();
  try {
    const doc = dom.window.document;
    const positiveTab = [...doc.querySelectorAll('[tabindex]')].filter(
      (el) => Number(el.getAttribute('tabindex')) > 0
    );
    assert.deepEqual(
      positiveTab.map((el) => el.outerHTML.slice(0, 80)),
      [],
      'Não use tabindex positivo (quebra ordem natural de Tab/Shift+Tab)'
    );
    assert.match(html, /:focus-visible\s*\{[^}]*outline\s*:/i, 'CSS deve definir outline visível em :focus-visible');
  } finally {
    dom.window.close();
  }
});

test('Painel Unificado: botões de ícone e grupos de controles possuem atributos ARIA adequados', () => {
  const dom = parseDom();
  try {
    const doc = dom.window.document;
    const iconBtns = [...doc.querySelectorAll('button.icon-btn, button.doc-close-btn')];
    assert.ok(iconBtns.length >= 4, 'Esperava botões de ícone/fechamento');
    for (const btn of iconBtns) {
      assert.ok(
        btn.getAttribute('aria-label'),
        `Botão de ícone sem aria-label: #${btn.id || btn.className}`
      );
    }
    const switches = [...doc.querySelectorAll('.metric-switch')];
    assert.ok(switches.length >= 4, 'Esperava switches de métrica Quantidade/%');
    for (const sw of switches) {
      assert.equal(sw.getAttribute('role'), 'group');
      assert.ok(sw.getAttribute('aria-label'), 'metric-switch sem aria-label');
      const btns = [...sw.querySelectorAll('button')];
      assert.equal(btns.length, 2);
      for (const b of btns) {
        assert.ok(['true', 'false'].includes(b.getAttribute('aria-pressed')), 'Botão de switch sem aria-pressed');
      }
    }
    assert.ok(doc.getElementById('activeFilters')?.getAttribute('aria-label'), '#activeFilters sem aria-label');
    assert.ok(doc.getElementById('levelChart'), '#levelChart ausente');
    assert.match(html, /aria-pressed="/, 'Botões selecionáveis de nível/filtro devem expor aria-pressed');
  } finally {
    dom.window.close();
  }
});
