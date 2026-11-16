/* Painel público GEDIV. Gráficos SVG adaptam a abordagem do painel existente.
   Entrada exclusiva: projeção pública protegida, nunca registros individuais. */
(function (root) {
  'use strict';
  const N = { eixo: { PROGRESSAO: 'Progressão Funcional', TEMPO_SERVICO: 'Tempo de Serviço' }, modalidade: { HORIZONTAL: 'Horizontal', VERTICAL: 'Vertical' } };
  const emptyMetric = () => ({ valor: null, minimo: null, maximo: null, rotulo: 'Preservado', protegido: true });
  const zeroMetric = () => ({ valor: 0, minimo: 0, maximo: 0, rotulo: '0', protegido: false });
  function numberBounds(m) {
    if (typeof m === 'number' && Number.isFinite(m)) return { min: m, max: m };
    if (!m || typeof m !== 'object') return null;
    if (Number.isFinite(m.minimo) && Number.isFinite(m.maximo)) return { min: m.minimo, max: m.maximo };
    if (Number.isFinite(m.valor)) return { min: m.valor, max: m.valor };
    return null;
  }
  function metricLabel(m) { return m && typeof m === 'object' ? (m.rotulo || (m.valor === 0 ? '0' : 'Preservado')) : typeof m === 'number' ? String(m) : 'Preservado'; }
  function sumMetrics(metrics, allowZero) {
    if (!metrics.length) return allowZero ? zeroMetric() : emptyMetric();
    const bounds = metrics.map(numberBounds);
    if (bounds.some(b => !b)) return emptyMetric();
    const min = bounds.reduce((n, b) => n + b.min, 0), max = bounds.reduce((n, b) => n + b.max, 0);
    return { valor: min === max ? min : null, minimo: min, maximo: max, rotulo: min === max ? String(min) : min + '–' + max, protegido: min !== max };
  }
  function filterCells(cells, state) {
    return cells.filter(c => (!state.inicio || c.periodo >= state.inicio) && (!state.fim || c.periodo <= state.fim)
      && (!state.eixo || c.eixo === state.eixo) && (!state.modalidade || c.modalidade === state.modalidade)
      && (!state.grupo || (state.grupo === 'NAO_INFORMADO' ? c.grupo == null : c.grupo === state.grupo)) && (!state.subcategoria || c.subcategoria === state.subcategoria)
      && (!state.situacao || c.situacao === state.situacao));
  }
  function csvValue(v) { const t = String(v == null ? '' : v); return '"' + (/^[=+@\-\t\r]/.test(t) ? "'" + t : t).replace(/"/g, '""') + '"'; }
  function cellsToRows(cells, catalogo) {
    const name = (list, code) => (list || []).find(x => x.codigo === code)?.nome || code || 'Não informado';
    const rows = [['Mês de publicação', 'Eixo', 'Modalidade', 'Grupo PCCR', 'Assunto TS', 'Situação', 'Atos (faixa)', 'Decisões (faixa)', 'Escopo']];
    cells.forEach(c => rows.push([c.periodo, N.eixo[c.eixo] || c.eixo, N.modalidade[c.modalidade] || '', c.grupo ? name(catalogo.grupos, c.grupo) : '', c.subcategoria ? name(catalogo.subcategorias, c.subcategoria) : '', c.situacao === 'conferido' ? 'Conferido' : 'Provisório', metricLabel(c.atos), metricLabel(c.decisoes), 'Agregados publicáveis parciais; contagens pequenas preservadas']));
    return rows;
  }
  function cellsToCsv(cells, catalogo) { return '\ufeff' + cellsToRows(cells, catalogo).map(r => r.map(csvValue).join(';')).join('\r\n'); }
  const helpers = { filterCells, sumMetrics, metricLabel, numberBounds, cellsToCsv, cellsToRows };
  if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
  if (typeof document === 'undefined') return;
  root.GedivPublico = helpers;
  const $ = id => document.getElementById(id);
  const fields = ['inicio', 'fim', 'eixo', 'modalidade', 'grupo', 'subcategoria', 'situacao'];
  let data = null, visible = [], state = Object.fromEntries(fields.map(f => [f, '']));
  const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const month = p => { if (!/^\d{4}-\d{2}$/.test(p || '')) return 'Período não informado'; const [y, m] = p.split('-'); return new Intl.DateTimeFormat('pt-BR', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(+y, +m - 1, 1))).replace(' de ', '/'); };
  const date = v => { const d = new Date(v); return Number.isNaN(d.getTime()) ? 'Não informada' : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(d); };
  const groupName = c => data?.catalogo?.grupos?.find(g => g.codigo === c)?.nome || (c ? c : 'Não informado');
  const subName = c => data?.catalogo?.subcategorias?.find(s => s.codigo === c)?.nome || (c ? c : 'Assunto não informado');
  const hasFilters = () => fields.some(f => state[f]);
  function setTheme(dark) { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; $('tema').setAttribute('aria-label', dark ? 'Ativar modo claro' : 'Ativar modo escuro'); $('tema').setAttribute('aria-pressed', String(dark)); try { localStorage.setItem('gediv_tema_publico', dark ? 'dark' : 'light'); } catch (_) {} }
  let savedTheme; try { savedTheme = localStorage.getItem('gediv_tema_publico'); } catch (_) {}
  setTheme(savedTheme ? savedTheme === 'dark' : window.matchMedia?.('(prefers-color-scheme: dark)').matches);
  $('tema').onclick = () => setTheme(document.documentElement.dataset.theme !== 'dark');
  function populate() {
    ['grupo', 'subcategoria'].forEach(id => { const items = id === 'grupo' ? data.catalogo.grupos : data.catalogo.subcategorias; $(id).innerHTML = '<option value="">' + (id === 'grupo' ? 'Todos os grupos' : 'Todos os assuntos') + '</option>' + items.map(o => '<option value="' + esc(o.codigo) + '">' + esc(o.codigo + ' · ' + o.nome) + '</option>').join('') + (id === 'grupo' ? '<option value="NAO_INFORMADO">Grupo não informado</option>' : ''); });
    const first = data.cobertura.primeira_publicacao?.slice(0, 7), last = data.cobertura.ultima_publicacao?.slice(0, 7);
    ['inicio', 'fim'].forEach(id => { if (first) $(id).min = first; if (last) $(id).max = last; });
  }
  function summaryMetric(key, source) {
    const r = source || data.resumo || {};
    if (key === 'decisoes') return r.decisoes || r.total_decisoes || sumMetrics([r.conferidos, r.provisorios].filter(Boolean), true);
    return r[key] || emptyMetric();
  }
  function confirmedZero() { const source = state.eixo && data.resumo_eixos?.[state.eixo]; const b = numberBounds(summaryMetric('conferidos', source)); return b && b.max === 0; }
  function metrics() {
    const filtered = hasFilters(), rows = visible, noConfirmed = confirmedZero();
    const onlyAxis = state.eixo && fields.every(f => f === 'eixo' || !state[f]);
    const axisSummary = onlyAxis && data.resumo_eixos?.[state.eixo];
    const useCells = filtered && !axisSummary, source = axisSummary || data.resumo;
    const cards = useCells ? [
      ['Decisões', sumMetrics(rows.map(c => c.decisoes), state.situacao === 'conferido' && noConfirmed), 'Faixa do recorte publicável'],
      ['Ocorrências de atos', sumMetrics(rows.map(c => c.atos), state.situacao === 'conferido' && noConfirmed), 'Soma dos recortes; um ato pode aparecer em mais de uma situação'],
      ['Decisões conferidas', sumMetrics(rows.filter(c => c.situacao === 'conferido').map(c => c.decisoes), noConfirmed), noConfirmed ? 'Nenhuma conferência registrada na base' : 'Recorte de dados conferidos'],
      ['Decisões provisórias', state.situacao === 'conferido' ? emptyMetric() : sumMetrics(rows.filter(c => c.situacao === 'provisorio').map(c => c.decisoes)), 'Ainda aguardam conferência administrativa']
    ] : [['Decisões', summaryMetric('decisoes', source), axisSummary ? 'Total do eixo disponível, em faixas' : 'Total da base disponível, em faixas'], ['Atos identificados', summaryMetric('atos', source), 'Publicações pendentes: ' + metricLabel(summaryMetric('publicacoes_pendentes', source))], ['Decisões conferidas', summaryMetric('conferidos', source), 'Conferência administrativa registrada'], ['Decisões provisórias', summaryMetric('provisorios', source), 'Aguardam conferência administrativa']];
    $('indicadores').innerHTML = cards.map(([title, m, description]) => '<article class="metric-card"><span>' + esc(title) + '</span><strong class="' + (numberBounds(m) ? '' : 'unavailable') + '">' + esc(metricLabel(m)) + '</strong><small>' + esc(description) + '</small></article>').join('');
    $('tituloIndicadores').textContent = useCells ? 'Visão filtrada de agregados publicáveis' : axisSummary ? 'Visão geral · ' + N.eixo[state.eixo] : 'Visão geral da base';
    $('escopoIndicadores').textContent = useCells ? 'Contagens parciais, apresentadas em faixas' : axisSummary ? 'Totais do eixo, apresentados em faixas' : 'Totais disponíveis, apresentados em faixas';
  }
  function evolution() {
    const box = $('evolucao');
    if (!visible.length) { box.innerHTML = '<p class="empty-state">' + (state.situacao === 'conferido' && confirmedZero() ? 'Ainda não há decisões conferidas na base disponível.' : 'Dados preservados ou sem agregados publicáveis neste recorte.') + '</p>'; return; }
    const periods = [...new Set(visible.map(c => c.periodo))].sort(), categories = ['VERTICAL', 'HORIZONTAL', 'TEMPO_SERVICO'];
    const series = periods.map(p => ({ periodo: p, values: categories.map(k => sumMetrics(visible.filter(c => c.periodo === p && (k === 'TEMPO_SERVICO' ? c.eixo === k : c.eixo === 'PROGRESSAO' && c.modalidade === k)).map(c => c.decisoes))) }));
    const L = Math.max(360, Math.min(980, box.clientWidth || 980)), A = 240, left = 45, right = 15, top = 15, bottom = 43, w = L - left - right, h = A - top - bottom;
    const max = Math.max(5, ...series.flatMap(s => s.values.map(v => numberBounds(v)?.max || 0))), step = w / periods.length, bw = Math.max(6, Math.min(30, step / 5));
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', `0 0 ${L} ${A}`); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', 'Evolução mensal das faixas de decisões publicáveis. Valores parciais.');
    const el = (tag, attrs, content) => { const x = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([k, v]) => x.setAttribute(k, v)); if (content != null) x.textContent = content; svg.appendChild(x); return x; };
    [0, Math.ceil(max / 2), max].forEach(v => { const y = top + h - v / max * h; el('line', { x1: left, x2: L - right, y1: y, y2: y, class: 'grid-line' }); el('text', { x: left - 10, y: y + 4, 'text-anchor': 'end' }, v); });
    series.forEach((s, i) => {
      s.values.forEach((v, j) => { const b = numberBounds(v); if (!b) return; const x = left + step * (i + .5) + (j - 1.5) * (bw + 5), cls = ['vertical', 'horizontal', 'tempo'][j], minH = b.min / max * h, tailH = (b.max - b.min) / max * h;
        const rect = el('rect', { x, y: top + h - minH, width: bw, height: minH, rx: 3, class: cls });
        const title = document.createElementNS(ns, 'title'); title.textContent = month(s.periodo) + ' · ' + (N.modalidade[categories[j]] || N.eixo[categories[j]]) + ': ' + metricLabel(v) + ' decisões (recorte parcial)'; rect.appendChild(title);
        if (tailH) el('rect', { x, y: top + h - b.max / max * h, width: bw, height: tailH, rx: 3, class: cls + ' range-tail' });
        el('text', { x: x + bw / 2, y: top + h - b.max / max * h - 6, 'text-anchor': 'middle' }, metricLabel(v));
      });
      const target = el('rect', { x: left + i * step, y: top, width: step, height: h + 8, class: 'plot-target', tabindex: '0', role: 'button', 'aria-label': 'Filtrar ' + month(s.periodo) });
      const choose = () => { state.inicio = state.fim = s.periodo; render(); }; target.onclick = choose; target.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(); } };
      el('text', { x: left + step * (i + .5), y: A - 19, 'text-anchor': 'middle' }, month(s.periodo));
    });
    el('text', { x: L - right, y: A - 2, 'text-anchor': 'end', class: 'range-caption' }, 'A parte clara completa o intervalo da faixa.');
    box.replaceChildren(svg);
  }
  function bars(id, items, property, scope) {
    const box = $(id); box.className = 'bars' + (property === 'subcategoria' ? ' tempo' : '');
    const rows = items.map(item => ({ item, metric: sumMetrics(visible.filter(c => c.eixo === scope && (property === 'grupo' && item.codigo === 'NAO_INFORMADO' ? c.grupo == null : c[property] === item.codigo)).map(c => c.decisoes)) }));
    const max = Math.max(1, ...rows.map(r => numberBounds(r.metric)?.max || 0));
    box.innerHTML = rows.map(({ item, metric }) => { const b = numberBounds(metric), selected = state[property] === item.codigo;
      return '<button type="button" class="bar-row' + (selected ? ' selected' : '') + '" data-code="' + esc(item.codigo) + '" aria-pressed="' + selected + '" title="' + esc(item.nome + ': ' + (b ? metricLabel(metric) + ' decisões em agregados publicáveis' : 'Dados preservados ou sem agregado publicável')) + '"><span class="bar-label">' + esc(item.codigo === 'NAO_INFORMADO' ? 'Não informado' : item.codigo) + '<small>' + esc(item.nome) + '</small></span><span class="bar-track" aria-hidden="true">' + (b ? '<i style="width:' + b.min / max * 100 + '%"></i><i class="tail" style="width:' + (b.max - b.min) / max * 100 + '%"></i>' : '') + '</span><span class="bar-count' + (b ? '' : ' unavailable') + '">' + esc(b ? metricLabel(metric) : 'Preservado / não divulgado') + '</span></button>'; }).join('');
    box.querySelectorAll('button').forEach(button => { button.onclick = () => { const code = button.dataset.code; state[property] = state[property] === code ? '' : code; state.eixo = scope; if (scope === 'PROGRESSAO') state.subcategoria = ''; else { state.grupo = ''; state.modalidade = ''; } render(); }; });
  }
  function table() {
    $('quantidadeTabela').textContent = visible.length ? visible.length + ' agregado(s) publicável(is) · não são registros individuais' : 'Nenhum agregado publicável neste recorte';
    $('tabela').innerHTML = visible.length ? visible.map(c => '<tr><td>' + esc(month(c.periodo)) + '</td><td>' + esc(N.eixo[c.eixo] || c.eixo) + (c.eixo === 'PROGRESSAO' ? '<small>' + esc(N.modalidade[c.modalidade] || 'Modalidade não informada') + '</small>' : '') + '</td><td>' + esc(c.eixo === 'PROGRESSAO' ? (c.grupo ? c.grupo + ' · ' + groupName(c.grupo) : 'Grupo não informado') : (c.subcategoria ? c.subcategoria + ' · ' + subName(c.subcategoria) : 'Assunto não informado')) + '</td><td><span class="status-pill ' + (c.situacao === 'conferido' ? 'conferido' : '') + '">' + (c.situacao === 'conferido' ? 'Conferido' : 'Provisório') + '</span></td><td>' + esc(metricLabel(c.atos)) + '</td><td><b>' + esc(metricLabel(c.decisoes)) + '</b></td></tr>').join('') : '<tr><td colspan="6" class="empty-state">' + (state.situacao === 'conferido' && confirmedZero() ? 'Não há decisões com conferência administrativa registrada na base disponível.' : 'Dados preservados ou sem agregados publicáveis. Isso não confirma ausência de atos.') + '</td></tr>';
    $('exportarCsv').disabled = !visible.length;
    $('exportarXlsx').disabled = !visible.length || !root.GEDIVXLSX;
    $('exportarPdf').disabled = !data;
  }
  function coverage() {
    const c = data.cobertura, dates = c.primeira_publicacao && c.ultima_publicacao ? date(c.primeira_publicacao + 'T12:00:00-03:00') + ' a ' + date(c.ultima_publicacao + 'T12:00:00-03:00') : 'Período ainda não informado';
    $('coberturaIndicadores').innerHTML = [['Edições disponíveis', c.edicoes], ['Páginas disponíveis', c.paginas], ['Cobertura histórica', c.historico_completo ? 'Completa' : 'Parcial']].map(([label, v]) => '<div class="coverage-stat"><b>' + esc(v ?? '—') + '</b><span>' + esc(label) + '</span></div>').join('');
    $('coberturaNotas').innerHTML = '<div><b>Documentos disponíveis</b><p>' + esc(dates) + '. O projeto prevê histórico desde 01/01/2026; períodos sem documentos não têm ausência de atos confirmada.</p></div><div><b>Auditoria de cobertura dirigida</b><p>' + esc(c.ausencia_tecnica_edicoes == null ? 'Há períodos aguardando confirmação documental.' : c.ausencia_tecnica_edicoes + ' edições com ausência técnica proposta de atos pertinentes; ' + (c.inconclusivas ?? '—') + ' edição inconclusiva.') + ' Conclusões técnicas não representam homologação humana.</p></div><div><b>Conferência e atualização</b><p>' + esc(c.observacao || 'O processamento alimenta uma projeção pública protegida. A atualização diária definitiva ainda não está ativa.') + '</p></div>';
  }
  function filterDescription() {
    const parts = [];
    if (state.inicio || state.fim) parts.push((state.inicio ? month(state.inicio) : 'Início disponível') + ' → ' + (state.fim ? month(state.fim) : 'Fim disponível'));
    if (state.eixo) parts.push(N.eixo[state.eixo]);
    if (state.modalidade) parts.push(N.modalidade[state.modalidade]);
    if (state.grupo) parts.push(state.grupo === 'NAO_INFORMADO' ? 'Grupo não informado' : state.grupo);
    if (state.subcategoria) parts.push(state.subcategoria);
    if (state.situacao) parts.push(state.situacao === 'conferido' ? 'Conferidos' : 'Provisórios');
    return parts.length ? parts.join(' · ') : 'Visão geral da base disponível';
  }
  function render() {
    fields.forEach(id => { $(id).value = state[id]; });
    $('grupo').disabled = state.eixo === 'TEMPO_SERVICO'; $('modalidade').disabled = state.eixo === 'TEMPO_SERVICO'; $('subcategoria').disabled = state.eixo === 'PROGRESSAO';
    document.querySelectorAll('#navegacao button').forEach(button => { const active = button.dataset.eixo === state.eixo; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
    const invalid = state.inicio && state.fim && state.inicio > state.fim;
    $('fim').setCustomValidity(invalid ? 'O mês final deve ser igual ou posterior ao mês inicial.' : '');
    visible = invalid ? [] : filterCells(data.celulas || [], state);
    $('filtrosAtivos').textContent = invalid ? 'Período inválido: escolha um mês final igual ou posterior ao inicial.' : filterDescription();
    metrics(); evolution(); bars('grupos', [...(data.catalogo.grupos || []), { codigo: 'NAO_INFORMADO', nome: 'Sem grupo reconhecido' }], 'grupo', 'PROGRESSAO'); bars('assuntos', data.catalogo.subcategorias || [], 'subcategoria', 'TEMPO_SERVICO'); table();
  }
  fields.forEach(id => $(id).addEventListener('change', () => {
    state[id] = $(id).value;
    if (id === 'eixo') { if (state.eixo === 'TEMPO_SERVICO') { state.grupo = ''; state.modalidade = ''; } else if (state.eixo === 'PROGRESSAO') state.subcategoria = ''; }
    if (id === 'grupo' && state.grupo) { state.eixo = 'PROGRESSAO'; state.subcategoria = ''; }
    if (id === 'modalidade' && state.modalidade) { state.eixo = 'PROGRESSAO'; state.subcategoria = ''; }
    if (id === 'subcategoria' && state.subcategoria) { state.eixo = 'TEMPO_SERVICO'; state.grupo = ''; state.modalidade = ''; }
    if (data) render();
  }));
  $('filtros').onsubmit = e => e.preventDefault();
  document.querySelectorAll('#navegacao button').forEach(button => { button.onclick = () => { state.eixo = button.dataset.eixo; if (state.eixo !== 'PROGRESSAO') { state.grupo = ''; state.modalidade = ''; } if (state.eixo !== 'TEMPO_SERVICO') state.subcategoria = ''; if (data) render(); }; });
  $('limpar').onclick = () => { state = Object.fromEntries(fields.map(f => [f, ''])); if (data) render(); };
  $('exportarCsv').onclick = () => { if (!data || !visible.length) return; const blob = new Blob([cellsToCsv(visible, data.catalogo)], { type: 'text/csv;charset=utf-8' }); const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'GEDIV_agregados_publicos.csv'; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); };
  $('exportarXlsx').onclick = () => { if (data && visible.length && root.GEDIVXLSX) root.GEDIVXLSX.baixar(cellsToRows(visible, data.catalogo), 'GEDIV_agregados_publicos.xlsx'); };
  $('exportarPdf').onclick = () => window.print();
  async function load() {
    $('erro').hidden = true;
    try {
      const response = await fetch('./dados.json', { cache: 'no-cache' });
      if (!response.ok) throw new Error('A projeção pública não está disponível neste momento.');
      const incoming = await response.json();
      if (incoming.schema_version !== 1 || !incoming.catalogo || !incoming.cobertura || !Array.isArray(incoming.celulas)) throw new Error('A projeção pública ainda não foi disponibilizada no formato esperado.');
      data = incoming; populate();
      $('atualizacao').textContent = date(data.atualizado_em);
      $('estado').innerHTML = '<span class="notice-icon" aria-hidden="true">i</span><div><b>Prévia pública · dados provisórios</b><p>Dados reais extraídos do Diário Oficial, ainda sujeitos à conferência administrativa. Contagens positivas são apresentadas em faixas; registros individuais e agregados pequenos não são divulgados.</p></div>';
      coverage(); render();
    } catch (error) {
      data = null; $('estado').hidden = true; $('erro').hidden = false; $('mensagemErro').textContent = error instanceof SyntaxError ? 'Não foi possível ler a projeção pública. Tente novamente em alguns instantes.' : error.message; $('atualizacao').textContent = 'Dados indisponíveis'; $('exportarCsv').disabled = $('exportarXlsx').disabled = $('exportarPdf').disabled = true;
    }
  }
  let resizeTimer; window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (data) evolution(); }, 120); });
  $('tentarNovamente').onclick = () => { $('estado').hidden = false; load(); };
  load();
})(typeof window !== 'undefined' ? window : globalThis);
