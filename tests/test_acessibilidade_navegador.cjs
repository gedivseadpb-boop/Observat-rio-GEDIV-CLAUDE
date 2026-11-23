'use strict';
/**
 * Teste automatizado de acessibilidade e responsividade em navegador real (Playwright)
 * para o Painel Unificado GEDIV.
 *
 * Uso:
 *   node tests/test_acessibilidade_navegador.cjs
 *   node tests/test_acessibilidade_navegador.cjs --url http://127.0.0.1:8000/painel/
 *   node tests/test_acessibilidade_navegador.cjs --static-dir <pasta_pacote_estatico>
 */
const { chromium } = require('playwright');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

function parseArgs(argv) {
  const args = { url: '', staticDir: '' };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--url' && argv[i + 1]) args.url = argv[++i];
    else if (argv[i] === '--static-dir' && argv[i + 1]) args.staticDir = argv[++i];
  }
  return args;
}

function startStaticServer(dir) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const clean = (req.url || '/').split('?')[0];
      const filePath = path.join(dir, clean === '/' ? 'index.html' : clean);
      if (!filePath.startsWith(dir) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
        res.writeHead(404);
        res.end('Not found');
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      const mime = ext === '.html' ? 'text/html; charset=utf-8'
        : ext === '.json' ? 'application/json; charset=utf-8'
        : 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': mime, 'Cache-Control': 'no-store' });
      fs.createReadStream(filePath).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address();
      resolve({ srv, url: `http://127.0.0.1:${addr.port}/` });
    });
  });
}

async function launchBrowser() {
  for (const opts of [
    { headless: true, channel: 'msedge' },
    { headless: true, channel: 'chrome' },
    { headless: true },
  ]) {
    try {
      return await chromium.launch(opts);
    } catch {
      // tenta próximo canal disponível
    }
  }
  throw new Error('Nenhum navegador Chromium/Edge/Chrome disponível para Playwright.');
}

