'use strict';
/* Auditoria de cores efetivamente renderizadas. Não substitui revisão visual,
   avaliação por usuários, nem certifica WCAG integralmente. Sem alteração do site. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:4175/';
const OUT = process.env.CONTRAST_OUT || path.resolve('..', 'gediv-evidencias/clareza/contraste');
const ROUTES = ['geral', 'progressao', 'tempo', 'dia', 'historico', 'alteracoes', 'outras', 'cobertura', 'pendencias', 'gerencial'];
const snapshots = [];

function collectPaintedContrast() {
  const rgb = value => {
    if (!value || value === 'none' || value === 'transparent') return [0, 0, 0, 0];
    const m = value.match(/^rgba?\(([^)]+)\)$/);
    if (!m) return null;
    const v = m[1].replace(/\//g, ' ').replace(/,/g, ' ').trim().split(/\s+/).map(Number);
    return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1];
  };
  const over = (fg, bg) => {
    const a = fg[3] + bg[3] * (1 - fg[3]);
    if (!a) return [0, 0, 0, 0];
    return [0, 1, 2].map(i => (fg[i] * fg[3] + bg[i] * bg[3] * (1 - fg[3])) / a).concat(a);
  };
  const luminance = c => c.slice(0, 3).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((n, v, i) => n + v * [.2126, .7152, .0722][i], 0);
  const ratio = (a, b) => { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const hex = c => '#' + c.slice(0, 3).map(n => Math.round(n).toString(16).padStart(2, '0')).join('');
  const descriptor = el => {
    if (el.id) return '#' + el.id;
    const parent = el.closest('[id]');
    return (parent ? '#' + parent.id + ' ' : '') + el.tagName.toLowerCase() + (el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 3).map(c => '.' + c).join('');
  };
  const visible = el => {
    if (el.closest('[hidden], dialog:not([open]), [inert]')) return false;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    for (let p = el; p; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (s.display === 'none' || s.visibility !== 'visible' || Number(s.opacity) === 0) return false;
      if (s.clip === 'rect(0px, 0px, 0px, 0px)' || s.clipPath === 'inset(50%)') return false;
      if (p.tagName === 'DETAILS' && !p.open && !p.querySelector('summary')?.contains(el)) return false;
    }
    return true;
  };
  function background(el, includeSelf = true) {
    const chain = [];
    for (let p = includeSelf ? el : el.parentElement; p; p = p.parentElement) chain.unshift(p);
    let paint = [255, 255, 255, 1];
    let gradients = [];
    for (const p of chain) {
      const s = getComputedStyle(p), color = rgb(s.backgroundColor);
      if (color) { paint = over(color, paint); if (color[3] === 1) gradients = []; }
      if (s.backgroundImage !== 'none') gradients.push(s.backgroundImage);
    }
    return { color: paint, gradients };
  }
  const results = [], manual = [];
  function measure(el, label, fg, bg, minimum, kind, extra = {}) {
    if (!fg || !bg.color) { manual.push({ selector: descriptor(el), kind, reason: 'Cor não RGB ou não resolvida', label }); return; }
    const opacity = (() => { let n = 1; for (let p = el; p; p = p.parentElement) n *= Number(getComputedStyle(p).opacity); return n; })();
    const disabled = el.matches(':disabled') || !!el.closest('[aria-disabled="true"]');
    const color = over([fg[0], fg[1], fg[2], fg[3] * opacity], bg.color);
    const actual = ratio(color, bg.color);
    const item = { selector: descriptor(el), kind, label: String(label).trim().slice(0, 110), foreground: hex(color), background: hex(bg.color), ratio: +actual.toFixed(3), minimum, passed: actual + .001 >= minimum, disabled, ...extra };
    if (bg.gradients.length) {
      // Não alegar aprovação numérica sobre gradiente sem amostragem de pixels.
      manual.push({ ...item, reason: 'Fundo com imagem/gradiente: inspecionar contraste nas áreas pintadas', gradients: bg.gradients });
    } else results.push(item);
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const el = node.parentElement, text = node.textContent.trim();
    if (!el || !text || !visible(el) || el.closest('script,style,option,title,desc,canvas,.sr-only,[aria-hidden="true"]')) continue;
    const range = document.createRange(); range.selectNodeContents(node);
    if (![...range.getClientRects()].some(r => r.width > 0 && r.height > 0)) continue;
    const s = getComputedStyle(el), size = parseFloat(s.fontSize), weight = parseFloat(s.fontWeight) || (s.fontWeight === 'bold' ? 700 : 400);
    const isSvg = el instanceof SVGElement;
    measure(el, text, rgb(isSvg ? s.fill : s.color), background(el), size >= 24 || (size >= 18.666 && weight >= 700) ? 3 : 4.5, isSvg ? 'svg-text' : 'text', { fontSize: size, fontWeight: weight });
  }
  for (const el of document.querySelectorAll('input:not([type=hidden]),textarea,select')) {
    if (!visible(el)) continue;
    const s = getComputedStyle(el), bg = background(el);
    if (el.tagName === 'SELECT') measure(el, el.selectedOptions[0]?.textContent || '', rgb(s.color), bg, 4.5, 'select-value');
    if (el.tagName !== 'SELECT' && !['checkbox', 'radio', 'range', 'color'].includes(el.type)) {
      if (el.value) measure(el, el.value, rgb(s.color), bg, 4.5, 'input-value');
      if (el.placeholder) {
        const ps = getComputedStyle(el, '::placeholder'), c = rgb(ps.color);
        if (c) c[3] *= Number(ps.opacity);
        measure(el, el.placeholder, c, bg, 4.5, 'placeholder');
      }
    }
    if (['checkbox', 'radio'].includes(el.type)) continue; // Interface nativa: inspeção visual em vez de presumir pixels a partir do CSS.
    const outside = background(el, false), border = rgb(s.borderTopColor);
    const controlBgRatio = ratio(bg.color, outside.color);
    const borderRatio = border ? ratio(over(border, outside.color), outside.color) : 1;
    if (parseFloat(s.borderTopWidth) > 0) {
      const best = Math.max(controlBgRatio, borderRatio);
      results.push({ selector: descriptor(el), kind: 'control-boundary', label: el.getAttribute('aria-label') || el.id || el.tagName, foreground: hex(border || bg.color), background: hex(outside.color), ratio: +best.toFixed(3), minimum: 3, passed: best >= 3, disabled: el.matches(':disabled'), evidence: 'Melhor contraste entre borda ou preenchimento e superfície externa' });
    }
  }
  for (const el of document.querySelectorAll('button[aria-label] svg, a[aria-label] svg')) {
    if (!visible(el)) continue;
    const s = getComputedStyle(el);
    measure(el, el.closest('[aria-label]').getAttribute('aria-label'), rgb(s.color), background(el), 3, 'control-icon');
  }
  const focused = document.activeElement;
  if (focused && visible(focused)) {
    const s = getComputedStyle(focused);
    if (parseFloat(s.outlineWidth) > 0 && s.outlineStyle !== 'none') measure(focused, focused.getAttribute('aria-label') || focused.textContent, rgb(s.outlineColor), background(focused, false), 3, 'focus-indicator');
  }
  for (const el of document.querySelectorAll('svg rect.chart-hit, svg circle.chart-hit, svg path.chart-hit, svg line.chart-hit, svg g.chart-hit > rect, svg g.chart-hit > circle, svg g.chart-hit > path')) {
    if (!visible(el)) continue;
    const s = getComputedStyle(el), fill = rgb(s.fill), stroke = rgb(s.stroke);
    const bg = background(el);
    // Um marcador vazado é reconhecido pelo contorno; o centro não precisa contrastar com o fundo.
    const useStroke = stroke && stroke[3] && parseFloat(s.strokeWidth) > 0 && (!fill || !fill[3] || ratio(stroke, bg.color) > ratio(fill, bg.color));
    const paint = useStroke ? stroke : fill;
    const alpha = parseFloat(useStroke ? s.strokeOpacity : s.fillOpacity) * Number(s.opacity);
    // Bandas translúcidas têm o mesmo valor disponível em rótulo/tabela; não são marca essencial isolada.
    if (alpha < .8 || !paint) continue;
    measure(el, el.getAttribute('aria-label') || el.closest('[aria-label]')?.getAttribute('aria-label') || el.tagName, paint, background(el), 3, 'chart-mark');
  }
  const rootStyle = getComputedStyle(document.documentElement);
  const tokens = Object.fromEntries(['--bg','--surface','--surface-alt','--side','--ink','--muted','--line','--control-border','--blue','--primary','--primary-hover','--on-primary','--focus','--green','--orange','--red', ...Array.from({length:7}, (_, i) => '--chart-' + (i + 1))].map(name => [name, rootStyle.getPropertyValue(name).trim()]));
  return { theme: document.documentElement.dataset.theme, route: location.hash, tokens, results, manual, notes: ['Textos decorativos aria-hidden e controles nativos de sistema não são tratados como pixels CSS.', 'Controles inativos são registrados separadamente porque possuem exceção WCAG; legibilidade continua recomendada.', 'O relatório não certifica WCAG integral; imagens, gradientes e interfaces nativas exigem inspeção visual.'] };
}

async function snapshot(page, state) {
  // Aguardar a pintura após navegação, troca de tema e DOM reconstruído por ResizeObserver.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  // A pintura de página inteira resolve também estilos de conteúdo fora da janela inicial.
  await page.screenshot({ fullPage: true, animations: 'disabled' });
  const data = await page.evaluate(collectPaintedContrast);
  snapshots.push({ state, ...data });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
  try {
    for (const theme of ['light', 'dark']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo', reducedMotion: 'reduce' });
      const page = await context.newPage();
      await page.addInitScript(t => localStorage.setItem('gediv_tema_publico', t), theme);
      for (const route of ROUTES) {
        if (await page.locator('#limpar').count()) await page.locator('#limpar').click();
        await page.goto(BASE + '#' + route);
        await page.waitForSelector('#pagina[aria-busy="false"]');
        await snapshot(page, 'normal');
      }
      await page.goto(BASE + '#geral'); await page.waitForSelector('#pagina[aria-busy="false"]');
      await page.locator('#limpar').click();
      for (const selector of ['#tema', 'button[form="filtros"]', '#abrirCalendario', '#abas a[aria-current="page"]', '.donut-legend button']) {
        const el = page.locator(selector).first();
        if (await el.count()) { await el.hover(); await snapshot(page, 'hover:' + selector); }
      }
      await page.locator('#abrirCalendario').focus(); await snapshot(page, 'focus-calendar-button');
      await page.locator('#abrirCalendario').click(); await snapshot(page, 'calendar-open');
      await page.locator('[data-cal-shortcut="anterior"]').click(); await snapshot(page, 'calendar-selected');
      await page.locator('#gedivCalInicio').focus(); await snapshot(page, 'calendar-focus');
      await page.locator('.gediv-cal-actions [data-cal-close]').click();
      await page.locator('.records [data-detalhe]').first().click(); await snapshot(page, 'modal-open');
      await page.locator('#fecharDetalhe').click();
      await page.locator('#grupo').selectOption('GAJ'); await page.locator('button[form="filtros"]').click(); await snapshot(page, 'filtered-GAJ');
      await page.route('**/dados.json', r => r.fulfill({ status: 503, body: 'Indisponível' }));
      await page.locator('#atualizar').click(); await page.locator('#erro:visible').waitFor(); await snapshot(page, 'error-disabled-exports');
      await context.close();
    }
  } finally { await browser.close(); }
  const matrix = new Map(), manualMatrix = new Map();
  for (const shot of snapshots) {
    for (const item of shot.results) {
      const key = [shot.theme, item.kind, item.foreground, item.background, item.minimum, item.disabled].join('|');
      if (!matrix.has(key)) matrix.set(key, { theme: shot.theme, ...item, occurrences: 0, examples: [] });
      const row = matrix.get(key); row.occurrences++;
      if (row.examples.length < 4 && !row.examples.some(x => x.selector === item.selector && x.route === shot.route)) row.examples.push({ route: shot.route, state: shot.state, selector: item.selector, label: item.label });
    }
    for (const item of shot.manual) {
      const key = [shot.theme, item.selector, item.foreground, item.background, item.reason].join('|');
      if (!manualMatrix.has(key)) manualMatrix.set(key, { theme: shot.theme, ...item, route: shot.route, state: shot.state });
    }
  }
  const rows = [...matrix.values()], failures = rows.filter(x => !x.passed && !x.disabled), disabled = rows.filter(x => x.disabled && !x.passed);
  const result = { base: BASE, checkedAt: new Date().toISOString(), tokens: Object.fromEntries(['light','dark'].map(theme => [theme, snapshots.find(s => s.theme === theme)?.tokens])), states: snapshots.map(s => ({ theme: s.theme, route: s.route, state: s.state, measured: s.results.length, manual: s.manual.length })), pairs: rows, failures, disabledAdvisories: disabled, manualReview: [...manualMatrix.values()], summary: { snapshots: snapshots.length, paintedSamples: snapshots.reduce((n, s) => n + s.results.length, 0), distinctPairs: rows.length, requiredFailures: failures.length, inactiveAdvisories: disabled.length, manualReview: manualMatrix.size } };
  fs.writeFileSync(path.join(OUT, 'contraste-renderizado.json'), JSON.stringify(result, null, 2));
  const report = ['# Contraste renderizado GEDIV', '', 'Medição em Chromium com JavaScript ativo. Texto normal 4.5:1, texto grande 3:1, sinais essenciais de controles 3:1. Não é certificação integral WCAG.', '', `Estados inspecionados: ${snapshots.length}; amostras pintadas: ${result.summary.paintedSamples}; pares distintos: ${rows.length}; falhas obrigatórias: ${failures.length}.`, '', '| Tema | Tipo | Frente | Fundo | Razão | Mínimo | Estado | Exemplo |', '|---|---|---|---|---:|---:|---|---|', ...rows.map(r => `| ${r.theme} | ${r.kind} | ${r.foreground} | ${r.background} | ${r.ratio.toFixed(2)} | ${r.minimum} | ${r.disabled ? 'Inativo (exceção, revisar legibilidade)' : r.passed ? 'Passou' : 'Falhou'} | ${r.selector.replace(/\|/g, '/')} |`), '', `Casos de revisão visual (gradientes/imagens/cores não resolvidas): ${manualMatrix.size}. Eles não são contabilizados como aprovados automaticamente.`];
  fs.writeFileSync(path.join(OUT, 'matriz-contraste.md'), report.join('\n'));
  console.log(JSON.stringify({ ...result.summary, output: OUT, topFailures: failures.slice(0, 5).map(r => ({ theme: r.theme, type: r.kind, ratio: r.ratio, minimum: r.minimum, foreground: r.foreground, background: r.background, examples: r.examples })) }, null, 2));
  if (failures.length) process.exitCode = 1;
})().catch(e => { console.error(e); process.exitCode = 1; });
