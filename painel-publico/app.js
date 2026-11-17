/* Interface pública GEDIV — Observatório do Diário Oficial. Fonte única: dados.json, contrato protegido versão 1. */
(function (root) {
  'use strict';
  if (typeof document === 'undefined') { module.exports = require('./modelo.js'); return; }
  const M = root.GedivModelo;
  root.GedivPublico = M;
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pages = {
    geral: 'Visão geral',
    progressao: 'Progressão Funcional',
    tempo: 'Tempo de Serviço',
    dia: 'Publicações do dia',
    historico: 'Histórico',
    alteracoes: 'Alterações / Refeitos',
    outras: 'Outras publicações',
    cobertura: 'Edições e fontes',
    pendencias: 'Pendências',
    gerencial: 'Área gerencial'
  };
  const colors = ['#1e64c8', '#0d9f7e', '#e68626', '#6c5ce7', '#c99b1e', '#c85a68', '#52789c'];
  const series = [
    { key: 'VERTICAL', name: 'Progressão Vertical', color: colors[0] },
    { key: 'HORIZONTAL', name: 'Progressão Horizontal', color: colors[1] },
    { key: 'TEMPO_SERVICO', name: 'Tempo de Serviço', color: colors[2] }
  ];
  const kpis = [
    ['processos', 'Total de processos distintos', 'Processos administrativos distintos (ex.: SAD-PSE-*). Um mesmo processo ou resenha pode reunir várias decisões individuais.', 'Processo administrativo', 'Base gerencial · agregação pública pendente'],
    ['resenhas', 'Total de resenhas', 'Resenhas / despachos distintos publicados no DOE-PB. Não se confundem com o total de decisões nem com ocorrências em células.', 'Resenha / ato', 'Resenhas em integração; atos são outra unidade'],
    ['decisoes', 'Total de decisões individuais', 'Decisões vigentes de publicações originais nos dois eixos. Divulgadas em faixas protegidas; identificação pessoal restrita.', 'Decisão original', 'Integrado na projeção pública'],
    ['deferidos', 'Total de deferimentos', 'Decisões originais com resultado de deferimento expresso após conferência documental.', 'Resultado de mérito', 'Pendente na projeção pública v1'],
    ['indeferidos', 'Total de indeferimentos', 'Decisões originais com resultado de indeferimento expresso. Não inclui atos tornados sem efeito.', 'Resultado de mérito', 'Pendente na projeção pública v1'],
    ['refeitos', 'Total de atos refeitos', 'Atos refeitos vinculados ao ato original com nova decisão administrativa. Usam a data do evento modificador.', 'Evento modificador', 'Pendente de vínculo público'],
    ['sem_efeito', 'Total de atos tornados sem efeito', 'Atos com evento de anulação/desconstituição documentalmente vinculado e validado. Não são contados como indeferimentos.', 'Evento modificador', 'Pendente de vínculo público']
  ];
  const extraKpis = [
    ['republicacoes', 'Total de republicações por incorreção', 'Republicações para correção material/formal de texto publicado com incorreção no DOE, preservando o ato original. Distinto de ato refeito e de ato tornado sem efeito.', 'Evento modificador'],
    ['outros_resultados', 'Outros resultados', 'Decisões com desfecho diverso de deferimento/indeferimento padrão (parcial, sobrestado, prejudicado ou não expresso na publicação).', 'Resultado de mérito'],
    ['cobertura_doe', 'Edições e páginas processadas', 'Volume documental do Diário Oficial da Paraíba processado na base canônica da projeção (edições lidas, páginas processadas e edições com atos GEDIV).', 'Cobertura documental']
  ];

  let data = null, state = M.novoEstado(), visible = [], page = 'geral', loading = false;
  let query = '', queryMode = 'agregados', queryPage = 0, pageSize = 5, tablePage = 0, tableSort = 'periodo', sortDirection = -1, selected = null;
  let calendarMonth = '', selectedDay = '', graphMeasure = 'quantidade', chartUnit = 'decisoes', toastTimer, focusBeforeDialog;
  let evolutionType = 'colunas', subjectChartType = 'rosca', resultsDimension = 'area';

  const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  function dayLabel(v) { return M.validDate(v) ? v.split('-').reverse().join('/') : 'Não extraído'; }
  function monthLabel(p) { return /^\d{4}-\d{2}$/.test(p || '') ? new Intl.DateTimeFormat('pt-BR', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(p + '-01T12:00:00Z')).replace(' de ', '/') : 'Não extraído'; }
  function timestamp(v) { const d = new Date(v); return Number.isNaN(d.getTime()) ? 'Não informada' : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(d); }
  const groupName = code => data?.catalogo.grupos.find(g => g.codigo === code)?.nome || 'Grupo não informado';
  const subName = code => data?.catalogo.subcategorias.find(s => s.codigo === code)?.nome || 'Assunto não informado';
  const cellCategory = c => c.eixo === 'TEMPO_SERVICO' ? (c.subcategoria ? c.subcategoria + ' · ' + subName(c.subcategoria) : 'Assunto não informado') : (c.grupo ? c.grupo + ' · ' + groupName(c.grupo) : 'Grupo não informado');
  const cellTitle = c => M.EIXOS[c.eixo] + (c.modalidade ? ' · ' + M.MODALIDADES[c.modalidade] : '');
  const cellKey = c => JSON.stringify([c.periodo, c.eixo, c.modalidade, c.grupo, c.subcategoria, c.situacao]);
  const matchesSeries = (c, s) => s === 'TEMPO_SERVICO' ? c.eixo === s : c.eixo === 'PROGRESSAO' && c.modalidade === s;
  const filteredMetric = (cells, prop = 'decisoes') => M.sumMetrics(cells.map(c => c[prop]));
  const pill = (text, cls = '') => '<span class="pill ' + esc(cls) + '">' + esc(text) + '</span>';
  const empty = (title, text, locked = false) => '<div class="empty-state">' + (locked ? '<span class="lock-symbol" aria-hidden="true">◇</span>' : '') + '<b>' + esc(title) + '</b><p>' + esc(text) + '</p></div>';
  const section = (title, subtitle, badge = 'Dados públicos') => '<div class="section-heading"><div><h2 id="tituloPagina" tabindex="-1">' + esc(title) + '</h2><p>' + esc(subtitle) + '</p></div>' + pill(badge) + '</div>';
  const panel = (title, desc, content, actions = '', cls = '') => '<section class="panel ' + cls + '"><div class="panel-head"><div><h3>' + esc(title) + '</h3><p>' + esc(desc) + '</p></div>' + (actions ? '<div class="panel-head-actions">' + actions + '</div>' : '') + '</div>' + content + '</section>';
  const definition = (label, value) => '<dt>' + esc(label) + '</dt><dd>' + esc(value ?? 'Não extraído') + '</dd>';
  const legend = () => '<div class="chart-legend">' + series.map(s => '<span class="legend-item"><i class="swatch" style="--series:' + s.color + '"></i>' + esc(s.name) + '</span>').join('') + '</div>';

  function tableHTML(headers, rows, caption = '') {
    return '<div class="table-scroll"><table>' + (caption ? '<caption>' + esc(caption) + '</caption>' : '') + '<thead><tr>' + headers.map(x => '<th scope="col">' + esc(x) + '</th>').join('') + '</tr></thead><tbody>' + (rows.length ? rows.map(r => '<tr>' + r.map(x => '<td>' + esc(x) + '</td>').join('') + '</tr>').join('') : '<tr><td colspan="' + headers.length + '">Não verificado / sem agregado publicável neste recorte.</td></tr>') + '</tbody></table></div>';
  }
  const alternative = (headers, rows, caption) => '<details class="table-alternative"><summary>Ver os dados em tabela</summary>' + tableHTML(headers, rows, caption) + '</details>';
  function notify(text) { $('toast').textContent = text; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 7000); }

  function describeFilters() {
    const parts = [];
    if (state.inicio || state.fim) parts.push((state.inicio ? dayLabel(state.inicio) : 'Início disponível') + ' → ' + (state.fim ? dayLabel(state.fim) : 'Fim disponível'));
    if (state.eixo) parts.push(M.EIXOS[state.eixo]);
    if (state.modalidade) parts.push(M.MODALIDADES[state.modalidade]);
    if (state.grupo) parts.push(state.grupo === 'NAO_INFORMADO' ? 'Grupo não informado' : state.grupo);
    if (state.subcategorias.length) parts.push(state.subcategorias.join(', '));
    if (state.situacao) parts.push({ conferido: 'Conferidos', provisorio: 'Provisórios', pendente: 'Pendentes / não verificados' }[state.situacao]);
    ['resultado', 'tipo', 'coberturaFiltro'].forEach(k => { if (state[k]) parts.push($(k)?.selectedOptions[0]?.textContent || state[k]); });
    return parts.join(' · ') || 'Toda a base disponível · cobertura parcial';
  }

  function renderFilterChips() {
    const container = $('chipsFiltro');
    if (!container) return;
    const chips = [];
    if (state.inicio || state.fim) chips.push(['periodo', (state.inicio ? dayLabel(state.inicio) : 'Início') + ' → ' + (state.fim ? dayLabel(state.fim) : 'Fim')]);
    if (state.eixo) chips.push(['eixo', M.EIXOS[state.eixo]]);
    if (state.modalidade) chips.push(['modalidade', M.MODALIDADES[state.modalidade]]);
    if (state.grupo) chips.push(['grupo', state.grupo === 'NAO_INFORMADO' ? 'Grupo não informado' : state.grupo]);
    state.subcategorias.forEach(s => chips.push(['sub:' + s, s]));
    if (state.situacao) chips.push(['situacao', { conferido: 'Conferidos', provisorio: 'Provisórios', pendente: 'Pendentes' }[state.situacao]]);
    ['resultado', 'tipo', 'coberturaFiltro'].forEach(k => { if (state[k]) chips.push([k, $(k)?.selectedOptions[0]?.textContent || state[k]]); });
    if (!chips.length) {
      container.innerHTML = '<span class="chip-muted">Sem filtros restritivos (exibindo toda a base disponível)</span>';
      return;
    }
    container.innerHTML = chips.map(([key, label]) => '<button type="button" class="filter-chip" data-remover-filtro="' + esc(key) + '" title="Remover filtro ' + esc(label) + '">' + esc(label) + ' <span aria-hidden="true">✕</span></button>').join('') + '<button type="button" class="filter-chip clear-all-chip" data-remover-filtro="todos">Limpar todos</button>';
  }

  function axisMetric(eixo, modalidade = '') {
    if (!data || (M.selectionIssue(state) || M.coverageIssue(data, state))) return M.vazio();
    if (state.eixo && state.eixo !== eixo) return M.vazio();
    if (modalidade && state.modalidade && state.modalidade !== modalidade) return M.vazio();
    if (!modalidade && !state.inicio && !state.fim && !state.grupo && !state.subcategorias.length && !state.modalidade) {
      return M.decisionMetric(data, { ...state, eixo }, visible.filter(c => c.eixo === eixo));
    }
    const cells = visible.filter(c => c.eixo === eixo && (!modalidade || c.modalidade === modalidade));
    return filteredMetric(cells, 'decisoes');
  }

  function executiveKPIs() {
    const decision = data ? M.decisionMetric(data, state, visible) : M.vazio();
    const acts = data ? M.qualityMetric(data, state, visible, 'atos') : M.vazio();
    const prog = axisMetric('PROGRESSAO');
    const vert = axisMetric('PROGRESSAO', 'VERTICAL');
    const horiz = axisMetric('PROGRESSAO', 'HORIZONTAL');
    const ts = axisMetric('TEMPO_SERVICO');
    const cob = data?.cobertura;
    const decBounds = M.numberBounds(decision);
    const progBounds = M.numberBounds(prog);
    const tsBounds = M.numberBounds(ts);
    const vertBounds = M.numberBounds(vert);
    const horizBounds = M.numberBounds(horiz);

    const progPct = decBounds && progBounds && decBounds.max > 0 ? Math.min(100, Math.round(progBounds.min / decBounds.min * 100)) : 0;
    const tsPct = decBounds && tsBounds && decBounds.max > 0 ? Math.min(100, Math.round(tsBounds.min / decBounds.min * 100)) : 0;
    const vertShare = vertBounds && horizBounds && (vertBounds.min + horizBounds.min) > 0 ? Math.round(vertBounds.min / (vertBounds.min + horizBounds.min) * 100) : 0;
    const vertInterval = M.shareLabel(M.shareInterval(vert, [vert, horiz]));
    const horizInterval = M.shareLabel(M.shareInterval(horiz, [vert, horiz]));
    const cobPct = cob && cob.edicoes ? Math.round((cob.edicoes - cob.ausencia_tecnica_edicoes - cob.inconclusivas) / cob.edicoes * 100) : 0;

    if (page === 'progressao') {
      const progActs = data ? M.qualityMetric(data, { ...state, eixo: 'PROGRESSAO', subcategorias: [] }, visible.filter(c => c.eixo === 'PROGRESSAO'), 'atos') : M.vazio();
      return '<section class="exec-kpi-section" aria-label="Indicadores executivos de Progressão Funcional">' +
        '<div class="exec-kpi-grid">' +
          '<article class="exec-kpi-card tone-blue">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">DECISÕES · EIXO PROGRESSÃO</span><button type="button" class="metric-help" data-kpi="decisoes" aria-label="Entender Decisões de Progressão">ⓘ</button></div>' +
            '<strong class="exec-kpi-value">' + esc(M.metricLabel(prog)) + '</strong>' +
            '<div class="exec-kpi-meta"><span>Total do eixo no recorte</span><b>Faixa protegida</b></div>' +
          '</article>' +
          '<article class="exec-kpi-card tone-indigo">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">PROGRESSÃO VERTICAL</span><button type="button" class="text-chip" data-serie="VERTICAL">' + (state.modalidade === 'VERTICAL' ? 'Ativo ✓' : 'Filtrar →') + '</button></div>' +
            '<strong class="exec-kpi-value">' + esc(M.metricLabel(vert)) + '</strong>' +
            '<div class="exec-kpi-meta"><span>Células publicáveis no recorte</span><b>' + vertInterval + ' entre modalidades visíveis</b></div>' +
          '</article>' +
          '<article class="exec-kpi-card tone-teal">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">PROGRESSÃO HORIZONTAL</span><button type="button" class="text-chip" data-serie="HORIZONTAL">' + (state.modalidade === 'HORIZONTAL' ? 'Ativo ✓' : 'Filtrar →') + '</button></div>' +
            '<strong class="exec-kpi-value">' + esc(M.metricLabel(horiz)) + '</strong>' +
            '<div class="exec-kpi-meta"><span>Células publicáveis no recorte</span><b>' + horizInterval + ' entre modalidades visíveis</b></div>' +
          '</article>' +
          '<article class="exec-kpi-card tone-amber">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">ATOS DE PROGRESSÃO NO DOE</span></div>' +
            '<strong class="exec-kpi-value">' + esc(M.metricLabel(progActs)) + '</strong>' +
            '<div class="exec-kpi-meta"><span>Atos distintos no eixo</span><b>Em conferência</b></div>' +
          '</article>' +
          '<article class="exec-kpi-card tone-slate">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">CATÁLOGO PCCR</span></div>' +
            '<strong class="exec-kpi-value">16 grupos</strong>' +
            '<div class="exec-kpi-meta"><span>' + new Set(visible.map(c => c.grupo).filter(Boolean)).size + ' grupos com células no recorte</span><b>Ausência de célula não significa zero</b></div>' +
          '</article>' +
        '</div>' +
      '</section>';
    }

    if (page === 'tempo') {
      const tsActs = data ? M.qualityMetric(data, { ...state, eixo: 'TEMPO_SERVICO', grupo: '', modalidade: '' }, visible.filter(c => c.eixo === 'TEMPO_SERVICO'), 'atos') : M.vazio();
      return '<section class="exec-kpi-section" aria-label="Indicadores executivos de Tempo de Serviço">' +
        '<div class="exec-kpi-grid">' +
          '<article class="exec-kpi-card tone-amber">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">DECISÕES · TEMPO DE SERVIÇO</span><button type="button" class="metric-help" data-kpi="decisoes" aria-label="Entender Decisões de Tempo de Serviço">ⓘ</button></div>' +
            '<strong class="exec-kpi-value">' + esc(M.metricLabel(ts)) + '</strong>' +
            '<div class="exec-kpi-meta"><span>Resumo geral do eixo no recorte</span><b>Faixa protegida</b></div>' +
          '</article>' +
          '<article class="exec-kpi-card tone-indigo">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">ATOS IDENTIFICADOS NO EIXO</span></div>' +
            '<strong class="exec-kpi-value">' + esc(M.metricLabel(tsActs)) + '</strong>' +
            '<div class="exec-kpi-meta"><span>Atos distintos de Tempo de Serviço</span><b>Provisórios em revisão</b></div>' +
          '</article>' +
          '<article class="exec-kpi-card tone-teal">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">MODALIDADES OFICIAIS</span></div>' +
            '<strong class="exec-kpi-value">7 serviços</strong>' +
            '<div class="exec-kpi-meta"><span>TS-01 a TS-07 no catálogo oficial</span><b>Sempre selecionáveis</b></div>' +
          '</article>' +
          '<article class="exec-kpi-card tone-blue">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">PROTEÇÃO DE CÉLULAS (LGPD)</span></div>' +
            '<strong class="exec-kpi-value">Limiar ≥ 5</strong>' +
            '<div class="exec-kpi-meta"><span>Subcategorias c/ &lt; 5 matrículas/mês</span><b>Preservadas (não são zero)</b></div>' +
          '</article>' +
          '<article class="exec-kpi-card tone-slate">' +
            '<div class="exec-kpi-top"><span class="exec-kpi-tag">COBERTURA DO DOE-PB</span><a class="text-chip" href="#cobertura">Fontes →</a></div>' +
            '<strong class="exec-kpi-value">' + (cob ? esc(cob.edicoes + ' ed. · ' + cob.paginas + ' págs.') : '—') + '</strong>' +
            '<div class="exec-kpi-meta"><span>Janela lida da projeção</span><b>' + (cob ? dayLabel(cob.primeira_publicacao) + ' a ' + dayLabel(cob.ultima_publicacao) : '') + '</b></div>' +
          '</article>' +
        '</div>' +
      '</section>';
    }

    return '<section class="exec-kpi-section" aria-label="Indicadores executivos em destaque">' +
      '<div class="exec-kpi-grid">' +
        '<article class="exec-kpi-card tone-blue">' +
          '<div class="exec-kpi-top"><span class="exec-kpi-tag">DECISÕES INDIVIDUAIS · 2 EIXOS</span><button type="button" class="metric-help" data-kpi="decisoes" aria-label="Entender Total de decisões individuais">ⓘ</button></div>' +
          '<strong class="exec-kpi-value">' + esc(M.metricLabel(decision)) + '</strong>' +
          '<div class="exec-kpi-meta"><span>' + (decBounds ? (M.summaryFor(data, state) ? 'Total do recorte em faixas protegidas' : 'Soma dos agregados visíveis') : 'Recorte sem agregado divulgado') + '</span><b>' + (decBounds ? 'Provisórios em validação' : '—') + '</b></div>' +
        '</article>' +
        '<article class="exec-kpi-card tone-indigo">' +
          '<div class="exec-kpi-top"><span class="exec-kpi-tag">ATOS IDENTIFICADOS NO DOE</span><button type="button" class="metric-help" data-kpi="atos" aria-label="Entender Atos identificados">ⓘ</button></div>' +
          '<strong class="exec-kpi-value">' + esc(M.metricLabel(acts)) + '</strong>' +
          '<div class="exec-kpi-meta"><span>Atos distintos no recorte</span><b>' + (M.numberBounds(acts) ? 'Resenhas: integração pendente' : 'Não calculável no recorte') + '</b></div>' +
        '</article>' +
        '<article class="exec-kpi-card tone-teal">' +
          '<div class="exec-kpi-top"><span class="exec-kpi-tag">PROGRESSÃO FUNCIONAL (EIXO 1)</span><button type="button" class="text-chip" data-eixo-rapido="PROGRESSAO">Filtrar eixo →</button></div>' +
          '<strong class="exec-kpi-value">' + esc(M.metricLabel(prog)) + '</strong>' +
          '<div class="exec-kpi-meta"><span>Vertical: <b>' + esc(M.metricLabel(vert)) + '</b> · Horizontal: <b>' + esc(M.metricLabel(horiz)) + '</b></span><b>Faixas do recorte; cobertura parcial</b></div>' +
        '</article>' +
        '<article class="exec-kpi-card tone-amber">' +
          '<div class="exec-kpi-top"><span class="exec-kpi-tag">TEMPO DE SERVIÇO (EIXO 2 · 7 SERVIÇOS)</span><button type="button" class="text-chip" data-eixo-rapido="TEMPO_SERVICO">Filtrar eixo →</button></div>' +
          '<strong class="exec-kpi-value">' + esc(M.metricLabel(ts)) + '</strong>' +
          '<div class="exec-kpi-meta"><span>Resumo do eixo · 7 modalidades TS-01 a TS-07</span><b>Detalhamento por serviço não divulgado</b></div>' +
        '</article>' +
        '<article class="exec-kpi-card tone-slate">' +
          '<div class="exec-kpi-top"><span class="exec-kpi-tag">EDIÇÕES E PÁGINAS PROCESSADAS</span><a class="text-chip" href="#cobertura">Fontes →</a></div>' +
          '<strong class="exec-kpi-value">' + (cob ? esc(cob.edicoes + ' ed. · ' + cob.paginas + ' págs.') : '—') + '</strong>' +
          '<div class="exec-kpi-meta"><span>' + (cob ? esc((cob.edicoes - cob.ausencia_tecnica_edicoes - cob.inconclusivas) + ' edições com atos · ' + cob.ausencia_tecnica_edicoes + ' sem atos · ' + cob.inconclusivas + ' inconcl.') : 'Base documental') + '</span><b>' + (cob ? dayLabel(cob.primeira_publicacao) + ' a ' + dayLabel(cob.ultima_publicacao) : '') + '</b></div>' +
        '</article>' +
      '</div>' +
      '<div class="pending-strip" role="region" aria-label="Resumo rápido de indicadores em integração">' +
        '<div class="pending-strip-title"><span class="pending-dot" aria-hidden="true"></span><b>Indicadores em acompanhamento (sem zero falso):</b></div>' +
        '<div class="pending-strip-items">' +
          '<span class="pending-pill" title="Processos SAD-PSE distintos e número exato de resenhas dependem de agregação segura na projeção pública"><b>Processos e Resenhas:</b> base gerencial (' + esc(M.metricLabel(acts)) + ' atos identificados)</span>' +
          '<span class="pending-pill" title="Deferimentos, indeferimentos e outros resultados dependem de homologação administrativa"><b>Mérito (Deferidos / Indeferidos / Outros):</b> em conferência documental</span>' +
          '<span class="pending-pill" title="Eventos modificadores separados por natureza jurídica: ato refeito, ato tornado sem efeito e republicação por incorreção"><b>Modificadores (Refeitos · Sem efeito · Republicações por incorreção):</b> vínculo em integração</span>' +
        '</div>' +
        '<a class="pending-strip-link" href="#tituloMonitorIndicadores">Ver matriz dos 10 indicadores ↓</a>' +
      '</div>' +
    '</section>';
  }

  function cards() {
    const decision = data ? M.decisionMetric(data, state, visible) : M.vazio();
    const acts = data ? M.qualityMetric(data, state, visible, 'atos') : M.vazio();
    $('indicadores').innerHTML = kpis.map(([key, title, help, category, statusNote]) => {
      const m = key === 'decisoes' ? decision : M.vazio();
      const hasVal = M.numberBounds(m);
      const subText = hasVal
        ? (M.summaryFor(data, state) ? 'Base do recorte, em faixas protegidas' : 'Agregados publicáveis parciais')
        : data
          ? (key === 'resenhas' && M.numberBounds(acts) ? 'Não verificado · ' + M.metricLabel(acts) + ' atos identificados' : 'Não verificado / não divulgado · ' + statusNote)
          : 'Aguardando dados';
      return '<article class="metric-card ' + (hasVal ? 'available' : 'pending-metric') + '">' +
        '<div class="metric-card-cat">' + esc(category) + '</div>' +
        '<span>' + esc(title) + '</span>' +
        '<strong>' + esc(M.metricLabel(m)) + '</strong>' +
        '<small>' + esc(subText) + '</small>' +
        '<button class="metric-help" type="button" data-kpi="' + key + '" aria-label="Entender: ' + esc(title) + '">ⓘ</button>' +
      '</article>';
    }).join('');

    const compContainer = $('indicadoresComplementares');
    if (!compContainer) return;
    const cob = data?.cobertura;
    compContainer.innerHTML = extraKpis.map(([key, title, help, category]) => {
      const isCob = key === 'cobertura_doe' && cob;
      const val = isCob ? (cob.edicoes + ' edições · ' + cob.paginas + ' págs.') : '—';
      const sub = isCob
        ? ((cob.edicoes - cob.ausencia_tecnica_edicoes - cob.inconclusivas) + ' edições com atos GEDIV · ' + cob.ausencia_tecnica_edicoes + ' com ausência técnica · ' + cob.inconclusivas + ' inconclusiva')
        : (data ? 'Não verificado / não divulgado na projeção v1' : 'Aguardando dados');
      return '<article class="metric-card secondary-card ' + (isCob ? 'available' : 'pending-metric') + '">' +
        '<div class="metric-card-cat">' + esc(category) + '</div>' +
        '<span>' + esc(title) + '</span>' +
        '<strong>' + esc(val) + '</strong>' +
        '<small>' + esc(sub) + '</small>' +
        '<button class="metric-help" type="button" data-kpi-extra="' + key + '" aria-label="Entender: ' + esc(title) + '">ⓘ</button>' +
      '</article>';
    }).join('') +
    '<article class="metric-card distinction-card">' +
      '<div class="metric-card-cat">Distinção conceitual obrigatória</div>' +
      '<span>Eventos modificadores não se confundem</span>' +
      '<ul class="distinction-list">' +
        '<li><b>Republicação por incorreção:</b> corrige erro material/formal mantendo o ato original.</li>' +
        '<li><b>Ato refeito:</b> substitui o ato anterior com nova apreciação/decisão vinculada.</li>' +
        '<li><b>Tornado sem efeito:</b> anula/desconstitui a validade do ato (não é indeferimento).</li>' +
      '</ul>' +
    '</article>';
  }

  function chartControls(id, allowTypeSwitch = false) {
    const typeBtns = allowTypeSwitch ? '<div class="segment-control compact-seg" role="group" aria-label="Formato do gráfico de evolução">' +
      [['colunas', 'Colunas'], ['empilhadas', 'Empilhadas'], ['linhas', 'Linhas']].map(([k, label]) => '<button type="button" data-tipo-evolucao="' + k + '" aria-pressed="' + (evolutionType === k) + '">' + label + '</button>').join('') +
    '</div>' : '';
    return '<div class="chart-actions">' + typeBtns + '<label>Unidade <select data-unidade aria-label="Unidade do gráfico ' + id + '"><option value="decisoes"' + (chartUnit === 'decisoes' ? ' selected' : '') + '>Decisões</option><option value="atos"' + (chartUnit === 'atos' ? ' selected' : '') + '>Ocorrências de atos nas células</option></select></label><label>Período <select data-granularidade aria-label="Granularidade do gráfico ' + id + '"><option value="mes">Mensal · disponível</option><option value="semana">Semanal · não disponível</option><option value="dia">Diária · não disponível</option></select></label><button class="text-button" type="button" data-png>↓ PNG</button></div>';
  }

  function evolution(line = false, width = 700) {
    const mode = line ? 'linhas' : evolutionType;
    const isLine = mode === 'linhas';
    const isStacked = mode === 'empilhadas';
    const periods = [...new Set(visible.map(c => c.periodo))].sort();
    const values = periods.map(p => series.map(s => filteredMetric(visible.filter(c => c.periodo === p && matchesSeries(c, s.key)), chartUnit)));
    const W = Math.max(300, Math.min(1100, Math.round(width))), H = 256, left = 46, right = 18, top = 28, bottom = 44, w = W - left - right, h = H - top - bottom;
    const max = isStacked
      ? Math.max(5, ...values.map(row => row.reduce((acc, m) => acc + (M.numberBounds(m)?.max || 0), 0)))
      : Math.max(5, ...values.flatMap(row => row.map(m => M.numberBounds(m)?.max || 0)));
    let svg = '';
    if (periods.length) {
      for (const tick of [0, Math.ceil(max / 2), max]) {
        const y = top + h - tick / max * h;
        svg += '<line class="grid-line" x1="' + left + '" x2="' + (W - right) + '" y1="' + y + '" y2="' + y + '"/><text x="' + (left - 8) + '" y="' + (y + 4) + '" text-anchor="end">' + tick + '</text>';
      }
      const step = w / periods.length, bw = Math.min(36, step / 4.6);
      if (isLine) {
        series.forEach((s, j) => {
          let previous = null;
          periods.forEach((p, i) => {
            const b = M.numberBounds(values[i][j]);
            if (!b) { previous = null; return; }
            const x = left + step * (i + .5), y = top + h - b.min / max * h, serial = Number(p.slice(0, 4)) * 12 + Number(p.slice(5));
            if (previous && serial === previous.serial + 1) svg += '<line x1="' + previous.x + '" y1="' + previous.y + '" x2="' + x + '" y2="' + y + '" stroke="' + s.color + '" stroke-width="3"/>';
            previous = { x, y, serial };
          });
        });
      }
      periods.forEach((p, i) => {
        if (isStacked) {
          let stackMin = 0;
          const stackW = Math.min(54, step * 0.48);
          const x = left + step * (i + .5) - stackW / 2;
          values[i].forEach((m, j) => {
            const b = M.numberBounds(m);
            if (!b) return;
            const segH = Math.max(2, b.min / max * h);
            const y = top + h - (stackMin / max * h) - segH;
            const label = monthLabel(p) + ' · ' + series[j].name + ': ' + M.metricLabel(m) + ' ' + (chartUnit === 'decisoes' ? 'decisões' : 'ocorrências de atos') + '. Selecionar mês.';
            svg += '<g class="chart-hit" role="button" tabindex="0" data-mes="' + p + '" aria-label="' + esc(label) + '"><title>' + esc(label) + '</title>' +
              '<rect x="' + x + '" y="' + y + '" width="' + stackW + '" height="' + segH + '" rx="3" fill="' + series[j].color + '"/>' +
              '<text x="' + (x + stackW / 2) + '" y="' + (y - 6) + '" text-anchor="middle">' + esc(M.metricLabel(m)) + '</text></g>';
            stackMin += b.min;
          });
        } else {
          values[i].forEach((m, j) => {
            const b = M.numberBounds(m);
            if (!b) return;
            const x = left + step * (i + .5) + (isLine ? 0 : (j - 1.5) * (bw + 6)), y = top + h - b.min / max * h, high = top + h - b.max / max * h;
            const label = monthLabel(p) + ' · ' + series[j].name + ': ' + M.metricLabel(m) + ' ' + (chartUnit === 'decisoes' ? 'decisões' : 'ocorrências de atos') + '. Selecionar mês.';
            svg += '<g class="chart-hit" role="button" tabindex="0" data-mes="' + p + '" aria-label="' + esc(label) + '"><title>' + esc(label) + '</title>';
            if (isLine) svg += '<line x1="' + x + '" x2="' + x + '" y1="' + high + '" y2="' + y + '" stroke="' + series[j].color + '" stroke-width="7" opacity=".3"/><circle class="line-mark" cx="' + x + '" cy="' + y + '" r="6" stroke="' + series[j].color + '"/>';
            else svg += '<rect x="' + x + '" y="' + y + '" width="' + bw + '" height="' + Math.max(2, b.min / max * h) + '" rx="4" fill="' + series[j].color + '"/><rect class="range-tail" x="' + x + '" y="' + high + '" width="' + bw + '" height="' + (b.max - b.min) / max * h + '" rx="4" fill="' + series[j].color + '"/>';
            svg += '<text x="' + (x + (isLine ? 0 : bw / 2)) + '" y="' + (high - 7) + '" text-anchor="middle">' + esc(M.metricLabel(m)) + '</text></g>';
          });
        }
        svg += '<text x="' + (left + step * (i + .5)) + '" y="' + (H - 15) + '" text-anchor="middle" font-weight="600">' + esc(monthLabel(p)) + '</text>';
      });
    }
    const body = chartControls(line ? 'histórico' : 'evolução', !line) +
      (svg ? '<div class="chart-box" data-plot-kind="' + (line ? 'line' : 'bars') + '"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + H + '" role="group" aria-label="' + (isLine ? 'Linhas' : isStacked ? 'Barras empilhadas' : 'Colunas agrupadas') + ' por mês, limites das faixas publicáveis">' + svg + '</svg></div>' : empty('Sem agregado publicável no recorte', (M.selectionIssue(state) || M.coverageIssue(data, state)) || 'Dados preservados ou não divulgados. Isso não confirma ausência de publicação.')) +
      legend() +
      '<p class="data-note">Clique em qualquer mês para filtrar o painel. Parte sólida: limite inferior; parte clara: teto da faixa.</p>' +
      alternative(['Mês', ...series.map(s => s.name)], periods.map((p, i) => [monthLabel(p), ...values[i].map(M.metricLabel)]), 'Mesmos dados do gráfico · ' + (chartUnit === 'decisoes' ? 'decisões' : 'ocorrências de atos') + ' em faixas');
    return panel(line ? 'Evolução histórica em linha (lacunas preservadas)' : 'Evolução mensal das publicações', line ? 'Une apenas meses consecutivos verificados' : 'Compare meses e modalidades · clique na barra para filtrar o mês', body);
  }

  function donut(ts = false) {
    const items = ts
      ? data.catalogo.subcategorias.map((s, i) => ({ key: s.codigo, name: s.codigo + ' · ' + s.nome, color: colors[i], metric: filteredMetric(visible.filter(c => c.eixo === 'TEMPO_SERVICO' && c.subcategoria === s.codigo)) }))
      : series.map(s => ({ ...s, metric: filteredMetric(visible.filter(c => matchesSeries(c, s.key))) }));
    const present = items.filter(i => M.numberBounds(i.metric));
    const total = M.sumMetrics(present.map(i => i.metric)), sumMin = present.reduce((n, i) => n + M.numberBounds(i.metric).min, 0);
    const isPie = !ts && subjectChartType === 'pizza';
    const radius = isPie ? 30 : 43;
    let offset = 0;
    const paths = present.map(i => {
      const size = sumMin ? M.numberBounds(i.metric).min / sumMin * 100 : 0;
      const path = '<circle class="chart-hit ' + (isPie ? 'pie-slice' : '') + '" cx="60" cy="60" r="' + radius + '" pathLength="100" stroke="' + i.color + '" stroke-dasharray="' + size + ' ' + (100 - size) + '" stroke-dashoffset="' + (-offset) + '" role="button" tabindex="0" data-' + (ts ? 'sub' : 'serie') + '="' + i.key + '" aria-label="Filtrar ' + esc(i.name) + '"><title>' + esc(i.name + ': ' + M.metricLabel(i.metric)) + '</title></circle>';
      offset += size;
      return path;
    }).join('');
    const rows = items.map(i => [i.name, M.metricLabel(i.metric), M.shareLabel(M.shareInterval(i.metric, present.map(x => x.metric)))]);
    const tsSummary = axisMetric('TEMPO_SERVICO');
    const progSummary = axisMetric('PROGRESSAO');
    const modeControls = !ts ? '<div class="segment-control compact-seg" role="group" aria-label="Formato do gráfico por assunto"><button type="button" data-formato-assunto="rosca" aria-pressed="' + (subjectChartType === 'rosca') + '">Rosca</button><button type="button" data-formato-assunto="pizza" aria-pressed="' + (subjectChartType === 'pizza') + '">Pizza</button></div>' : '';
    const extraAxisNote = !ts && M.numberBounds(tsSummary) && !present.some(p => p.key === 'TEMPO_SERVICO')
      ? '<div class="axis-summary-callout"><span><b>Resumo por eixo na base:</b> Progressão Funcional: <b>' + esc(M.metricLabel(progSummary)) + '</b> · Tempo de Serviço: <b>' + esc(M.metricLabel(tsSummary)) + '</b> (células mensais por subcategoria TS preservadas por terem &lt; 5 decisões).</span></div>'
      : '';
    const body = '<div class="donut-layout"><div class="donut ' + (isPie ? 'is-pie' : '') + '"><svg viewBox="0 0 120 120" role="group" aria-label="Distribuição dos limites inferiores das faixas publicáveis"><circle cx="60" cy="60" r="' + radius + '"/>' + paths + '</svg>' +
      (!isPie ? '<div class="donut-center"><b>' + esc(M.metricLabel(total)) + '</b><small>' + (present.length ? 'decisões nas células' : 'Células < 5 preservadas') + '</small></div>' : '') +
      '</div><div class="donut-legend">' +
      (isPie ? '<div class="pie-total-badge">Total nos agregados exibidos: <b>' + esc(M.metricLabel(total)) + '</b></div>' : '') +
      items.map((i, k) => '<button type="button" data-' + (ts ? 'sub' : 'serie') + '="' + i.key + '" title="Consultar ' + esc(i.name) + '"><i class="swatch" style="--series:' + i.color + '"></i><span>' + esc(i.name) + ' <b>' + esc(M.metricLabel(i.metric)) + '</b><small>' + (M.numberBounds(i.metric) ? esc(rows[k][2]) + ' entre agregados exibidos' : (i.key === 'TEMPO_SERVICO' && M.numberBounds(tsSummary) ? M.metricLabel(tsSummary) + ' no resumo do eixo · detalhamento preservado' : 'Não divulgado / célula < 5')) + '</small></span></button>').join('') +
      '</div></div>' + extraAxisNote +
      '<p class="data-note">Arcos proporcionais aos limites inferiores. Clique em uma fatia ou item da legenda para filtrar.</p>' +
      alternative(['Assunto', 'Decisões (faixa)', '% entre agregados exibidos (faixa)'], rows, 'Sem inferência sobre células suprimidas');
    return panel(ts ? 'Distribuição de Tempo de Serviço por modalidade' : 'Distribuição por assunto (Rosca / Pizza)', ts ? 'Sete serviços oficiais TS-01 a TS-07' : 'Proporção entre modalidades com células publicáveis · clique para filtrar', body, modeControls);
  }

  function comparisonProg() {
    const vertCells = visible.filter(c => c.eixo === 'PROGRESSAO' && c.modalidade === 'VERTICAL');
    const horizCells = visible.filter(c => c.eixo === 'PROGRESSAO' && c.modalidade === 'HORIZONTAL');
    const vertDec = filteredMetric(vertCells, 'decisoes');
    const horizDec = filteredMetric(horizCells, 'decisoes');
    const vertAtos = filteredMetric(vertCells, 'atos');
    const horizAtos = filteredMetric(horizCells, 'atos');
    const vb = M.numberBounds(vertDec), hb = M.numberBounds(horizDec);
    const totalMin = (vb?.min || 0) + (hb?.min || 0);
    const vPct = totalMin ? Math.round((vb?.min || 0) / totalMin * 100) : 50;
    const hPct = totalMin ? 100 - vPct : 50;

    const periods = [...new Set(data.celulas.map(c => c.periodo))].sort().slice(-2);
    const firstPeriod = periods[0], lastPeriod = periods.at(-1);
    const periodCaption = periods.map(monthLabel).join(' → ');
    const outVert = filteredMetric(vertCells.filter(c => c.periodo === firstPeriod), 'decisoes');
    const novVert = filteredMetric(vertCells.filter(c => c.periodo === lastPeriod), 'decisoes');
    const outHoriz = filteredMetric(horizCells.filter(c => c.periodo === firstPeriod), 'decisoes');
    const novHoriz = filteredMetric(horizCells.filter(c => c.periodo === lastPeriod), 'decisoes');

    const body = '<div class="comp-grid">' +
      '<div class="comp-card comp-vert">' +
        '<div class="comp-card-head"><span class="swatch" style="--series:' + colors[0] + '"></span><b>Progressão Vertical</b><button type="button" class="text-chip" data-serie="VERTICAL">' + (state.modalidade === 'VERTICAL' ? 'Filtro ativo ✓' : 'Filtrar Vertical') + '</button></div>' +
        '<div class="comp-main-num"><strong>' + esc(M.metricLabel(vertDec)) + '</strong><span>decisões nas células</span></div>' +
        '<div class="comp-sub-stats">' +
          '<div><small>Ocorrências de atos</small><b>' + esc(M.metricLabel(vertAtos)) + '</b></div>' +
          '<div><small>' + esc(periodCaption) + '</small><b>' + esc(M.metricLabel(outVert)) + ' → ' + esc(M.metricLabel(novVert)) + '</b></div>' +
          '<div><small>Grupos PCCR nas células</small><b>Grupo não informado</b></div>' +
        '</div>' +
      '</div>' +
      '<div class="comp-card comp-horiz">' +
        '<div class="comp-card-head"><span class="swatch" style="--series:' + colors[1] + '"></span><b>Progressão Horizontal</b><button type="button" class="text-chip" data-serie="HORIZONTAL">' + (state.modalidade === 'HORIZONTAL' ? 'Filtro ativo ✓' : 'Filtrar Horizontal') + '</button></div>' +
        '<div class="comp-main-num"><strong>' + esc(M.metricLabel(horizDec)) + '</strong><span>decisões nas células</span></div>' +
        '<div class="comp-sub-stats">' +
          '<div><small>Ocorrências de atos</small><b>' + esc(M.metricLabel(horizAtos)) + '</b></div>' +
          '<div><small>' + esc(periodCaption) + '</small><b>' + esc(M.metricLabel(outHoriz)) + ' → ' + esc(M.metricLabel(novHoriz)) + '</b></div>' +
          '<div><small>Grupos PCCR divulgados</small><b>' + esc([...new Set(horizCells.map(c => c.grupo).filter(Boolean))].join(', ') || 'Não divulgado') + '</b></div>' +
        '</div>' +
      '</div>' +
    '</div>' +
    '<div class="comp-stacked-bar-wrap">' +
      '<div class="comp-bar-labels"><span>Vertical: <b>' + (totalMin ? vPct + '%' : '—') + '</b> (lim. inf.)</span><span>Horizontal: <b>' + (totalMin ? hPct + '%' : '—') + '</b> (lim. inf.)</span></div>' +
      '<div class="comp-stacked-bar" role="img" aria-label="Barra empilhada comparativa entre Progressão Vertical e Horizontal">' +
        (totalMin ? '<span class="comp-seg-v" style="width:' + vPct + '%"></span><span class="comp-seg-h" style="width:' + hPct + '%"></span>' : '<span class="comp-seg-empty">Sem agregado no recorte</span>') +
      '</div>' +
    '</div>' +
    alternative(
      ['Modalidade', 'Decisões (faixa)', 'Ocorrências de atos', monthLabel(firstPeriod), monthLabel(lastPeriod)],
      [
        ['Progressão Vertical', M.metricLabel(vertDec), M.metricLabel(vertAtos), M.metricLabel(outVert), M.metricLabel(novVert)],
        ['Progressão Horizontal', M.metricLabel(horizDec), M.metricLabel(horizAtos), M.metricLabel(outHoriz), M.metricLabel(novHoriz)]
      ],
      'Comparativo direto entre Progressão Vertical e Progressão Horizontal'
    );
    return panel('Comparativo: Progressão Vertical × Progressão Horizontal', 'Barras empilhadas, evolução mensal e distribuição por modalidade do eixo Progressão', body, pill('Eixo Progressão: ' + M.metricLabel(axisMetric('PROGRESSAO')), 'conferido'));
  }

  function bars(ts = false) {
    const rawItems = ts ? data.catalogo.subcategorias : [...data.catalogo.grupos, { codigo: 'NAO_INFORMADO', nome: 'Grupo não informado (Progressão Vertical)' }];
    const mapped = rawItems.map(i => {
      const metric = filteredMetric(visible.filter(c => c.eixo === (ts ? 'TEMPO_SERVICO' : 'PROGRESSAO') && (ts ? c.subcategoria === i.codigo : i.codigo === 'NAO_INFORMADO' ? c.grupo === null : c.grupo === i.codigo)));
      return { item: i, metric, bounds: M.numberBounds(metric) };
    });
    if (!ts) {
      mapped.sort((a, b) => (b.bounds?.min ?? -1) - (a.bounds?.min ?? -1));
    }
    const present = mapped.map(m => m.metric).filter(M.numberBounds);
    const max = Math.max(1, ...present.map(m => M.numberBounds(m).max));
    const controls = '<div class="segment-control compact-seg" role="group" aria-label="Medida das barras"><button type="button" data-medida="quantidade" aria-pressed="' + (graphMeasure === 'quantidade') + '">Quantidade</button><button type="button" data-medida="percentual" aria-pressed="' + (graphMeasure === 'percentual') + '">%</button></div>';

    const renderRow = ({ item: i, metric, bounds: b }) => {
      const perc = M.shareInterval(metric, present);
      const current = ts ? state.subcategorias.includes(i.codigo) : state.grupo === i.codigo;
      return '<button type="button" class="bar-row ' + (b ? 'has-data' : 'no-data') + '" data-' + (ts ? 'sub' : 'grupo') + '="' + i.codigo + '" aria-pressed="' + current + '" aria-label="' + esc(i.codigo + ', ' + i.nome + ', ' + (b ? M.metricLabel(metric) + ' decisões' : 'não divulgado')) + '">' +
        '<span class="bar-label"><b>' + esc(i.codigo === 'NAO_INFORMADO' ? 'Não informado' : i.codigo) + '</b><small>' + esc(i.nome) + '</small></span>' +
        '<span class="bar-track" style="--series:' + (ts ? colors[2] : (i.codigo === 'NAO_INFORMADO' ? colors[0] : colors[1])) + '" aria-hidden="true">' +
          (b ? '<i style="width:' + (graphMeasure === 'quantidade' ? b.min / max * 100 : perc?.min || 0) + '%"></i><i class="tail" style="width:' + (graphMeasure === 'quantidade' ? (b.max - b.min) / max * 100 : (perc?.max || 0) - (perc?.min || 0)) + '%"></i>' : '<span class="bar-preserved-label">Célula &lt; 5 preservada</span>') +
        '</span>' +
        '<span class="bar-value">' + (b ? '<b>' + esc(graphMeasure === 'quantidade' ? M.metricLabel(metric) : M.shareLabel(perc)) + '</b>' : '—<small class="unavailable"> Preservado</small>') + '</span>' +
      '</button>';
    };

    let listHTML = '';
    if (!ts) {
      const withData = mapped.filter(m => m.bounds || state.grupo === m.item.codigo);
      const withoutData = mapped.filter(m => !m.bounds && state.grupo !== m.item.codigo);
      const topRows = (withData.length ? withData : mapped.slice(0, 5)).map(renderRow).join('');
      const restRows = (withData.length ? withoutData : mapped.slice(5)).map(renderRow).join('');
      listHTML = '<div class="bar-list">' + topRows + '</div>' +
        (restRows ? '<details class="more-bars"><summary>Ver demais ' + (withData.length ? withoutData.length : mapped.length - 5) + ' grupos do catálogo PCCR sem agregado divulgado neste recorte</summary><div class="bar-list secondary-bar-list">' + restRows + '</div></details>' : '');
    } else {
      const tsAxis = axisMetric('TEMPO_SERVICO');
      const tsActs = data?.resumo_eixos?.TEMPO_SERVICO?.atos || M.vazio();
      const tsHeader = '<div class="ts-axis-banner">' +
        '<div><b>Total do eixo Tempo de Serviço no recorte: ' + esc(M.metricLabel(tsAxis)) + ' decisões</b><p>Atos identificados no eixo: <b>' + esc(M.metricLabel(tsActs)) + '</b>. As 7 modalidades oficiais estão listadas abaixo; subcategorias com menos de 5 decisões por mês ficam preservadas por privacidade (LGPD).</p></div>' +
        pill('7 modalidades oficiais', 'provisorio') +
      '</div>';
      listHTML = tsHeader + '<div class="bar-list">' + mapped.map(renderRow).join('') + '</div>';
    }

    return panel(
      ts ? 'Sete modalidades de Tempo de Serviço (TS-01 a TS-07)' : 'Progressão por grupo ocupacional do PCCR (16 grupos)',
      ts ? 'Selecione uma ou mais modalidades para filtrar · resumo do eixo preservado' : 'Grupos com faixas divulgadas em destaque · clique em uma barra para filtrar',
      listHTML + '<p class="data-note">Decisões em faixas. % = intervalo entre agregados exibidos. — indica recorte preservado (&lt; 5) ou não disponível; nunca zero falso.</p>' +
      alternative(['Categoria', 'Decisões (faixa)', '% exibido (faixa)'], mapped.map(({ item: i, metric }) => [i.codigo + ' · ' + i.nome, M.metricLabel(metric), M.shareLabel(M.shareInterval(metric, present))])),
      controls
    );
  }

  function results(kind = '') {
    const activeKind = kind || resultsDimension;
    const items = activeKind === 'ts'
      ? data.catalogo.subcategorias.map(i => ({
          name: i.codigo + ' · ' + i.nome,
          key: i.codigo,
          attr: 'sub',
          provisorio: filteredMetric(visible.filter(c => c.eixo === 'TEMPO_SERVICO' && c.subcategoria === i.codigo && c.situacao === 'provisorio')),
          conferido: filteredMetric(visible.filter(c => c.eixo === 'TEMPO_SERVICO' && c.subcategoria === i.codigo && c.situacao === 'conferido'))
        }))
      : activeKind === 'grupos'
        ? [...data.catalogo.grupos, { codigo: 'NAO_INFORMADO', nome: 'Grupo não informado' }].filter(i => ['NAO_INFORMADO', 'GPC', 'GAJ', 'MAG', 'SSA'].includes(i.codigo)).map(i => ({
            name: i.codigo + ' · ' + i.nome,
            key: i.codigo,
            attr: 'grupo',
            provisorio: filteredMetric(visible.filter(c => c.eixo === 'PROGRESSAO' && (i.codigo === 'NAO_INFORMADO' ? c.grupo === null : c.grupo === i.codigo) && c.situacao === 'provisorio')),
            conferido: filteredMetric(visible.filter(c => c.eixo === 'PROGRESSAO' && (i.codigo === 'NAO_INFORMADO' ? c.grupo === null : c.grupo === i.codigo) && c.situacao === 'conferido'))
          }))
        : series.map(s => ({
            ...s,
            attr: 'serie',
            provisorio: s.key === 'TEMPO_SERVICO' && !visible.some(c => c.eixo === 'TEMPO_SERVICO') ? axisMetric('TEMPO_SERVICO') : filteredMetric(visible.filter(c => matchesSeries(c, s.key) && c.situacao === 'provisorio')),
            conferido: filteredMetric(visible.filter(c => matchesSeries(c, s.key) && c.situacao === 'conferido'))
          }));

    const dimSwitch = !kind ? '<div class="segment-control compact-seg" role="group" aria-label="Recorte de resultados">' +
      [['area', 'Por área'], ['grupos', 'Principais grupos PCCR'], ['ts', 'Modalidades TS']].map(([k, label]) => '<button type="button" data-dim-resultado="' + k + '" aria-pressed="' + (resultsDimension === k) + '">' + label + '</button>').join('') +
    '</div>' : pill('Mérito em conferência', 'neutral');

    const body = '<div class="chart-legend">' +
      '<span class="legend-item"><i class="swatch" style="--series:var(--green)"></i>Deferido (pendente na projeção v1)</span>' +
      '<span class="legend-item"><i class="swatch" style="--series:var(--red)"></i>Indeferido (pendente na projeção v1)</span>' +
      '<span class="legend-item"><i class="swatch" style="--series:var(--orange)"></i>Volume extraído em conferência (provisório)</span>' +
    '</div>' +
    items.map(i => {
      const pb = M.numberBounds(i.provisorio);
      return '<div class="result-row">' +
        '<button class="text-button result-label-btn" type="button" data-' + i.attr + '="' + i.key + '">' + esc(i.name) + '</button>' +
        '<span class="result-track stacked-swatch">' +
          (pb ? '<span class="result-prov-fill" style="width:100%">' + esc(M.metricLabel(i.provisorio)) + ' decisões extraídas · mérito em conferência</span>' : 'Mérito não verificado / célula preservada') +
        '</span>' +
        '<span class="result-note">' + (pb ? 'Aguarda homologação' : 'Resultado não divulgado') + '</span>' +
      '</div>';
    }).join('') +
    '<p class="data-note">A projeção pública v1 informa o volume de decisões extraídas em conferência administrativa, mas ainda não desagrega Deferidos, Indeferidos e Outros resultados por célula.</p>' +
    alternative(
      ['Área / modalidade', 'Decisões em conferência', 'Deferidos', 'Indeferidos', 'Outros'],
      items.map(i => [i.name, M.metricLabel(i.provisorio), 'Não verificado', 'Não verificado', 'Não verificado'])
    );
    return panel(
      activeKind === 'ts' ? 'Deferimentos, indeferimentos e situação · Tempo de Serviço' : activeKind === 'grupos' ? 'Deferimentos, indeferimentos e situação · Grupos PCCR' : 'Deferimentos, indeferimentos e situação por área e modalidade',
      'Situação das decisões extraídas e disponibilidade dos resultados de mérito',
      body,
      dimSwitch
    );
  }

  function pageControls(info, target) {
    return '<div class="pagination"><button type="button" data-paginar="' + target + ':anterior" aria-label="Página anterior de ' + target + '"' + (info.page === 0 ? ' disabled' : '') + '>‹</button><span>' + (info.total ? (info.page * pageSize + 1) + '–' + Math.min((info.page + 1) * pageSize, info.total) + ' de ' + info.total : 'Nenhum agregado') + ' · ' + (info.page + 1) + '/' + info.pages + '</span><button type="button" data-paginar="' + target + ':proxima" aria-label="Próxima página de ' + target + '"' + (info.page + 1 >= info.pages ? ' disabled' : '') + '>›</button><label>Exibir<select data-tamanho aria-label="Itens por página"><option value="5"' + (pageSize === 5 ? ' selected' : '') + '>5</option><option value="10"' + (pageSize === 10 ? ' selected' : '') + '>10</option><option value="10000"' + (pageSize === 10000 ? ' selected' : '') + '>Todos</option></select></label></div>';
  }

  function queryPanel() {
    const items = M.sortCells(M.searchCells(visible, query, data.catalogo)), info = M.pagination(items, queryPage, pageSize);
    queryPage = info.page;
    const tabs = '<div class="query-tabs" role="group" aria-label="Forma de consulta">' + [['agregados', 'Agregados (' + items.length + ')'], ['resenha', 'Por resenha'], ['processo', 'Por processo']].map(([key, name]) => '<button type="button" data-consulta="' + key + '" aria-pressed="' + (queryMode === key) + '">' + name + '</button>').join('') + '</div>';
    const search = '<div class="search-field"><label for="buscaLista">Pesquisar nos agregados públicos</label><input type="search" id="buscaLista" autocomplete="off" maxlength="100" placeholder="Ex.: nov/2026, GPC, GAJ, Vertical..." value="' + esc(query) + '"></div>';
    let body;
    if (queryMode !== 'agregados') {
      body = empty(
        queryMode === 'resenha' ? 'Resenhas individuais em integração' : 'Consulta por processo restrita (LGPD)',
        queryMode === 'resenha'
          ? 'A projeção pública atual informa ' + M.metricLabel(data.resumo.atos) + ' atos distintos na base completa, sem lista nominal de resenhas. Os agregados mensais não são convertidos em resenhas fictícias.'
          : 'Nome, matrícula, número de processo (SAD-PSE) e evidências individuais exigem autenticação no servidor gerencial.',
        true
      ) + '<div class="detail-actions"><a class="button primary" href="#gerencial">Entender o acesso gerencial</a><button type="button" class="button" data-consulta="agregados">Voltar aos agregados</button></div>';
    } else {
      body = search + '<div id="listaConsulta">' + (info.items.length ? '<div class="query-list">' + info.items.map(c =>
        '<details class="query-item" data-item="' + esc(cellKey(c)) + '"' + (selected && cellKey(selected) === cellKey(c) ? ' open' : '') + '>' +
          '<summary>' +
            '<div class="query-item-main">' +
              '<div class="query-item-badges"><span class="month-badge">' + esc(monthLabel(c.periodo)) + '</span>' + pill(c.situacao === 'conferido' ? 'Conferido' : 'Provisório', c.situacao) + '</div>' +
              '<b>' + esc(cellTitle(c)) + '</b>' +
              '<small>' + esc(cellCategory(c)) + '</small>' +
            '</div>' +
            '<div class="query-item-metric"><strong>' + esc(M.metricLabel(c.decisoes)) + '</strong><small>decisões · ' + esc(M.metricLabel(c.atos)) + ' atos</small></div>' +
          '</summary>' +
          '<div>' +
            '<p><b>Categoria:</b> ' + esc(cellCategory(c)) + '</p>' +
            '<p class="field-note">Agregado mensal protegido; clique abaixo para inspecionar a ficha documental completa e proveniência.</p>' +
            '<button type="button" class="button primary compact" data-detalhe="' + esc(cellKey(c)) + '">Ver ficha do agregado →</button>' +
          '</div>' +
        '</details>'
      ).join('') + '</div>' : empty('Nenhum agregado encontrado', query ? 'Tente outro mês, grupo ou modalidade. A busca não consulta dados individuais.' : 'Dados preservados ou sem agregado publicável neste recorte.')) + pageControls(info, 'lista') + '</div>' +
      '<div class="query-footer-actions"><button class="text-button" type="button" data-exportar-lista' + (!items.length ? ' disabled' : '') + '>↓ Exportar lista (CSV)</button><a class="text-button" href="#cobertura">Fontes oficiais →</a></div>';
    }
    return panel('Publicações, resenhas e processos', 'Navegação documental sincronizada com os filtros ativos', tabs + body, '<button type="button" class="button compact" data-expandir-lista aria-label="Ampliar a lista de agregados">⛶ Ampliar</button>');
  }

  function detailContent(c, expanded = false) {
    const activeCell = c || (!expanded && visible.length ? visible[0] : null);
    if (!activeCell) return empty('Selecione um agregado na lista', 'Abra um item em Publicações, resenhas e processos para consultar a ficha documental, o período e a proveniência.');
    let html = (!c && !expanded ? '<div class="auto-preview-banner">Exibindo prévia do 1º agregado visível · clique em qualquer item acima para trocar</div>' : '') +
      '<dl class="detail-list">' +
        definition('Período', monthLabel(activeCell.periodo)) +
        definition('Eixo', M.EIXOS[activeCell.eixo]) +
        definition('Modalidade', activeCell.modalidade ? M.MODALIDADES[activeCell.modalidade] : activeCell.subcategoria ? activeCell.subcategoria + ' · ' + subName(activeCell.subcategoria) : 'Não extraído') +
        definition('Grupo PCCR', activeCell.eixo === 'PROGRESSAO' ? groupName(activeCell.grupo) : 'Não se aplica') +
        definition('Decisões', M.metricLabel(activeCell.decisoes) + ' (faixa publicável)') +
        definition('Atos nesta célula', M.metricLabel(activeCell.atos) + ' (não somar como atos distintos)') +
        definition('Conferência', activeCell.situacao === 'conferido' ? 'Conferido' : 'Provisório · aguarda conferência') +
        definition('Resenha / ato', 'Não extraído na projeção pública') +
        definition('Página no DOE', 'Não extraído na projeção pública') +
      '</dl>';
    if (expanded) {
      html += '<h3>Origem e limites desta ficha</h3><dl class="detail-list">' +
        definition('Fonte', 'Diário Oficial do Estado da Paraíba') +
        definition('Projeção gerada', timestamp(data.atualizado_em) + ' (Brasília)') +
        definition('Versão das regras', data.versao_regras) +
        definition('Arquivo público', 'dados.json · contrato público versão 1') +
        definition('Unidade', 'Decisão individual contada em agregado mensal; sem identidade individual') +
        definition('PDF e página oficial', 'Não extraído; nenhuma URL individual inferida') +
        definition('Evidência e revisão individual', 'Acesso gerencial seguro necessário') +
      '</dl><p class="data-note">Uma faixa não revela o valor exato. Um registro pode participar de várias ocorrências; atos, processos e pessoas não são unidades intercambiáveis.</p>';
    }
    return html +
      '<div class="hierarchy-trail" aria-label="Trilha de navegação documental em 7 níveis">' +
        '<span class="trail-step done">1. Eixo</span><span class="trail-sep">›</span>' +
        '<span class="trail-step done">2. Modalidade</span><span class="trail-sep">›</span>' +
        '<span class="trail-step done">3. Grupo/Serviço</span><span class="trail-sep">›</span>' +
        '<span class="trail-step done">4. Agregado mensal</span><span class="trail-sep">›</span>' +
        '<span class="trail-step locked" title="Disponível na área gerencial autenticada">5. Resenha ◇</span><span class="trail-sep">›</span>' +
        '<span class="trail-step locked" title="Disponível na área gerencial autenticada">6. Processo ◇</span><span class="trail-sep">›</span>' +
        '<span class="trail-step locked" title="Disponível na área gerencial autenticada">7. PDF DOE ◇</span>' +
      '</div>' +
      '<div class="detail-actions">' +
        (!expanded ? '<button type="button" class="button primary compact" data-detalhe="' + esc(cellKey(activeCell)) + '">Entender este agregado</button>' : '<button type="button" class="button" data-exportar-item="' + esc(cellKey(activeCell)) + '">↓ Exportar agregado (CSV)</button>') +
        '<a class="button compact" href="#cobertura">Edições e fontes</a>' +
      '</div>';
  }

  function recordsPanel() {
    const rows = M.sortCells(visible, tableSort, sortDirection), info = M.pagination(rows, tablePage, pageSize);
    tablePage = info.page;
    const headers = [['periodo', 'Mês'], ['eixo', 'Eixo / modalidade'], ['categoria', 'Grupo / serviço'], ['situacao', 'Conferência'], ['atos', 'Atos na célula'], ['decisoes', 'Decisões']];
    const body = '<div class="table-scroll"><table><caption>Agregados mensais publicáveis · faixas protegidas. Não são registros individuais.</caption><thead><tr>' + headers.map(([key, title]) => '<th scope="col" aria-sort="' + (tableSort === key ? sortDirection === 1 ? 'ascending' : 'descending' : 'none') + '"><button type="button" data-ordenar="' + key + '">' + esc(title) + (tableSort === key ? sortDirection === 1 ? ' ↑' : ' ↓' : ' ↕') + '</button></th>').join('') + '<th scope="col">Consulta</th></tr></thead><tbody>' + (info.items.length ? info.items.map(c => '<tr><td><b>' + esc(monthLabel(c.periodo)) + '</b></td><td>' + esc(cellTitle(c)) + '</td><td>' + esc(cellCategory(c)) + '</td><td>' + pill(c.situacao === 'conferido' ? 'Conferido' : 'Provisório', c.situacao) + '</td><td>' + esc(M.metricLabel(c.atos)) + '</td><td><b>' + esc(M.metricLabel(c.decisoes)) + '</b></td><td><button class="table-button" type="button" data-detalhe="' + esc(cellKey(c)) + '">Entender agregado →</button></td></tr>').join('') : '<tr><td colspan="7">Não há agregados publicáveis neste recorte. Isso não confirma ausência de publicações.</td></tr>') + '</tbody></table></div>' + pageControls(info, 'tabela') + '<p class="data-note">Os totais da base incluem recortes que não podem ser divulgados. Atos podem repetir entre células; não some esta coluna como atos distintos. Exportações incluem todas as páginas da seleção.</p>';
    return panel('Tabela de consulta dos agregados disponíveis', visible.length + ' agregado(s) neste recorte · ordenar, consultar ficha ou exportar', body, '<button class="button compact" type="button" data-ver-todos>Ver todos os agregados</button>', 'records');
  }

  function coveragePanel() {
    const c = data.cobertura;
    const totalEd = c.edicoes;
    const comAtos = c.edicoes_com_atos ?? Math.max(0, totalEd - (c.ausencia_tecnica_edicoes || 0) - (c.inconclusivas || 0));
    const semAtos = c.ausencia_tecnica_edicoes || 0;
    const inconc = c.inconclusivas || 0;
    const p1 = totalEd ? comAtos / totalEd * 100 : 0;
    const p2 = totalEd ? semAtos / totalEd * 100 : 0;
    const p3 = totalEd ? inconc / totalEd * 100 : 0;

    const ringSVG = '<div class="coverage-ring-box">' +
      '<div class="coverage-ring">' +
        '<svg viewBox="0 0 120 120" role="img" aria-label="Anel de cobertura das ' + esc(totalEd) + ' edições processadas">' +
          '<circle cx="60" cy="60" r="44" fill="none" stroke="var(--bg)" stroke-width="16"/>' +
          '<circle cx="60" cy="60" r="44" fill="none" stroke="var(--green)" stroke-width="16" pathLength="100" stroke-dasharray="' + p1 + ' ' + (100 - p1) + '" stroke-dashoffset="0"/>' +
          '<circle cx="60" cy="60" r="44" fill="none" stroke="var(--blue)" stroke-width="16" pathLength="100" stroke-dasharray="' + p2 + ' ' + (100 - p2) + '" stroke-dashoffset="' + (-p1) + '"/>' +
          '<circle cx="60" cy="60" r="44" fill="none" stroke="var(--orange)" stroke-width="16" pathLength="100" stroke-dasharray="' + p3 + ' ' + (100 - p3) + '" stroke-dashoffset="' + (-(p1 + p2)) + '"/>' +
        '</svg>' +
        '<div class="coverage-ring-center"><b>' + esc(totalEd) + '</b><small>edições lidas</small></div>' +
      '</div>' +
      '<div class="coverage-ring-legend">' +
        '<div><i class="swatch" style="--series:var(--green)"></i><span><b>' + esc(comAtos) + ' edições</b> com atos GEDIV extraídos (' + Math.round(p1) + '%)</span></div>' +
        '<div><i class="swatch" style="--series:var(--blue)"></i><span><b>' + esc(semAtos) + ' edições</b> com ausência técnica proposta (' + Math.round(p2) + '%)</span></div>' +
        '<div><i class="swatch" style="--series:var(--orange)"></i><span><b>' + esc(inconc) + ' edição</b> com leitura inconclusiva (' + Math.round(p3) + '%)</span></div>' +
      '</div>' +
    '</div>';

    return panel(
      'Cobertura de leitura do Diário Oficial (DOE-PB)',
      'Base documental da projeção inteira · estes números referem-se às edições processadas',
      '<div class="coverage-visual-grid">' +
        ringSVG +
        '<div class="coverage-stats">' +
          [['Edições disponíveis', c.edicoes], ['Páginas processadas', c.paginas], ['Edições com atos GEDIV', comAtos], ['Histórico desde 01/01/2026', 'Parcial']].map(([name, v]) => '<div class="coverage-stat"><b>' + esc(v) + '</b><span>' + esc(name) + '</span></div>').join('') +
        '</div>' +
      '</div>' +
      '<div class="coverage-notes">' +
        '<div><b>Período documental disponível</b><p>' + esc(dayLabel(c.primeira_publicacao)) + ' a ' + esc(dayLabel(c.ultima_publicacao)) + '. O intervalo não comprova a existência de todas as edições entre essas datas.</p></div>' +
        '<div><b>Conferência de cobertura</b><p>' + esc(c.ausencia_tecnica_edicoes) + ' edições com ausência técnica proposta de atos pertinentes e ' + esc(c.inconclusivas) + ' inconclusiva(s). Isso não é ausência de edição nem homologação humana.</p></div>' +
        '<div><b>Histórico em expansão</b><p>Datas sem informação continuam não verificadas. Totais por dia, edição, quarentena e situação dependem da matriz documental autorizada.</p></div>' +
      '</div>' +
      '<div class="detail-actions"><a class="button" href="#historico">Ver calendário de cobertura</a><a class="button" href="#cobertura">Matriz de edições e fontes</a><a class="button" href="#pendencias">Ver pendências de conferência</a></div>'
    );
  }

  function overview() {
    const title = page === 'progressao' ? 'Progressão Funcional' : page === 'tempo' ? 'Tempo de Serviço' : 'Visão geral executiva';
    const subtitle = page === 'progressao'
      ? 'Análise executiva de Progressão Vertical, Progressão Horizontal e grupos ocupacionais do PCCR.'
      : page === 'tempo'
        ? 'Acompanhamento executivo das 7 modalidades oficiais de Tempo de Serviço / Contribuição (TS-01 a TS-07).'
        : 'Painel gerencial de publicações da GEDIV no Diário Oficial da Paraíba · indicadores, gráficos e consulta documental.';
    let charts;
    if (page === 'tempo') {
      charts = '<div class="chart-grid">' + bars(true) + donut(true) + '</div>' +
        '<div class="chart-grid">' + evolution() + results('ts') + '</div>' +
        evolution(true);
    } else if (page === 'progressao') {
      charts = comparisonProg() +
        '<div class="chart-grid">' + evolution() + donut() + '</div>' +
        '<div class="chart-grid">' + bars(false) + results('grupos') + '</div>' +
        evolution(true);
    } else {
      charts = '<div class="chart-grid">' + evolution() + donut() + '</div>' +
        comparisonProg() +
        '<div class="chart-grid">' + bars(false) + bars(true) + '</div>' +
        '<div class="chart-grid">' + results() + evolution(true) + '</div>';
    }
    return section(title, subtitle, 'Dados reais · faixas protegidas') +
      executiveKPIs() +
      '<div class="overview-grid">' +
        '<div class="charts-column">' + charts + '</div>' +
        '<aside class="query-column" aria-label="Consultas e detalhes">' +
          queryPanel() +
          '<section class="panel detail-panel"><div class="panel-head"><div><h3>Ficha documental da seleção</h3><p>Proveniência, contagem e trilha documental</p></div></div><div id="detalheSelecao">' + detailContent(selected) + '</div></section>' +
        '</aside>' +
      '</div>' +
      recordsPanel() +
      coveragePanel();
  }

  function history() {
    const c = data.cobertura;
    const year = calendarMonth.slice(0, 4) || today().slice(0, 4), periods = Array.from({ length: 12 }, (_, i) => year + '-' + String(i + 1).padStart(2, '0'));
    const calendarMonths = '<div class="history-months">' + periods.map(p => {
      const has = data.celulas.some(cell => cell.periodo === p);
      const inRange = c.primeira_publicacao && p >= c.primeira_publicacao.slice(0, 7) && p <= c.ultima_publicacao.slice(0, 7);
      const mDec = has ? filteredMetric(data.celulas.filter(cell => cell.periodo === p), 'decisoes') : null;
      return '<button type="button" data-calendario="' + p + '" class="' + (has ? 'available' : '') + '">' +
        '<b>' + esc(monthLabel(p)) + '</b>' +
        '<small>' + (has ? ('Agregados: ' + M.metricLabel(mDec) + ' dec.') : inRange ? 'Cobertura diária não informada' : 'Não verificado') + '</small>' +
      '</button>';
    }).join('') + '</div>';
    const [y, m] = calendarMonth.split('-').map(Number), first = new Date(Date.UTC(y, m - 1, 1, 12)).getUTCDay(), days = new Date(Date.UTC(y, m, 0, 12)).getUTCDate();
    const cells = Array.from({ length: first }, () => '<span aria-hidden="true"></span>').join('') + Array.from({ length: days }, (_, i) => { const d = calendarMonth + '-' + String(i + 1).padStart(2, '0'); return '<button type="button" data-dia="' + d + '" class="' + (selectedDay === d ? 'selected' : '') + '" aria-label="Consultar cobertura de ' + dayLabel(d) + ', não verificada por dia"><b>' + (i + 1) + '</b><small>Não verificado</small></button>'; }).join('');
    const histKPIs = '<div class="support-cards">' +
      '<div class="support-card"><span>Início histórico previsto</span><b>01/01/2026</b><small>Meta de retrospectiva documental</small></div>' +
      '<div class="support-card"><span>Janela lida atualmente</span><b>' + esc(dayLabel(c.primeira_publicacao) + ' – ' + dayLabel(c.ultima_publicacao)) + '</b><small>Janela da projeção inteira</small></div>' +
      '<div class="support-card"><span>Edições processadas</span><b>' + esc(c.edicoes) + ' edições</b><small>' + esc((c.edicoes - c.ausencia_tecnica_edicoes - c.inconclusivas) + ' com atos · ' + c.ausencia_tecnica_edicoes + ' sem atos') + '</small></div>' +
      '<div class="support-card"><span>Páginas processadas</span><b>' + esc(c.paginas) + ' págs.</b><small>' + esc(c.inconclusivas) + ' edição inconclusiva</small></div>' +
    '</div>';
    return section('Histórico e cobertura', 'Histórico previsto desde 01/01/2026. Lacunas nunca são apresentadas como ausência de atos.', 'Cobertura documental parcial') +
      histKPIs +
      coveragePanel() +
      panel('Mapa dos meses de ' + esc(year), 'Selecione um mês para inspecionar seu calendário diário ou aplicar aos indicadores.', calendarMonths) +
      panel('Calendário de conferência diária (' + esc(monthLabel(calendarMonth)) + ')', 'A projeção pública contém agregados mensais; selecione uma data para inspecionar sua situação.', '<div class="calendar-controls"><button class="button" type="button" data-mover-mes="-1" aria-label="Mês anterior">‹ Anterior</button><label>Mês <input type="month" id="mesCalendario" min="2026-01" value="' + calendarMonth + '"></label><button class="button" type="button" data-mover-mes="1" aria-label="Próximo mês">Próximo ›</button><button class="button primary compact" type="button" data-mes="' + calendarMonth + '">Aplicar ' + esc(monthLabel(calendarMonth)) + ' aos indicadores</button></div><div class="calendar">' + ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map(x => '<span class="weekday">' + x + '</span>').join('') + cells + '</div><p class="data-note">Não verificado = sem confirmação diária nesta projeção. Não significa “sem publicação”. Não há calendário de edições ausentes homologado disponível.</p>') +
      evolution(true) +
      recordsPanel();
  }

  function daily() {
    const c = data.cobertura;
    const inWindow = c.primeira_publicacao && c.ultima_publicacao && selectedDay >= c.primeira_publicacao && selectedDay <= c.ultima_publicacao;
    const dayKPIs = '<div class="support-cards">' +
      '<div class="support-card"><span>Data selecionada</span><b>' + esc(dayLabel(selectedDay)) + '</b><small>' + (inWindow ? 'Dentro da janela documental lida' : 'Fora da janela lida (01/10 a 14/11/2026)') + '</small></div>' +
      '<div class="support-card"><span>Última publicação da base</span><b>' + esc(dayLabel(c.ultima_publicacao)) + '</b><small>Primeira lida: ' + esc(dayLabel(c.primeira_publicacao)) + '</small></div>' +
      '<div class="support-card"><span>Granularidade pública</span><b>Mensal (faixas)</b><small>Nenhum total mensal é atribuído ao dia</small></div>' +
      '<div class="support-card"><span>Acervo processado</span><b>' + esc(c.edicoes + ' ed. · ' + c.paginas + ' págs.') + '</b><small>Fonte: DOE-PB (A União)</small></div>' +
    '</div>';
    return section('Publicações do dia', 'Consulte uma data específica, a janela documental lida e a disponibilidade das fontes oficiais.', dayLabel(selectedDay)) +
      dayKPIs +
      panel('Consulta por data de publicação', 'A atualização relê a projeção disponível; não inicia coleta ou leitura de PDFs.',
        '<form id="formDia" class="day-picker">' +
          '<label>Data da publicação<input type="date" id="dataDia" min="2026-01-01" value="' + selectedDay + '" required></label>' +
          '<button class="button primary" type="submit">Consultar este dia</button>' +
          '<button class="button" type="button" data-ultima-data>Última data da base (' + esc(dayLabel(c.ultima_publicacao)) + ')</button>' +
          '<button class="button" type="button" data-mes="' + selectedDay.slice(0, 7) + '">Ver agregado do mês (' + esc(monthLabel(selectedDay.slice(0, 7))) + ')</button>' +
        '</form>' +
        empty('Situação do dia: não verificada individualmente na projeção pública', 'A projeção disponível contém agregados mensais e um resumo de cobertura. Ela não informa a edição, o suplemento ou as publicações de cada dia. Isso não confirma ausência de publicação em ' + dayLabel(selectedDay) + '.') +
        '<div class="list-status"><div><b>Edição e suplemento do DOE-PB</b><p>Identificação diária por número de edição não extraída na projeção pública v1.</p></div>' + pill('Não extraído', 'neutral') + '</div>' +
        '<div class="list-status"><div><b>PDF oficial, integridade (SHA-256) e leitura</b><p>URL direta, página exata e hash do PDF exigem metadados documentais verificados na área gerencial.</p></div>' + pill('Não verificado', 'neutral') + '</div>' +
        '<div class="list-status"><div><b>Classificação e conferência diária</b><p>Não há resultados diários autorizados nesta projeção; consulte o mês completo para ver as faixas mensais.</p></div>' + pill('Não verificado', 'neutral') + '</div>' +
        '<div class="detail-actions"><a class="button" href="#cobertura">Ver fontes e cobertura disponíveis</a><button class="button primary compact" type="button" data-mes="' + selectedDay.slice(0, 7) + '">Consultar o mês completo</button></div>'
      ) +
      coveragePanel();
  }

  function changes() {
    const modKPIs = '<div class="support-cards">' +
      '<div class="support-card"><span>Atos refeitos</span><b>—</b><small>Substituição decisória · vínculo pendente</small></div>' +
      '<div class="support-card"><span>Tornados sem efeito</span><b>—</b><small>Anulação validada · não é indeferimento</small></div>' +
      '<div class="support-card"><span>Republicações por incorreção</span><b>—</b><small>Correção material mantendo ato original</small></div>' +
      '<div class="support-card"><span>Retificações pontuais</span><b>—</b><small>Correção parcial de campo publicado</small></div>' +
    '</div>';
    return section('Alterações / Refeitos', 'Republicações por incorreção, atos refeitos e atos tornados sem efeito são acompanhados separadamente das decisões originais.', 'Vínculos não disponibilizados') +
      modKPIs +
      panel('Matriz de distinção e acompanhamento de eventos modificadores', 'Cada evento precisa de publicação de origem, versão e data próprias antes de ser contabilizado.',
        empty('Eventos ainda não disponibilizados na projeção pública', 'O arquivo público atual não contém vínculos entre originais, republicações por incorreção, atos refeitos e anulações. Ausência de lista não significa zero eventos.') +
        tableHTML(
          ['Natureza do evento', 'Definição operacional obrigatória', 'Impacto na decisão original', 'Ato de origem / Data', 'Conferência'],
          [
            ['Republicação por incorreção', 'Reprodução do texto para corrigir erro material ou formal da publicação anterior', 'Preserva a validade do ato original', 'Não extraído', 'Não verificado'],
            ['Ato refeito', 'Novo ato administrativo vinculado que substitui a apreciação anterior', 'Substitui o ato original (usa data do evento)', 'Não extraído', 'Não verificado'],
            ['Retificação', 'Correção pontual de dado específico sem republicar o ato completo', 'Atualiza dado específico do registro', 'Não extraído', 'Não verificado'],
            ['Tornado sem efeito', 'Desconstituição / anulação documentalmente vinculada e validada', 'Extingue efeitos do ato (não é indeferimento)', 'Não extraído', 'Não verificado']
          ]
        ) +
        '<p class="data-note">As linhas acima definem as regras de negócio oficiais do Observatório GEDIV. Uma anulação nunca é contada como indeferimento, e modificadores não inflam os gráficos de decisões originais.</p>'
      );
  }

  function others() {
    const subjects = [
      ['Publicações relacionadas à GEDIV / DEREH', 'Despachos e expedientes compartilhados; menção isolada à DEREH não exclui vínculo com a GEDIV.'],
      ['Portarias e atos normativos', 'Normativos internos, designações e regulamentações correlatas à gestão de direitos e vantagens.'],
      ['Alterações legais', 'Leis, decretos e normas estaduais com impacto sobre PCCR e tempo de serviço.'],
      ['Abono de permanência', 'Matéria acompanhada em triagem; inclusão em indicadores depende de definição administrativa.'],
      ['Assuntos fora dos dois eixos (Vacância / Licença-saúde)', 'Excluídos expressamente dos indicadores públicos de Progressão Funcional e Tempo de Serviço.']
    ];
    return section('Outras publicações', 'Área de apoio para matérias relacionadas à GEDIV e à DEREH; não constitui um terceiro eixo de indicadores.', 'Triagem e conferência') +
      panel('Catálogo de triagem das matérias correlatas', 'Menção à DEREH, isoladamente, não exclui vínculo com a GEDIV.',
        empty('Lista de matérias não disponibilizada na projeção pública', 'A projeção pública atual não inclui a listagem individualizada de outras publicações. Nenhum registro fictício foi criado para preencher esta tela.') +
        subjects.map(([title, desc]) => '<div class="list-status"><div><b>' + esc(title) + '</b><p>' + esc(desc) + '</p></div>' + pill('Não verificado', 'neutral') + '</div>').join('') +
        '<div class="detail-actions"><a class="button" href="#pendencias">Ver pendências e dúvidas de classificação</a></div>'
      );
  }

  function pending() {
    const pendingMetric = M.qualityMetric(data, state, visible, 'publicacoes_pendentes');
    const provMetric = M.qualityMetric(data, state, visible, 'provisorios');
    const confMetric = M.qualityMetric(data, state, visible, 'conferidos');
    return section('Pendências de conferência', 'Extração automática, interpretação documental e conferência administrativa são etapas distintas.', 'Revisão por exceção') +
      '<div class="support-cards">' +
        '<div class="support-card"><span>Publicações pendentes no recorte</span><b>' + esc(M.metricLabel(pendingMetric)) + '</b><small>Atos aguardando homologação humana</small></div>' +
        '<div class="support-card"><span>Decisões provisórias no recorte</span><b>' + esc(M.metricLabel(provMetric)) + '</b><small>Extraídas com sucesso · em revisão</small></div>' +
        '<div class="support-card"><span>Decisões conferidas</span><b>' + esc(M.metricLabel(confMetric)) + '</b><small>Homologação administrativa concluída</small></div>' +
        '<div class="support-card"><span>Edições inconclusivas na base</span><b>' + esc(data.cobertura.inconclusivas) + '</b><small>Resumo de cobertura documental</small></div>' +
      '</div>' +
      panel('O que precisa de conferência administrativa', 'Situação conhecida nesta projeção e limites de interpretação documental.',
        '<div class="list-status"><div><b>Interpretação documental inconclusiva</b><p>A cobertura registra leituras inconclusivas que exigem conferência. Detalhes de documentos individuais não integram esta projeção pública.</p></div>' + pill('Não verificado', 'neutral') + '</div>' +
        '<div class="list-status"><div><b>Grupos e códigos PCCR sem homologação</b><p>TEC. ADM / AST, STF / SFT e denominação INT dependem de confirmação administrativa. Não são equiparados por aproximação.</p></div>' + pill('Confirmação necessária', 'provisorio') + '</div>' +
        '<div class="list-status"><div><b>Tempo de Serviço: células mensais preservadas (&lt; 5)</b><p>Os sete serviços (TS-01 a TS-07) permanecem acessíveis, com total do eixo em ' + esc(M.metricLabel(axisMetric('TEMPO_SERVICO'))) + ' decisões. Subcategorias com menos de 5 matrículas no mês ficam preservadas.</p></div>' + pill('Preservado (LGPD)', 'neutral') + '</div>' +
        '<div class="list-status"><div><b>Revisão de registros individuais e evidências PDF</b><p>Consultas por nome, matrícula e processo SAD-PSE exigem acesso gerencial autenticado e trilha de auditoria.</p></div><a class="button primary compact" href="#gerencial">Área gerencial</a></div>'
      ) +
      panel('Indicadores aguardando publicação agregada na base canônica', 'Estes indicadores não recebem zero falso e serão ativados automaticamente quando homologados no gerador público.',
        tableHTML(
          ['Indicador solicitado', 'Situação atual', 'Motivo técnico / governança', 'Ação necessária'],
          [
            ['1. Total de processos distintos', 'Pendente na projeção v1', 'Identificadores SAD-PSE ficam restritos ao banco gerencial; falta contagem agregada distinta no gerador público', 'Publicar contagem agregada distinta em faixa após conferência de vínculos'],
            ['4. Total de deferimentos', 'Em conferência (' + M.metricLabel(provMetric) + ' extraídas)', 'Projeção v1 publica volume total de decisões provisórias sem desagregar mérito por célula', 'Homologar classificação de mérito (Deferido) no pipeline público'],
            ['5. Total de indeferimentos', 'Em conferência (' + M.metricLabel(provMetric) + ' extraídas)', 'Depende da homologação humana da classificação de mérito para não confundir com atos sem efeito', 'Homologar classificação de mérito (Indeferido) no pipeline público'],
            ['6. Total de atos refeitos', 'Vínculos em revisão', 'Exige vínculo formal entre o novo ato administrativo e a publicação original substituída', 'Concluir vinculação documental na fila de revisão gerencial'],
            ['7. Total de atos tornados sem efeito', 'Vínculos em revisão', 'Anulação/desconstituição validada; nunca deve ser somada como indeferimento', 'Concluir validação de eventos modificadores na base canônica'],
            ['8. Total de republicações por incorreção', 'Vínculos em revisão', 'Reprodução para correção material mantendo o ato original; exige deduplicação documental', 'Vincular republicações aos atos originais antes da exportação pública'],
            ['9. Outros resultados', 'Em conferência', 'Desfechos residuais (parcialmente deferido, sobrestado, arquivado) dependem da revisão de mérito', 'Homologar desfechos residuais na revisão administrativa']
          ]
        )
      ) +
      recordsPanel();
  }

  function sources() {
    const c = data.cobertura;
    const comAtos = c.edicoes - c.ausencia_tecnica_edicoes - c.inconclusivas;
    const covCards = '<div class="support-cards">' +
      '<div class="support-card"><span>Edições processadas</span><b>' + esc(c.edicoes) + ' edições</b><small>Janela: ' + esc(dayLabel(c.primeira_publicacao) + ' a ' + dayLabel(c.ultima_publicacao)) + '</small></div>' +
      '<div class="support-card"><span>Páginas lidas do DOE-PB</span><b>' + esc(c.paginas) + ' páginas</b><small>Extração real sem dados simulados</small></div>' +
      '<div class="support-card"><span>Edições com atos GEDIV</span><b>' + esc(comAtos) + ' edições</b><small>' + esc(c.ausencia_tecnica_edicoes) + ' ausências técnicas · ' + esc(c.inconclusivas) + ' inconclusiva</small></div>' +
      '<div class="support-card"><span>Proteção LGPD ativa</span><b>Limiar ≥ ' + esc(data.privacidade.limiar) + '</b><small>Faixas de ' + esc(data.privacidade.faixa) + ' · sem dados nominais</small></div>' +
    '</div>';
    return section('Edições e fontes', 'Confira de onde vêm os números, a cobertura documental e as regras de proteção.', 'Proveniência dos dados') +
      covCards +
      coveragePanel() +
      panel('Matriz dos 10 indicadores executivos solicitados', 'Diagnóstico de existência na base, segurança LGPD e conexão com o frontend público (`dados.json`).',
        tableHTML(
          ['#', 'Indicador executivo', 'Disponibilidade atual', 'Fonte / Camada', 'Conexão no painel público'],
          [
            ['1', 'Total de processos distintos', 'Pendente na projeção v1', 'Base gerencial SQLite (`processo`)', 'Card de acompanhamento · aguarda contagem agregada sem expor SAD-PSE'],
            ['2', 'Total de atos (resenhas indisponíveis)', 'Ativo: ' + M.metricLabel(data.resumo.atos), '`dados.json` → `resumo.atos` e `celulas[].atos`', 'Card executivo principal e fichas de agregados mensais'],
            ['3', 'Total de decisões individuais', 'Ativo: ' + M.metricLabel(M.sumMetrics([data.resumo.conferidos, data.resumo.provisorios])), '`dados.json` → `resumo` e `celulas[].decisoes`', 'Card executivo principal, gráficos de evolução, rosca e barras'],
            ['4', 'Total de deferimentos', 'Em conferência administrativa', 'Base canônica (mérito em revisão)', 'Matriz de 10 indicadores e painel de resultados por área'],
            ['5', 'Total de indeferimentos', 'Em conferência administrativa', 'Base canônica (mérito em revisão)', 'Matriz de 10 indicadores e painel de resultados por área'],
            ['6', 'Total de atos refeitos', 'Vínculos em revisão', 'Eventos modificadores (base gerencial)', 'Matriz de 10 indicadores e aba Alterações / Refeitos'],
            ['7', 'Total de atos tornados sem efeito', 'Vínculos em revisão', 'Eventos modificadores (base gerencial)', 'Matriz de 10 indicadores (separado de indeferimentos)'],
            ['8', 'Total de republicações por incorreção', 'Vínculos em revisão', 'Eventos modificadores (base gerencial)', 'Matriz de 10 indicadores (separado de atos refeitos)'],
            ['9', 'Outros resultados', 'Em conferência administrativa', 'Base canônica (mérito em revisão)', 'Matriz de 10 indicadores e tabela alternativa de resultados'],
            ['10', 'Edições e páginas processadas', 'Ativo: ' + c.edicoes + ' edições · ' + c.paginas + ' págs.', '`dados.json` → `cobertura.edicoes` e `cobertura.paginas`', 'Card executivo de cobertura, anel SVG e aba Edições e fontes']
          ]
        )
      ) +
      panel('Situações da cobertura por edição', 'Classificação técnica utilizada no inventário documental do Diário Oficial.',
        tableHTML(
          ['Situação documental', 'Quantidade na base', 'Significado operacional'],
          [
            ['Edições com atos GEDIV extraídos', String(comAtos), 'Edições lidas onde foram identificadas publicações pertinentes à GEDIV'],
            ['Ausência técnica proposta', String(c.ausencia_tecnica_edicoes), 'Edições lidas sem detecção automática de atos GEDIV (sujeito à revisão)'],
            ['Leitura inconclusiva', String(c.inconclusivas), 'Edição com pendência técnica de leitura/interpretação'],
            ['Verificada por revisão humana', 'Não verificado por edição', 'Fonte e leitura documental homologadas administrativamente'],
            ['Quarentena', 'Não verificado por edição', 'Fonte separada para análise de integridade de arquivo'],
            ['Ausência confirmada de edição', 'Não verificado por edição', 'Dia sem publicação do DOE comprovado documentalmente; nunca presumido por lacuna']
          ]
        ) +
        '<p class="data-note">As ' + esc(c.edicoes) + ' edições e ' + esc(c.paginas) + ' páginas representam o total processado na projeção inteira (' + esc(dayLabel(c.primeira_publicacao)) + ' a ' + esc(dayLabel(c.ultima_publicacao)) + ').</p>'
      ) +
      panel('Origem, contrato público e atualização', 'Mesma fonte canônica para indicadores, gráficos, tabelas e exportações.',
        '<dl class="detail-list">' +
          definition('Origem oficial', 'Diário Oficial do Estado da Paraíba (A União) · dados reais') +
          definition('Arquivo da consulta', 'dados.json · projeção pública protegida (contrato versão ' + data.schema_version + ')') +
          definition('Gerada em', timestamp(data.atualizado_em) + ' (horário de Brasília)') +
          definition('Versão das regras', data.versao_regras) +
          definition('Regra de privacidade (LGPD)', 'Limiar mínimo de ' + data.privacidade.limiar + ' matrículas e divulgação em faixas de ' + data.privacidade.faixa) +
          definition('Edições / PDFs individuais', 'Restritos à área gerencial autenticada; nenhuma URL individual é presumida') +
          definition('Botão Atualizar dados', 'Relê a projeção pública disponível sem iniciar coleta, OCR ou alteração de banco') +
        '</dl>'
      );
  }

  function management() {
    const groups = [
      ['1. Identificação funcional e publicação', 'Nome completo, matrícula, número do processo administrativo (SAD-PSE), órgão, cargo, eixo, modalidade, resultado original, data da publicação, número de resenha / ato e página do PDF.'],
      ['2. Progressão Funcional (PCCR)', 'Grupo ocupacional PCCR e descritor original; classes e níveis anteriores e posteriores, inclusive saltos oficiais publicados sem normalização artificial.'],
      ['3. Tempo de Serviço / Contribuição', 'Modalidade oficial TS-01 a TS-07, origem do tempo, período inicial e final, quantidade de dias e demais atributos publicados.'],
      ['4. Fonte documental, evidência e trilha de auditoria', 'PDF oficial na página exata, hash SHA-256, trecho de evidência original, estado de validação (Pendente / Conferido / Conflito), histórico de versões e vínculos com eventos modificadores.']
    ];
    return section('Área gerencial', 'Consultas nominais por processo, resenha, servidor e revisão documental ficam isoladas da consulta pública.', 'NÃO HABILITADA (SEGURANÇA)') +
      panel('Acesso individual protegido por autenticação no servidor', 'Esta distribuição pública estática não contém senhas, tokens nem registros individuais ocultos.',
        empty('NÃO HABILITADA (SEGURANÇA)', 'A pesquisa por nome, matrícula ou processo (SAD-PSE) e as fichas individuais exigem autenticação real no servidor gerencial, autorização por perfil e trilha de auditoria. Nenhum dado pessoal foi incluído no pacote público.', true) +
        '<div class="hierarchy-trail" aria-label="Fluxo completo na área gerencial">' +
          '<span class="trail-step done">1. Edição DOE</span><span class="trail-sep">›</span>' +
          '<span class="trail-step done">2. Página PDF</span><span class="trail-sep">›</span>' +
          '<span class="trail-step locked">3. Resenha / Ato ◇</span><span class="trail-sep">›</span>' +
          '<span class="trail-step locked">4. Processo SAD-PSE ◇</span><span class="trail-sep">›</span>' +
          '<span class="trail-step locked">5. Servidor / Matrícula ◇</span><span class="trail-sep">›</span>' +
          '<span class="trail-step locked">6. Decisão / Mérito ◇</span><span class="trail-sep">›</span>' +
          '<span class="trail-step locked">7. Evento Modificador ◇</span>' +
        '</div>' +
        '<p class="data-note">O pacote público contém apenas agregados protegidos. A área gerencial requer validação própria de autenticação, autorização e auditoria antes de ser habilitada.</p>'
      ) +
      panel('Estrutura das fichas documentais na área gerencial autenticada', 'Navegação prevista: Resenha → tabela completa de ocorrências → processo → ficha documental e PDF oficial.',
        '<div class="field-groups">' + groups.map(([title, text]) => '<details open><summary>' + esc(title) + '</summary><p>' + esc(text) + '</p><p class="field-note">Campos ausentes na publicação original permanecem rotulados como “Não extraído”.</p></details>').join('') + '</div>'
      );
  }

  function syncForm() {
    M.CAMPOS.forEach(k => { if ($(k)) $(k).value = state[k]; });
    document.querySelectorAll('[name=servico]').forEach(input => { input.checked = state.subcategorias.includes(input.value); });
    $('modalidade').disabled = $('grupo').disabled = state.eixo === 'TEMPO_SERVICO';
    document.querySelectorAll('[name=servico]').forEach(input => { input.disabled = state.eixo === 'PROGRESSAO'; });
    $('filtrosPendentes').textContent = '';
    document.querySelectorAll('[data-periodo]').forEach(btn => {
      const p = btn.dataset.periodo;
      const active = (p === 'tudo' && !state.inicio && !state.fim) ||
        (/^20\d\d-\d\d$/.test(p) && state.inicio === p + '-01' && state.fim === M.monthEnd(p)) ||
        (p === 'hoje' && state.inicio === today() && state.fim === today()) ||
        (p === 'mes' && state.inicio === today().slice(0,7) + '-01' && state.fim === M.monthEnd(today().slice(0,7))) ||
        (p === 'ano' && state.inicio === today().slice(0,4) + '-01-01' && state.fim === today().slice(0,4) + '-12-31');
      btn.setAttribute('aria-pressed', String(active));
    });
  }

  function fitPlots() {
    document.querySelectorAll('.chart-box').forEach(box => {
      if (box.clientWidth > 0) box.closest('.panel').outerHTML = evolution(box.dataset.plotKind === 'line', box.clientWidth);
    });
  }

  function render(sync = false) {
    cards();
    if (!data) return;
    visible = M.filterCells(data.celulas, state);
    if (selected && !visible.some(c => cellKey(c) === cellKey(selected))) selected = null;
    if (sync) syncForm();
    $('filtrosAtivos').textContent = describeFilters();
    renderFilterChips();
    const issue = (M.selectionIssue(state) || M.coverageIssue(data, state));
    $('restricaoRecorte').hidden = !issue;
    $('restricaoRecorte').innerHTML = issue ? '<div><b>Este recorte não pode ser calculado</b><p>' + esc(issue) + '</p></div>' : '';
    const contents = { geral: overview, progressao: overview, tempo: overview, historico: history, dia: daily, alteracoes: changes, outras: others, cobertura: sources, pendencias: pending, gerencial: management };
    $('pagina').innerHTML = contents[page]();
    fitPlots();
    $('pagina').setAttribute('aria-busy', 'false');
    document.querySelectorAll('#abas a, #menuApoio a').forEach(a => {
      if (a.hash === '#' + page) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    $('contextoCurto').textContent = pages[page];
    $('situacaoResumo').textContent = state.situacao === 'conferido' ? 'Consulta de dados conferidos' : 'Dados reais · conferência parcial';
    document.title = pages[page] + ' | Observatório do Diário Oficial · GEDIV';
    cards();
    buildPrint();
  }

  function setFilters(patch) {
    state = { ...state, ...patch };
    if (page === 'dia') {
      if (state.inicio && state.inicio === state.fim) selectedDay = state.inicio;
      else page = 'geral';
    }
    if (page === 'progressao' && state.eixo === 'TEMPO_SERVICO') page = 'tempo';
    if (page === 'tempo' && state.eixo === 'PROGRESSAO') page = 'progressao';
    queryPage = tablePage = 0;
    writeLocation();
    render(true);
    $('anuncio').textContent = 'Consulta atualizada. ' + ((M.selectionIssue(state) || M.coverageIssue(data, state)) || visible.length + ' agregados publicáveis na seleção.');
  }

  function monthFilter(p) { setFilters({ inicio: p + '-01', fim: M.monthEnd(p) }); }

  function writeLocation(replace = false) {
    const params = new URLSearchParams();
    M.CAMPOS.forEach(k => { if (state[k]) params.set(k, state[k]); });
    state.subcategorias.forEach(s => params.append('servico', s));
    const hash = '#' + page + (params.size ? '?' + params.toString() : '');
    if (location.hash !== hash) window.history[replace ? 'replaceState' : 'pushState'](null, '', hash);
    document.querySelectorAll('#abas a, #menuApoio a, .brand, footer a').forEach(a => {
      const target = a.hash.slice(1).split('?')[0];
      if (Object.hasOwn(pages, target)) a.href = '#' + target + (params.size ? '?' + params.toString() : '');
    });
  }

  function readLocation() {
    const params = new URLSearchParams(location.hash.split('?')[1] || '');
    const next = M.novoEstado();
    for (const k of M.CAMPOS) {
      const value = params.get(k) || '';
      if (k === 'inicio' || k === 'fim') { if (M.validDate(value)) next[k] = value; }
      else if (k === 'grupo') { if (['MAG','SSA','GAJ','FAP','AST','ANS','ESP','DPS','SFT','OSPB','GPC','SEI','SAT','ACI','PPGG','INT','NAO_INFORMADO'].includes(value)) next[k] = value; }
      else if (Array.from($(k)?.options || []).some(o => o.value === value)) next[k] = value;
    }
    next.subcategorias = [...new Set(params.getAll('servico').filter(s => /^TS-0[1-7]$/.test(s)))];
    return next;
  }

  function populate() {
    $('grupo').innerHTML = '<option value="">Todos os grupos ocupacionais</option>' + data.catalogo.grupos.map(g => '<option value="' + g.codigo + '">' + esc(g.codigo + ' · ' + g.nome) + '</option>').join('') + '<option value="NAO_INFORMADO">Grupo não informado</option>';
    $('listaServicos').innerHTML = data.catalogo.subcategorias.map(s => '<label><input name="servico" type="checkbox" value="' + s.codigo + '"><span><small>' + s.codigo + '</small>' + esc(s.nome) + '</span></label>').join('');
    calendarMonth ||= data.cobertura.ultima_publicacao?.slice(0, 7) || today().slice(0, 7);
    selectedDay ||= today();
    $('atualizacao').textContent = timestamp(data.atualizado_em);
    $('versaoResumo').textContent = '· Mensal em faixas';
    if ($('coberturaTopoResumo') && data.cobertura) {
      $('coberturaTopoResumo').textContent = data.cobertura.edicoes + ' edições · ' + data.cobertura.paginas + ' págs.';
    }
  }

  function route(initial = false) {
    const next = location.hash.slice(1).split('?')[0];
    page = Object.hasOwn(pages, next) ? next : 'geral';
    if (location.hash.includes('?')) state = readLocation();
    if (page === 'progressao') state = { ...state, eixo: 'PROGRESSAO', subcategorias: [] };
    if (page === 'tempo') state = { ...state, eixo: 'TEMPO_SERVICO', grupo: '', modalidade: '' };
    if (page === 'dia') { selectedDay = state.inicio && state.inicio === state.fim ? state.inicio : selectedDay || today(); state = { ...state, inicio: selectedDay, fim: selectedDay }; }
    writeLocation(true);
    if ($('detalhe').open) $('detalhe').close();
    closeMenu(false);
    if (data) { render(true); if (!initial) $('tituloPagina').focus({ preventScroll: false }); }
  }

  function showDialog(title, html) {
    focusBeforeDialog = document.activeElement;
    $('tituloDetalhe').textContent = title;
    $('corpoDetalhe').innerHTML = html;
    if (!$('detalhe').open) $('detalhe').showModal();
    $('fecharDetalhe').focus();
  }

  function showInfo() {
    const definitions = [
      ['Conferido', 'Existe registro de conferência administrativa na base. Não se presume por haver um gráfico.'],
      ['Provisório', 'Extração real aguardando conferência. Não é resultado administrativo oficial.'],
      ['Não verificado', 'Informação ausente ou insuficiente. Nunca é substituída por zero.'],
      ['Preservado / não divulgado', 'O recorte pode estar suprimido para proteger pessoas (células < 5). Não permite concluir ausência de atos.'],
      ['Republicação × Refeito × Sem efeito', 'Republicação por incorreção corrige erro material/formal mantendo o ato; Ato refeito substitui a decisão por novo ato; Tornado sem efeito anula o ato (não é indeferimento).'],
      ['Unidades de contagem', 'Edição, resenha, ato, processo, decisão, ocorrência e pessoa são unidades documentais distintas e não intercambiáveis.'],
      ['Faixas e percentuais', 'Contagens positivas são intervalos de 5. As formas dos gráficos usam limites inferiores; percentuais são intervalos entre agregados exibidos.'],
      ['Privacidade e LGPD', 'Nomes, matrículas e números de processos (SAD-PSE) ficam restritos à área gerencial autenticada no servidor.']
    ];
    showDialog('Metodologia, contagens e proteção de dados', '<p>Esta consulta usa exclusivamente a projeção pública protegida do Diário Oficial da Paraíba. A cobertura é parcial e as contagens são divulgadas em faixas.</p><div class="definition-list">' + definitions.map(([title, text]) => '<div><b>' + esc(title) + '</b><p>' + esc(text) + '</p></div>').join('') + '</div><p class="data-note">' + esc(data?.privacidade.observacao || '') + '</p>');
  }

  function exportRows(cells = visible, local = false) {
    const rows = [['Observatório do Diário Oficial | Painel GEDIV · consulta pública'], ['Projeção gerada (Brasília)', timestamp(data.atualizado_em)], ['Versão de regras', data.versao_regras], ['Filtros aplicados', describeFilters()], ['Escopo', local ? 'Lista pesquisada de agregados públicos; sem registros individuais' : 'Todos os agregados publicáveis dos filtros aplicados, incluindo todas as páginas'], ['Limites', 'Faixas protegidas; ausência de agregado não confirma ausência de atos; atos nas células não são somáveis como distintos']];
    if ((M.selectionIssue(state) || M.coverageIssue(data, state))) rows.push(['Recorte indisponível', (M.selectionIssue(state) || M.coverageIssue(data, state))]);
    if (!cells.length) rows.push(['Resultado', 'Sem agregado publicável; isso não equivale a zero publicações']);
    return [...rows, [], ...M.cellsToRows(cells, data.catalogo)];
  }

  function download(blob, filename) { const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  function exportCsv(cells = visible, local = false) { if (data) download(new Blob(['\ufeff' + exportRows(cells, local).map(r => r.map(M.csvValue).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' }), local ? 'GEDIV_lista_publica.csv' : 'GEDIV_agregados_publicos.csv'); }

  function buildPrint() {
    if (!data) { $('impressao').innerHTML = ''; return; }
    const rows = M.cellsToRows(M.sortCells(visible, tableSort, sortDirection), data.catalogo), metric = M.decisionMetric(data, state, visible);
    $('impressao').innerHTML = '<h1>Observatório do Diário Oficial | Painel GEDIV</h1><h2>Consulta pública · ' + esc(pages[page]) + '</h2><p>Projeção gerada em ' + esc(timestamp(data.atualizado_em)) + ' (Brasília) · ' + esc(data.versao_regras) + '</p><p><b>Filtros:</b> ' + esc(describeFilters()) + '</p><div class="print-metrics">' + kpis.map(([key, title]) => '<div>' + esc(title) + '<b>' + (key === 'decisoes' ? esc(M.metricLabel(metric)) : '— · Não verificado') + '</b></div>').join('') + '</div><div class="print-note">' + esc((M.selectionIssue(state) || M.coverageIssue(data, state)) || 'Agregados mensais publicáveis em faixas. A consulta é parcial; dados suprimidos não são zero. Atos nas células podem repetir e não devem ser somados como atos distintos.') + '</div>' + tableHTML(rows[0], rows.slice(1)) + '<p><b>Cobertura da projeção inteira, sem filtro:</b> ' + data.cobertura.edicoes + ' edições · ' + data.cobertura.paginas + ' páginas · ' + esc(dayLabel(data.cobertura.primeira_publicacao)) + ' a ' + esc(dayLabel(data.cobertura.ultima_publicacao)) + '. Histórico parcial desde 01/01/2026.</p><p>Fonte: Diário Oficial do Estado da Paraíba. Não substitui a publicação oficial. Nenhum dado individual integra este relatório.</p>';
  }

  async function savePng(button) {
    const svg = button.closest('.panel')?.querySelector('svg');
    if (!svg) { notify('Não há gráfico publicável para exportar neste recorte.'); return; }
    const copy = svg.cloneNode(true);
    copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    copy.querySelectorAll('text').forEach(x => { x.setAttribute('fill', '#153452'); x.setAttribute('font-family', 'Arial, sans-serif'); x.setAttribute('font-size', '11'); });
    copy.querySelectorAll('.grid-line').forEach(x => x.setAttribute('stroke', '#d7e4f1'));
    copy.querySelectorAll('.line-mark').forEach(x => x.setAttribute('fill', '#fff'));
    copy.querySelectorAll('.range-tail').forEach(x => x.setAttribute('opacity', '.3'));
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)], { type: 'image/svg+xml' }));
    try {
      const img = new Image(); img.src = url; await img.decode();
      const canvas = document.createElement('canvas'); canvas.width = 1400;
      const ctx = canvas.getContext('2d'); ctx.font = '18px Arial';
      const filterLines = []; let currentLine = '';
      for (const word of ('Filtros: ' + describeFilters()).split(' ')) {
        if (currentLine && ctx.measureText(currentLine + ' ' + word).width > 1336) { filterLines.push(currentLine); currentLine = ''; }
        currentLine += (currentLine ? ' ' : '') + word;
      }
      if (currentLine) filterLines.push(currentLine);
      const headerHeight = 90 + filterLines.length * 24;
      const box = svg.viewBox.baseVal, plotHeight = Math.round(1336 * box.height / box.width);
      canvas.height = headerHeight + plotHeight + 130;
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#153452'; ctx.font = 'bold 24px Arial';
      ctx.fillText('GEDIV · ' + button.closest('.panel').querySelector('h3').textContent, 32, 40);
      ctx.font = '18px Arial'; filterLines.forEach((line, i) => ctx.fillText(line, 32, 75 + i * 24));
      ctx.drawImage(img, 32, headerHeight, 1336, plotHeight);
      const footerY = headerHeight + plotHeight + 25;
      series.forEach((item, i) => { const x = 32 + i * 435; ctx.fillStyle = item.color; ctx.fillRect(x, footerY - 14, 16, 16); ctx.fillStyle = '#153452'; ctx.fillText(item.name, x + 25, footerY); });
      ctx.font = '16px Arial'; ctx.fillText('Agregados mensais parciais em faixas · partes sólidas: limites inferiores', 32, footerY + 35);
      ctx.fillText('Projeção: ' + timestamp(data.atualizado_em) + ' (Brasília)', 32, footerY + 64);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
      if (blob) download(blob, 'GEDIV_grafico_publico.png');
    } catch (_) { notify('Não foi possível gerar o PNG. Use a tabela ou PDF / imprimir.'); } finally { URL.revokeObjectURL(url); }
  }

  function closeMenu(returnFocus = true) {
    const wasOpen = $('casca').classList.contains('menu-open');
    $('casca').classList.remove('menu-open'); $('fundoMenu').hidden = true;
    $('conteudo').inert = false; document.querySelector('.topbar').inert = false;
    $('menuLateral').removeAttribute('role'); $('menuLateral').removeAttribute('aria-modal');
    $('abrirMenu').setAttribute('aria-expanded', String(!window.matchMedia('(max-width:780px)').matches && !$('casca').classList.contains('menu-collapsed')));
    if (returnFocus && wasOpen) $('abrirMenu').focus();
  }

  function openMenuSidebar() {
    if (window.matchMedia('(max-width:780px)').matches) {
      $('casca').classList.remove('menu-collapsed'); $('casca').classList.add('menu-open'); $('fundoMenu').hidden = false;
      $('conteudo').inert = true; document.querySelector('.topbar').inert = true;
      $('menuLateral').setAttribute('role', 'dialog'); $('menuLateral').setAttribute('aria-modal', 'true'); $('menuLateral').setAttribute('aria-label', 'Menu e filtros');
      $('recolherMenu').focus();
    } else {
      $('casca').classList.remove('menu-collapsed');
      $('recolherMenu').focus();
      if (data) setTimeout(fitPlots, 60);
    }
    $('abrirMenu').setAttribute('aria-expanded', 'true');
  }

  $('abrirMenu').onclick = openMenuSidebar;
  if ($('expandirMenuTrilho')) $('expandirMenuTrilho').onclick = openMenuSidebar;
  $('recolherMenu').onclick = () => {
    if (window.matchMedia('(max-width:780px)').matches) closeMenu();
    else {
      $('casca').classList.add('menu-collapsed');
      $('abrirMenu').setAttribute('aria-expanded', 'false');
      if ($('expandirMenuTrilho')) $('expandirMenuTrilho').focus(); else $('abrirMenu').focus();
      if (data) setTimeout(fitPlots, 60);
    }
  };
  $('fundoMenu').onclick = () => closeMenu();

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeMenu();
    const el = e.target.closest('svg [role=button]');
    if (el && ['Enter', ' '].includes(e.key)) { e.preventDefault(); el.dispatchEvent(new MouseEvent('click', { bubbles: true })); }
  });

  $('fecharDetalhe').onclick = () => $('detalhe').close();
  $('detalhe').addEventListener('close', () => { if (focusBeforeDialog?.isConnected) focusBeforeDialog.focus({ preventScroll: true }); else $('tituloPagina')?.focus({ preventScroll: true }); });
  $('detalhe').addEventListener('click', e => { if (e.target === $('detalhe') && (e.clientX < $('detalhe').getBoundingClientRect().left || e.clientX > $('detalhe').getBoundingClientRect().right || e.clientY < $('detalhe').getBoundingClientRect().top || e.clientY > $('detalhe').getBoundingClientRect().bottom)) $('detalhe').close(); });

  function setTheme(dark) {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    $('tema').setAttribute('aria-label', dark ? 'Ativar modo claro' : 'Ativar modo escuro'); $('tema').setAttribute('aria-pressed', String(dark));
    try { localStorage.setItem('gediv_tema_publico', dark ? 'dark' : 'light'); } catch (_) { /* armazenamento opcional */ }
  }
  let savedTheme; try { savedTheme = localStorage.getItem('gediv_tema_publico'); } catch (_) { /* armazenamento opcional */ }
  setTheme(savedTheme ? savedTheme === 'dark' : window.matchMedia('(prefers-color-scheme:dark)').matches);
  $('tema').onclick = () => setTheme(document.documentElement.dataset.theme !== 'dark');
  $('sobreDados').onclick = showInfo;
  $('abrirCalendario').onclick = () => {
    if (!data || !root.GedivCalendario) return;
    root.GedivCalendario.abrir({ inicio: state.inicio, fim: state.fim,
      primeiraData: data.cobertura.primeira_publicacao, ultimaData: data.cobertura.ultima_publicacao,
      onApply: patch => { if (patch.inicio === patch.fim && patch.inicio) selectedDay = patch.inicio; setFilters(patch); closeMenu(); }
    });
  };

  $('filtros').addEventListener('change', e => {
    const id = e.target.id;
    if (id === 'eixo') {
      if ($('eixo').value === 'TEMPO_SERVICO') $('grupo').value = $('modalidade').value = '';
      if ($('eixo').value === 'PROGRESSAO') document.querySelectorAll('[name=servico]').forEach(x => { x.checked = false; });
    }
    if ((id === 'grupo' || id === 'modalidade') && e.target.value) { $('eixo').value = 'PROGRESSAO'; document.querySelectorAll('[name=servico]').forEach(x => { x.checked = false; }); }
    if (e.target.name === 'servico' && e.target.checked) { $('eixo').value = 'TEMPO_SERVICO'; $('grupo').value = $('modalidade').value = ''; }
    $('modalidade').disabled = $('grupo').disabled = $('eixo').value === 'TEMPO_SERVICO';
    document.querySelectorAll('[name=servico]').forEach(x => { x.disabled = $('eixo').value === 'PROGRESSAO'; });
    $('fim').setCustomValidity(''); $('filtrosPendentes').textContent = 'Alterações prontas. Selecione Aplicar filtros.';
  });

  $('filtros').onsubmit = e => {
    e.preventDefault(); if (!data) return;
    const next = Object.fromEntries(M.CAMPOS.map(k => [k, $(k).value])); next.subcategorias = [...document.querySelectorAll('[name=servico]:checked')].map(x => x.value);
    if (next.inicio && next.fim && next.inicio > next.fim) { $('fim').setCustomValidity('A data final deve ser igual ou posterior à inicial.'); $('fim').reportValidity(); return; }
    setFilters(next); closeMenu();
  };

  $('limpar').onclick = () => { state = M.novoEstado(); page = 'geral'; query = ''; selected = null; queryPage = tablePage = 0; $('fim').setCustomValidity(''); writeLocation(); if (data) render(true); notify('Filtros limpos. Consulta de toda a base disponível.'); };

  document.addEventListener('click', e => {
    const el = e.target.closest('[data-periodo],[data-mes],[data-grupo],[data-sub],[data-serie],[data-medida],[data-consulta],[data-detalhe],[data-paginar],[data-ordenar],[data-ver-todos],[data-exportar-lista],[data-exportar-item],[data-expandir-lista],[data-calendario],[data-dia],[data-mover-mes],[data-ultima-data],[data-kpi],[data-kpi-extra],[data-png],[data-tipo-evolucao],[data-formato-assunto],[data-dim-resultado],[data-remover-filtro],[data-eixo-rapido]');
    if (!el || !data) return;
    const d = el.dataset;
    if (d.periodo) {
      const t = today(), month = t.slice(0, 7);
      const patch = d.periodo === 'hoje'
        ? { inicio: t, fim: t }
        : d.periodo === 'mes'
          ? { inicio: month + '-01', fim: M.monthEnd(month) }
          : d.periodo === 'ano'
            ? { inicio: t.slice(0, 4) + '-01-01', fim: t.slice(0, 4) + '-12-31' }
            : /^20\d\d-(0[1-9]|1[0-2])$/.test(d.periodo)
              ? { inicio: d.periodo + '-01', fim: M.monthEnd(d.periodo) }
              : { inicio: '', fim: '' };
      setFilters(patch); notify(d.periodo === 'hoje' ? 'Consulta diária selecionada. A fonte mensal não fornece total por dia.' : 'Período aplicado aos indicadores.');
    }
    else if (d.mes) { monthFilter(d.mes); notify('Mês aplicado: ' + monthLabel(d.mes) + '.'); }
    else if (d.eixoRapido) { setFilters(state.eixo === d.eixoRapido ? { eixo: '', modalidade: '', grupo: '', subcategorias: [] } : d.eixoRapido === 'TEMPO_SERVICO' ? { eixo: 'TEMPO_SERVICO', modalidade: '', grupo: '' } : { eixo: 'PROGRESSAO', subcategorias: [] }); }
    else if (d.removerFiltro) {
      if (d.removerFiltro === 'todos') { $('limpar').click(); }
      else if (d.removerFiltro === 'periodo') setFilters({ inicio: '', fim: '' });
      else if (d.removerFiltro.startsWith('sub:')) { const code = d.removerFiltro.slice(4); setFilters({ subcategorias: state.subcategorias.filter(x => x !== code) }); }
      else setFilters({ [d.removerFiltro]: '' });
    }
    else if (d.tipoEvolucao) { evolutionType = d.tipoEvolucao; render(); }
    else if (d.formatoAssunto) { subjectChartType = d.formatoAssunto; render(); }
    else if (d.dimResultado) { resultsDimension = d.dimResultado; render(); }
    else if (d.grupo) setFilters({ eixo: 'PROGRESSAO', grupo: state.grupo === d.grupo ? '' : d.grupo, subcategorias: [] });
    else if (d.sub) setFilters({ eixo: 'TEMPO_SERVICO', modalidade: '', grupo: '', subcategorias: state.subcategorias.includes(d.sub) ? state.subcategorias.filter(x => x !== d.sub) : [...state.subcategorias, d.sub] });
    else if (d.serie) setFilters(d.serie === 'TEMPO_SERVICO' ? { eixo: 'TEMPO_SERVICO', modalidade: '', grupo: '' } : { eixo: 'PROGRESSAO', modalidade: state.modalidade === d.serie ? '' : d.serie, subcategorias: [] });
    else if (d.medida) { graphMeasure = d.medida; render(); }
    else if (d.consulta) { queryMode = d.consulta; queryPage = 0; render(); }
    else if (d.detalhe) { selected = visible.find(c => cellKey(c) === d.detalhe) || null; showDialog('Ficha do agregado público', detailContent(selected, true)); if ($('detalheSelecao')) $('detalheSelecao').innerHTML = detailContent(selected); }
    else if (d.paginar) { const [target, direction] = d.paginar.split(':'); if (target === 'lista') queryPage += direction === 'proxima' ? 1 : -1; else tablePage += direction === 'proxima' ? 1 : -1; render(); }
    else if (d.ordenar) { sortDirection = tableSort === d.ordenar ? -sortDirection : 1; tableSort = d.ordenar; tablePage = 0; render(); }
    else if (Object.hasOwn(d, 'verTodos')) { pageSize = 10000; render(); }
    else if (Object.hasOwn(d, 'exportarLista')) exportCsv(M.searchCells(visible, query, data.catalogo), true);
    else if (d.exportarItem) exportCsv(visible.filter(c => cellKey(c) === d.exportarItem), true);
    else if (Object.hasOwn(d, 'expandirLista')) showDialog('Todos os agregados da lista', tableHTML(...(() => { const rows = M.cellsToRows(M.sortCells(M.searchCells(visible, query, data.catalogo)), data.catalogo); return [rows[0], rows.slice(1)]; })()));
    else if (d.calendario) { calendarMonth = d.calendario; render(); $('mesCalendario').focus({ preventScroll: true }); }
    else if (d.dia) { selectedDay = d.dia; if (page === 'dia') { setFilters({ inicio: selectedDay, fim: selectedDay }); } else location.hash = 'dia'; }
    else if (d.moverMes) { const [y, m] = calendarMonth.split('-').map(Number); const date = new Date(Date.UTC(y, m - 1 + Number(d.moverMes), 1, 12)); if (date.getUTCFullYear() >= 2026 && date.getUTCFullYear() <= 2099) { calendarMonth = date.toISOString().slice(0, 7); render(); } }
    else if (Object.hasOwn(d, 'ultimaData') && data.cobertura.ultima_publicacao) { selectedDay = data.cobertura.ultima_publicacao; setFilters({ inicio: selectedDay, fim: selectedDay }); }
    else if (d.kpi) {
      if (d.kpi === 'atos') {
        showDialog('Atos identificados no DOE', '<p>Atos distintos no recorte: <b>' + esc(M.metricLabel(M.qualityMetric(data, state, visible, 'atos'))) + '</b>.</p><p>Um ato pode conter várias decisões e aparecer em várias células. A contagem de resenhas distintas não está disponível. Não some as ocorrências de atos das células.</p><p>Filtros: ' + esc(describeFilters()) + '</p>');
        return;
      }
      const entry = kpis.find(x => x[0] === d.kpi);
      if (entry) showDialog(entry[1], '<p>' + esc(entry[2]) + '</p><p>' + (d.kpi === 'decisoes' ? 'Contagem do recorte: <b>' + esc(M.metricLabel(M.decisionMetric(data, state, visible))) + '</b>. O total geral e os agregados publicáveis têm escopos diferentes; células pequenas ficam preservadas.' : 'Este indicador não pode ser calculado a partir dos agregados disponíveis. — significa “Não verificado / não divulgado”, nunca zero presumido.') + '</p><p class="data-note">Período e filtros: ' + esc(describeFilters()) + '</p>');
    }
    else if (d.kpiExtra) {
      const entry = extraKpis.find(x => x[0] === d.kpiExtra);
      if (entry) showDialog(entry[1], '<p>' + esc(entry[2]) + '</p><p class="data-note">Categoria documental: ' + esc(entry[3]) + ' · Recorte: ' + esc(describeFilters()) + '</p>');
    }
    else if (Object.hasOwn(d, 'png')) savePng(el);
  });

  document.addEventListener('change', e => {
    if (e.target.matches('[data-tamanho]')) { pageSize = Number(e.target.value); queryPage = tablePage = 0; render(); }
    if (e.target.matches('[data-unidade]')) { chartUnit = e.target.value; render(); }
    if (e.target.matches('[data-granularidade]') && e.target.value !== 'mes') { e.target.value = 'mes'; notify('A fonte pública só permite gráficos mensais. A granularidade solicitada não está disponível.'); }
    if (e.target.id === 'mesCalendario' && /^20\d\d-(0[1-9]|1[0-2])$/.test(e.target.value) && e.target.value >= '2026-01') { calendarMonth = e.target.value; render(); }
  });

  let searchTimer;
  document.addEventListener('input', e => {
    if (e.target.id !== 'buscaLista') return;
    query = e.target.value; queryPage = 0; clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const focused = document.activeElement?.id === 'buscaLista';
      const selectionStart = $('buscaLista')?.selectionStart;
      const wrapper = $('buscaLista')?.closest('.panel');
      if (!wrapper) return;
      wrapper.outerHTML = queryPanel();
      if (focused) { $('buscaLista').focus({ preventScroll: true }); try { $('buscaLista').setSelectionRange(selectionStart, selectionStart); } catch (_) { /* campo de busca */ } }
    }, 180);
  });

  document.addEventListener('toggle', e => {
    if (!e.target.matches('details.query-item') || !e.target.open) return;
    selected = visible.find(c => cellKey(c) === e.target.dataset.item) || null;
    document.querySelectorAll('details.query-item[open]').forEach(x => { if (x !== e.target) x.open = false; });
    if ($('detalheSelecao')) $('detalheSelecao').innerHTML = detailContent(selected);
  }, true);

  document.addEventListener('submit', e => {
    if (e.target.id !== 'formDia') return;
    e.preventDefault(); const d = $('dataDia').value;
    if (M.validDate(d)) { selectedDay = d; setFilters({ inicio: d, fim: d }); }
  });

  $('exportarCsv').onclick = () => exportCsv();
  $('exportarXlsx').onclick = () => { if (data && root.GEDIVXLSX) root.GEDIVXLSX.baixar(exportRows(), 'GEDIV_agregados_publicos.xlsx'); };
  $('exportarPdf').onclick = () => {
    if (!data || !root.GEDIVPDF) return;
    const table = M.cellsToRows(M.sortCells(visible, tableSort, sortDirection), data.catalogo);
    root.GEDIVPDF.baixar({
      titulo: 'Observatório do Diário Oficial | Painel GEDIV',
      metadados: [...exportRows().slice(1, 6),
        ['Recorte', (M.selectionIssue(state) || M.coverageIssue(data, state)) || 'Agregados publicáveis parciais. Nenhum dado individual.'],
        ['Indicadores', 'Processos, resenhas, deferidos, indeferidos, refeitos e tornados sem efeito: não verificado / não divulgado.'],
        ['Decisões (faixa)', M.metricLabel(M.decisionMetric(data, state, visible))]],
      cabecalho: table[0], linhas: table.slice(1)
    });
  };
  $('imprimir').onclick = () => { if (data) { buildPrint(); window.print(); } };
  window.addEventListener('beforeprint', buildPrint);
  window.addEventListener('hashchange', () => route());
  window.addEventListener('popstate', () => { state = readLocation(); route(); });
  let resizeTimer;
  window.addEventListener('resize', () => {
    if (!window.matchMedia('(max-width:780px)').matches) closeMenu(false);
    clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (data) fitPlots(); }, 120);
  });

  async function load(manual = false) {
    if (loading) return;
    loading = true; $('atualizar').disabled = true; $('erro').hidden = true; $('estado').hidden = false;
    $('pagina').setAttribute('aria-busy', 'true');
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('./dados.json', { cache: 'no-cache', signal: controller.signal });
      if (!response.ok) throw new Error('A projeção pública não está disponível (HTTP ' + response.status + '). Use Tentar novamente.');
      data = M.validateProjection(await response.json());
      populate();
      $('estado').innerHTML = '<span aria-hidden="true">✓</span><div><b>Projeção real carregada · contagens protegidas em faixas</b><p>Use os filtros laterais ou clique nas barras e fatias dos gráficos para refinar a consulta.</p></div>';
      $('exportarCsv').disabled = $('imprimir').disabled = false;
      $('exportarPdf').disabled = !root.GEDIVPDF; $('exportarXlsx').disabled = !root.GEDIVXLSX;
      render(true);
      if (manual) notify('Projeção relida com sucesso. Isso não iniciou coleta nem conferência. Gerada em ' + timestamp(data.atualizado_em) + '.');
    } catch (error) {
      data = null; visible = []; selected = null; cards();
      if ($('detalhe').open) $('detalhe').close();
      $('estado').hidden = true; $('erro').hidden = false; $('restricaoRecorte').hidden = true;
      $('mensagemErro').textContent = error.name === 'AbortError' ? 'A leitura demorou além do esperado. Verifique a conexão e tente novamente.' : error instanceof SyntaxError ? 'O arquivo dados.json não pôde ser lido. A projeção precisa estar disponível em JSON público válido.' : error.message;
      $('pagina').innerHTML = '<h2 id="tituloPagina">Dados indisponíveis</h2>' + empty('Consulta temporariamente indisponível', 'Nenhum valor anterior foi mantido como se estivesse atualizado. Use Tentar novamente.');
      $('atualizacao').textContent = 'Dados indisponíveis'; $('situacaoResumo').textContent = 'Falha ao ler a projeção';
      $('coberturaTopoResumo').textContent = 'Cobertura indisponível'; $('versaoResumo').textContent = '';
      $('exportarCsv').disabled = $('exportarXlsx').disabled = $('exportarPdf').disabled = $('imprimir').disabled = true;
      $('pagina').setAttribute('aria-busy', 'false'); buildPrint();
    } finally { clearTimeout(timeout); loading = false; $('atualizar').disabled = false; }
  }
  $('atualizar').onclick = () => load(true);
  $('tentarNovamente').onclick = () => load(true);
  const headerObserver = new ResizeObserver(() => {
    document.documentElement.style.setProperty('--header-height', Math.ceil(document.querySelector('.topbar').getBoundingClientRect().height) + 'px');
  });
  headerObserver.observe(document.querySelector('.topbar'));
  route(true); cards(); load();
})(typeof window !== 'undefined' ? window : globalThis);