(async () => {
  const args = parseArgs(process.argv.slice(2));
  let srv = null;
  let tmpDir = '';
  let targetUrl = args.url;

  if (!targetUrl) {
    let dir = args.staticDir;
    if (!dir) {
      tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gediv-a11y-'));
      dir = path.join(tmpDir, 'public');
      const repoRoot = path.join(__dirname, '..');
      execFileSync(process.env.PYTHON || 'python', [
        path.join(repoRoot, 'scripts', 'preparar_previa_github_pages.py'),
        '--saida', dir,
      ], { stdio: 'pipe' });
    }
    const started = await startStaticServer(dir);
    srv = started.srv;
    targetUrl = started.url;
  }

  const browser = await launchBrowser();
  const report = { url: targetUrl, checks: [], errors: [], viewports: {} };

  try {
    // 1. Desktop 1440x900 — teclado, foco, ARIA e modais
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    page.on('console', (m) => { if (m.type() === 'error') report.errors.push('console: ' + m.text()); });
    page.on('pageerror', (e) => report.errors.push('pageerror: ' + e.message));

    await page.goto(targetUrl, { waitUntil: 'networkidle' });
    await page.waitForSelector('#levelChart .group-row');

    // 1a. Tab e Shift+Tab deslocam foco entre controles reais
    await page.keyboard.press('Tab');
    const firstFocused = await page.evaluate(() => ({
      tag: document.activeElement?.tagName,
      id: document.activeElement?.id || '',
      text: (document.activeElement?.textContent || '').trim().slice(0, 40),
    }));
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    const thirdFocused = await page.evaluate(() => ({
      tag: document.activeElement?.tagName,
      id: document.activeElement?.id || '',
      text: (document.activeElement?.textContent || '').trim().slice(0, 40),
    }));
    if (firstFocused.id === thirdFocused.id && firstFocused.text === thirdFocused.text) {
      throw new Error('Tab não deslocou o foco entre elementos interativos.');
    }
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Shift+Tab');
    const backFocused = await page.evaluate(() => ({
      tag: document.activeElement?.tagName,
      id: document.activeElement?.id || '',
      text: (document.activeElement?.textContent || '').trim().slice(0, 40),
    }));
    if (backFocused.id !== firstFocused.id || backFocused.text !== firstFocused.text) {
      throw new Error(`Shift+Tab não retornou ao elemento anterior (${JSON.stringify(firstFocused)} vs ${JSON.stringify(backFocused)})`);
    }
    report.checks.push('keyboard_tab_and_shift_tab_ok');

    // 1b. Indicador visível de foco via teclado (:focus-visible)
    await page.locator('.tabs button[data-view="vertical"]').focus();
    await page.keyboard.press('Tab');
    const focusStyle = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el) return null;
      const cs = getComputedStyle(el);
      return {
        tag: el.tagName,
        outlineStyle: cs.outlineStyle,
        outlineWidth: cs.outlineWidth,
        boxShadow: cs.boxShadow,
      };
    });
    if (!focusStyle || (focusStyle.outlineStyle === 'none' && focusStyle.boxShadow === 'none')) {
      throw new Error('Elemento focado via teclado sem indicador visual de foco: ' + JSON.stringify(focusStyle));
    }
    report.checks.push('visible_focus_indicator_ok');

    // 1c. Ativação de aba via Enter e aria-current="page"
    await page.locator('.tabs button[data-view="vertical"]').focus();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(100);
    const tabCurrent = await page.getAttribute('.tabs button[data-view="vertical"]', 'aria-current');
    if (tabCurrent !== 'page') throw new Error('Enter na aba Vertical não ativou aria-current="page"');
    await page.locator('.tabs button[data-view="geral"]').focus();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(100);
    report.checks.push('tab_activation_enter_aria_current_ok');

    // 1d. Ativação de switch Quantidade/% via Espaço e verificação de aria-pressed
    const pctBtn = page.locator('#levelCard .metric-switch button[data-unit="pct"]');
    await pctBtn.focus();
    await page.keyboard.press('Space');
    await page.waitForTimeout(100);
    if ((await pctBtn.getAttribute('aria-pressed')) !== 'true') {
      throw new Error('Espaço no switch % de Progressão Vertical não atualizou aria-pressed="true"');
    }
    const qtyBtn = page.locator('#levelCard .metric-switch button[data-unit="qty"]');
    await qtyBtn.focus();
    await page.keyboard.press('Space');
    await page.waitForTimeout(100);
    report.checks.push('metric_switch_space_aria_pressed_ok');

    // 1e. Se modo detalhado (barras clicáveis), testar ativação por Enter em uma barra A–F + abertura/fechamento de modal via Escape com retorno de foco
    const clickableBar = page.locator('#levelChart button[data-level="NAO_APLICA"]');
    if ((await clickableBar.count()) > 0 && !(await clickableBar.isDisabled())) {
      await clickableBar.focus();
      await page.keyboard.press('Enter');
      await page.waitForTimeout(120);
      if ((await clickableBar.getAttribute('aria-pressed')) !== 'true') {
        throw new Error('Enter na barra NAO_APLICA não ativou aria-pressed="true"');
      }
      await clickableBar.focus();
      await page.keyboard.press('Enter');
      await page.waitForTimeout(120);
      report.checks.push('vertical_level_bar_keyboard_toggle_ok');
    }

    // 1f. Modal #dialog: abrir via Enter no #full, fechar com Escape e conferir retorno de foco ao #full
    await page.locator('#full').focus();
    await page.keyboard.press('Enter');
    await page.waitForSelector('#dialog[open]');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(120);
    const modalClosedAndFocused = await page.evaluate(() => ({
      open: document.querySelector('#dialog')?.hasAttribute('open'),
      activeId: document.activeElement?.id || '',
    }));
    if (modalClosedAndFocused.open) throw new Error('Escape não fechou #dialog');
    if (modalClosedAndFocused.activeId !== 'full') {
      throw new Error(`Foco não retornou ao disparador #full após Escape (ativo: "${modalClosedAndFocused.activeId}")`);
    }
    report.checks.push('dialog_escape_and_focus_return_ok');

    // 1g. Botão de conta #delicateAcctBtn: abrir com Enter (diálogo de acesso/aviso ou menu) e fechar com Escape
    const acctBtn = page.locator('#delicateAcctBtn');
    if ((await acctBtn.count()) > 0 && (await acctBtn.isVisible())) {
      await acctBtn.focus();
      await page.keyboard.press('Enter');
      await page.waitForTimeout(100);
      const acctOpened = await page.evaluate(() => ({
        menu: !document.querySelector('#delicateAcctMenu')?.hidden,
        loginDlg: !!document.querySelector('#loginDialog')?.hasAttribute('open'),
        infoDlg: !!document.querySelector('#dialog')?.hasAttribute('open'),
      }));
      if (!acctOpened.menu && !acctOpened.loginDlg && !acctOpened.infoDlg) {
        throw new Error('Enter em #delicateAcctBtn não abriu menu nem diálogo de acesso/aviso');
      }
      await page.keyboard.press('Escape');
      await page.waitForTimeout(100);
      const acctClosed = await page.evaluate(() => ({
        menuHidden: !!document.querySelector('#delicateAcctMenu')?.hidden,
        loginClosed: !document.querySelector('#loginDialog')?.hasAttribute('open'),
        infoClosed: !document.querySelector('#dialog')?.hasAttribute('open'),
      }));
      if (!acctClosed.menuHidden || !acctClosed.loginClosed || !acctClosed.infoClosed) {
        throw new Error('Escape não fechou o menu/diálogo aberto por #delicateAcctBtn: ' + JSON.stringify(acctClosed));
      }
      report.checks.push('account_control_keyboard_escape_ok');
    }

    // 1g-bis. Menu dropdown de exportação (#downloadToggle / #downloadMenu): Enter abre, Escape fecha e devolve foco
    const dlBtn = page.locator('#downloadToggle');
    if ((await dlBtn.count()) > 0 && (await dlBtn.isVisible())) {
      await dlBtn.focus();
      await page.keyboard.press('Enter');
      await page.waitForTimeout(80);
      const dlOpen = await page.evaluate(() => ({
        menuVisible: !document.querySelector('#downloadMenu')?.hidden,
        expanded: document.querySelector('#downloadToggle')?.getAttribute('aria-expanded'),
      }));
      if (!dlOpen.menuVisible || dlOpen.expanded !== 'true') {
        throw new Error('Enter em #downloadToggle não abriu #downloadMenu com aria-expanded="true": ' + JSON.stringify(dlOpen));
      }
      await page.keyboard.press('Escape');
      await page.waitForTimeout(80);
      const dlClosed = await page.evaluate(() => ({
        menuHidden: !!document.querySelector('#downloadMenu')?.hidden,
        expanded: document.querySelector('#downloadToggle')?.getAttribute('aria-expanded'),
        activeId: document.activeElement?.id || '',
      }));
      if (!dlClosed.menuHidden || dlClosed.expanded !== 'false' || dlClosed.activeId !== 'downloadToggle') {
        throw new Error('Escape em #downloadMenu não fechou ou não devolveu foco: ' + JSON.stringify(dlClosed));
      }
      report.checks.push('download_menu_keyboard_escape_focus_ok');
    }

    // 1h. Verificar ausência de rolagem horizontal em Desktop (1440), Tablet (768) e Mobile (390)
    const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    report.viewports.desktop_1440 = desktopOverflow;
    if (desktopOverflow > 2) throw new Error(`Overflow horizontal em desktop 1440px: ${desktopOverflow}px`);
    await ctx.close();

    for (const [label, width, height] of [
      ['tablet_768', 768, 1024],
      ['mobile_390', 390, 844],
    ]) {
      const vctx = await browser.newContext({ viewport: { width, height } });
      const vpage = await vctx.newPage();
      vpage.on('console', (m) => { if (m.type() === 'error') report.errors.push(`${label}-console: ${m.text()}`); });
      vpage.on('pageerror', (e) => report.errors.push(`${label}-pageerror: ${e.message}`));
      await vpage.goto(targetUrl, { waitUntil: 'networkidle' });
      await vpage.waitForSelector('#levelChart .group-row');
      const overflow = await vpage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      report.viewports[label] = overflow;
      if (overflow > 2) throw new Error(`Overflow horizontal em ${label}: ${overflow}px`);
      await vctx.close();
    }
    report.checks.push('responsive_desktop_tablet_mobile_zero_overflow_ok');

    if (report.errors.length) {
      throw new Error('Erros detectados durante auditoria de acessibilidade: ' + JSON.stringify(report.errors));
    }
    console.log(JSON.stringify(report, null, 2));
  } finally {
    await browser.close();
    if (srv) srv.close();
    if (tmpDir) fs.rmSync(tmpDir, { recursive: true, force: true });
  }
})();
