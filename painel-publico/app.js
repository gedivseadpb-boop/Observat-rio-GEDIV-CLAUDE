/* Interface pública GEDIV. Fonte única: dados.json, contrato protegido versão 1. */
(function (root) {
  'use strict';
  if (typeof document === 'undefined') { module.exports = require('./modelo.js'); return; }
  const M = root.GedivModelo;
  root.GedivPublico = M;
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pages = { geral: 'Visão geral', progressao: 'Progressão Funcional', tempo: 'Tempo de Serviço', dia: 'Publicações do dia', historico: 'Histórico', alteracoes: 'Alterações / Refeitos', outras: 'Outras publicações', cobertura: 'Edições e fontes', pendencias: 'Pendências', gerencial: 'Área gerencial' };
  const colors = ['#2870db', '#13a985', '#ed9440', '#cd7549', '#c9a02b', '#d08070', '#9b718a'];
  const series = [ { key: 'VERTICAL', name: 'Progressão Vertical', color: colors[0] }, { key: 'HORIZONTAL', name: 'Progressão Horizontal', color: colors[1] }, { key: 'TEMPO_SERVICO', name: 'Tempo de Serviço', color: colors[2] } ];
  const kpis = [
    ['processos', 'Total de processos', 'Processos distintos. Não equivalem ao número de decisões ou de ocorrências.'],
    ['resenhas', 'Total de resenhas', 'Resenhas distintas. Um ato não é necessariamente uma resenha.'],
    ['decisoes', 'Total de decisões individuais', 'Decisões vigentes de publicações originais. O número é divulgado em faixas; a identificação individual é restrita.'],
    ['deferidos', 'Deferidos', 'Decisões com resultado de deferimento expresso. A projeção atual não discrimina resultados.'],
    ['indeferidos', 'Indeferidos', 'Decisões com resultado de indeferimento expresso. A projeção atual não discrimina resultados.'],
    ['refeitos', 'Refeitos', 'Republicações vinculadas ao ato original. Usam a data do evento modificador.'],
    ['sem_efeito', 'Tornados sem efeito', 'Atos com evento de anulação documentalmente vinculado e validado. Não são contados como indeferimentos.']
  ];
  let data = null, state = M.novoEstado(), visible = [], page = 'geral', loading = false;
  let query = '', queryMode = 'agregados', queryPage = 0, pageSize = 5, tablePage = 0, tableSort = 'periodo', sortDirection = -1, selected = null;
  let calendarMonth = '', selectedDay = '', graphMeasure = 'quantidade', chartUnit = 'decisoes', toastTimer, focusBeforeDialog;
  const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  function dayLabel(v) { return M.validDate(v) ? v.split('-').reverse().join('/') : 'Não extraído'; }
  function monthLabel(p) { return /^\d{4}-\d{2}$/.test(p || '') ? new Intl.DateTimeFormat('pt-BR', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(p + '-01T12:00:00Z')).replace(' de ', '/') : 'Não extraído'; }
  function timestamp(v) { const d = new Date(v); return Number.isNaN(d.getTime()) ? 'Não informada' : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(d); }
  const groupName = code => data.catalogo.grupos.find(g => g.codigo === code)?.nome || 'Grupo não informado';
  const subName = code => data.catalogo.subcategorias.find(s => s.codigo === code)?.nome || 'Assunto não informado';
  const cellCategory = c => c.eixo === 'TEMPO_SERVICO' ? (c.subcategoria ? c.subcategoria + ' · ' + subName(c.subcategoria) : 'Assunto não informado') : (c.grupo ? c.grupo + ' · ' + groupName(c.grupo) : 'Grupo não informado');
  const cellTitle = c => M.EIXOS[c.eixo] + (c.modalidade ? ' · ' + M.MODALIDADES[c.modalidade] : '');
  const cellKey = c => JSON.stringify([c.periodo, c.eixo, c.modalidade, c.grupo, c.subcategoria, c.situacao]);
  const matchesSeries = (c, s) => s === 'TEMPO_SERVICO' ? c.eixo === s : c.eixo === 'PROGRESSAO' && c.modalidade === s;
  const filteredMetric = (cells, prop = 'decisoes') => M.sumMetrics(cells.map(c => c[prop]));
  const pill = (text, cls = '') => '<span class="pill ' + esc(cls) + '">' + esc(text) + '</span>';
  const empty = (title, text, locked = false) => '<div class="empty-state">' + (locked ? '<span class="lock-symbol" aria-hidden="true">◇</span>' : '') + '<b>' + esc(title) + '</b><p>' + esc(text) + '</p></div>';
  const section = (title, subtitle, badge = 'Dados públicos') => '<div class="section-heading"><div><h2 id="tituloPagina" tabindex="-1">' + esc(title) + '</h2><p>' + esc(subtitle) + '</p></div>' + pill(badge) + '</div>';
  const panel = (title, desc, content, actions = '', cls = '') => '<section class="panel ' + cls + '"><div class="panel-head"><div><h3>' + esc(title) + '</h3><p>' + esc(desc) + '</p></div>' + actions + '</div>' + content + '</section>';
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
    ['resultado', 'tipo', 'coberturaFiltro'].forEach(k => { if (state[k]) parts.push($(k).selectedOptions[0]?.textContent || state[k]); });
    return parts.join(' · ') || 'Toda a base disponível · cobertura parcial';
  }
  function cards() {
    const decision = data ? M.decisionMetric(data, state, visible) : M.vazio();
    $('indicadores').innerHTML = kpis.map(([key, title, help]) => {
      const m = key === 'decisoes' ? decision : M.vazio();
      return '<article class="metric-card ' + (M.numberBounds(m) ? 'available' : '') + '"><span>' + esc(title) + '</span><strong>' + esc(M.metricLabel(m)) + '</strong><small>' + (M.numberBounds(m) ? (M.summaryFor(data, state) ? 'Base do recorte, em faixas' : 'Agregados publicáveis parciais') : data ? 'Não verificado / não divulgado' : 'Aguardando dados') + '</small><button class="metric-help" type="button" data-kpi="' + key + '" aria-label="Entender: ' + esc(title) + '">ⓘ</button></article>';
    }).join('');
  }
  function qualityCards() {
    const rows = [ ['Decisões conferidas', M.qualityMetric(data, state, visible, 'conferidos'), 'Conferência administrativa registrada'], ['Decisões provisórias', M.qualityMetric(data, state, visible, 'provisorios'), 'Aguardam conferência administrativa'], ['Atos identificados', M.qualityMetric(data, state, visible, 'atos'), 'Atos distintos; não equivalem a resenhas'], ['Publicações pendentes', M.qualityMetric(data, state, visible, 'publicacoes_pendentes'), 'Revisão administrativa ainda pendente'] ];
    return '<div class="support-cards">' + rows.map(([title, m, note]) => '<div class="support-card"><span>' + esc(title) + '</span><b>' + esc(M.metricLabel(m)) + '</b><small>' + esc(M.numberBounds(m) ? note : 'Não calculável para este recorte') + '</small></div>').join('') + '</div>';
  }
  function chartControls(id) {
    return '<div class="chart-actions"><label>Unidade <select data-unidade aria-label="Unidade do gráfico ' + id + '"><option value="decisoes"' + (chartUnit === 'decisoes' ? ' selected' : '') + '>Decisões</option><option value="atos"' + (chartUnit === 'atos' ? ' selected' : '') + '>Ocorrências de atos nas células</option></select></label><label>Período <select data-granularidade aria-label="Granularidade do gráfico ' + id + '"><option value="mes">Mensal · disponível</option><option value="semana">Semanal · não disponível</option><option value="dia">Diária · não disponível</option></select></label><button class="text-button" type="button" data-png>↓ PNG</button></div>';
  }
  function evolution(line = false) {
    const periods = [...new Set(visible.map(c => c.periodo))].sort();
    const values = periods.map(p => series.map(s => filteredMetric(visible.filter(c => c.periodo === p && matchesSeries(c, s.key)), chartUnit)));
    const W = 700, H = 260, left = 48, right = 20, top = 28, bottom = 46, w = W - left - right, h = H - top - bottom;
    const max = Math.max(5, ...values.flatMap(row => row.map(m => M.numberBounds(m)?.max || 0)));
    let svg = '';
    if (periods.length) {
      for (const tick of [0, Math.ceil(max / 2), max]) { const y = top + h - tick / max * h; svg += '<line class="grid-line" x1="' + left + '" x2="' + (W - right) + '" y1="' + y + '" y2="' + y + '"/><text x="' + (left - 8) + '" y="' + (y + 4) + '" text-anchor="end">' + tick + '</text>'; }
      const step = w / periods.length, bw = Math.min(34, step / 5);
      if (line) series.forEach((s, j) => {
        // Une somente meses consecutivos: uma lacuna de cobertura nunca vira uma linha contínua.
        let previous = null;
        periods.forEach((p, i) => { const b = M.numberBounds(values[i][j]); if (!b) { previous = null; return; } const x = left + step * (i + .5), y = top + h - b.min / max * h, serial = Number(p.slice(0, 4)) * 12 + Number(p.slice(5));
          if (previous && serial === previous.serial + 1) svg += '<line x1="' + previous.x + '" y1="' + previous.y + '" x2="' + x + '" y2="' + y + '" stroke="' + s.color + '" stroke-width="3"/>';
          previous = { x, y, serial };
        });
      });
      periods.forEach((p, i) => {
        values[i].forEach((m, j) => { const b = M.numberBounds(m); if (!b) return; const x = left + step * (i + .5) + (line ? 0 : (j - 1.5) * (bw + 5)), y = top + h - b.min / max * h, high = top + h - b.max / max * h;
          const label = monthLabel(p) + ' · ' + series[j].name + ': ' + M.metricLabel(m) + ' ' + (chartUnit === 'decisoes' ? 'decisões' : 'ocorrências de atos') + '. Selecionar mês.';
          svg += '<g class="chart-hit" role="button" tabindex="0" data-mes="' + p + '" aria-label="' + esc(label) + '"><title>' + esc(label) + '</title>';
          if (line) svg += '<line x1="' + x + '" x2="' + x + '" y1="' + high + '" y2="' + y + '" stroke="' + series[j].color + '" stroke-width="7" opacity=".3"/><circle class="line-mark" cx="' + x + '" cy="' + y + '" r="6" stroke="' + series[j].color + '"/>';
          else svg += '<rect x="' + x + '" y="' + y + '" width="' + bw + '" height="' + Math.max(1, b.min / max * h) + '" rx="3" fill="' + series[j].color + '"/><rect class="range-tail" x="' + x + '" y="' + high + '" width="' + bw + '" height="' + (b.max - b.min) / max * h + '" rx="3" fill="' + series[j].color + '"/>';
          svg += '<text x="' + (x + (line ? 0 : bw / 2)) + '" y="' + (high - 8) + '" text-anchor="middle">' + esc(M.metricLabel(m)) + '</text></g>';
        });
        svg += '<text x="' + (left + step * (i + .5)) + '" y="' + (H - 18) + '" text-anchor="middle">' + esc(monthLabel(p)) + '</text>';
      });
    }
    const body = chartControls(line ? 'histórico' : 'evolução') + (svg ? '<div class="chart-box"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + H + '" role="group" aria-label="' + (line ? 'Linhas' : 'Colunas agrupadas') + ' por mês, limites das faixas publicáveis">' + svg + '</svg></div>' : empty('Sem agregado publicável no recorte', M.selectionIssue(state) || 'Dados preservados ou não divulgados. Isso não confirma ausência de publicação.')) + legend()
      + '<p class="data-note">Parte sólida: limite inferior. Parte clara: restante da faixa. ' + (chartUnit === 'atos' ? 'Ocorrências de atos nas células podem se repetir; não são atos distintos.' : 'São decisões de agregados publicáveis, não totais exatos da base.') + '</p>'
      + alternative(['Mês', ...series.map(s => s.name)], periods.map((p, i) => [monthLabel(p), ...values[i].map(M.metricLabel)]), 'Mesmos dados do gráfico · ' + (chartUnit === 'decisoes' ? 'decisões' : 'ocorrências de atos') + ' em faixas');
    return panel(line ? 'Evolução histórica' : 'Evolução das publicações', 'Dados mensais por modalidade · selecione um mês para consultar', body);
  }
  function donut(ts = false) {
    const items = ts ? data.catalogo.subcategorias.map((s, i) => ({ key: s.codigo, name: s.codigo + ' · ' + s.nome, color: colors[i], metric: filteredMetric(visible.filter(c => c.eixo === 'TEMPO_SERVICO' && c.subcategoria === s.codigo)) })) : series.map(s => ({ ...s, metric: filteredMetric(visible.filter(c => matchesSeries(c, s.key))) }));
    const present = items.filter(i => M.numberBounds(i.metric));
    const total = M.sumMetrics(present.map(i => i.metric)), sumMin = present.reduce((n, i) => n + M.numberBounds(i.metric).min, 0);
    let offset = 0;
    const paths = present.map(i => { const size = sumMin ? M.numberBounds(i.metric).min / sumMin * 100 : 0; const path = '<circle class="chart-hit" cx="60" cy="60" r="43" pathLength="100" stroke="' + i.color + '" stroke-dasharray="' + size + ' ' + (100 - size) + '" stroke-dashoffset="' + (-offset) + '" role="button" tabindex="0" data-' + (ts ? 'sub' : 'serie') + '="' + i.key + '" aria-label="Filtrar ' + esc(i.name) + '"><title>' + esc(i.name + ': ' + M.metricLabel(i.metric)) + '</title></circle>'; offset += size; return path; }).join('');
    const rows = items.map(i => [i.name, M.metricLabel(i.metric), M.shareLabel(M.shareInterval(i.metric, present.map(x => x.metric)))]);
    const body = '<div class="donut-layout"><div class="donut"><svg viewBox="0 0 120 120" role="group" aria-label="Distribuição dos limites inferiores das faixas publicáveis"><circle cx="60" cy="60" r="43"/>' + paths + '</svg><div class="donut-center"><b>' + esc(M.metricLabel(total)) + '</b><small>' + (present.length ? 'decisões no recorte publicável' : 'Não divulgado') + '</small></div></div><div class="donut-legend">' + items.map((i, k) => '<button type="button" data-' + (ts ? 'sub' : 'serie') + '="' + i.key + '" title="Consultar ' + esc(i.name) + '"><i class="swatch" style="--series:' + i.color + '"></i><span>' + esc(i.name) + ' <b>' + esc(M.metricLabel(i.metric)) + '</b><small>' + (M.numberBounds(i.metric) ? esc(rows[k][2]) + ' entre agregados exibidos' : 'Não divulgado / não verificado') + '</small></span></button>').join('') + '</div></div><p class="data-note">Arcos proporcionais aos limites inferiores. Percentuais são intervalos entre os agregados exibidos; não representam toda a base. Categorias preservadas não entram no denominador.</p>' + alternative(['Assunto', 'Decisões (faixa)', '% entre agregados exibidos (faixa)'], rows, 'Sem inferência sobre células suprimidas');
    return panel(ts ? 'Tempo de Serviço por serviço' : 'Publicações por assunto', 'Selecione a legenda para consultar · dois eixos de indicadores', body);
  }
  function bars(ts = false) {
    const items = ts ? data.catalogo.subcategorias : [...data.catalogo.grupos, { codigo: 'NAO_INFORMADO', nome: 'Grupo não informado' }];
    const values = items.map(i => filteredMetric(visible.filter(c => c.eixo === (ts ? 'TEMPO_SERVICO' : 'PROGRESSAO') && (ts ? c.subcategoria === i.codigo : i.codigo === 'NAO_INFORMADO' ? c.grupo === null : c.grupo === i.codigo))));
    const present = values.filter(M.numberBounds), max = Math.max(1, ...present.map(m => M.numberBounds(m).max));
    const controls = '<div class="segment-control" role="group" aria-label="Medida das barras"><button type="button" data-medida="quantidade" aria-pressed="' + (graphMeasure === 'quantidade') + '">Quantidade</button><button type="button" data-medida="percentual" aria-pressed="' + (graphMeasure === 'percentual') + '">%</button></div>';
    const rows = items.map((i, k) => { const b = M.numberBounds(values[k]), perc = M.shareInterval(values[k], present), current = ts ? state.subcategorias.includes(i.codigo) : state.grupo === i.codigo;
      return '<button type="button" class="bar-row" data-' + (ts ? 'sub' : 'grupo') + '="' + i.codigo + '" aria-pressed="' + current + '" aria-label="' + esc(i.codigo + ', ' + i.nome + ', ' + (b ? M.metricLabel(values[k]) + ' decisões' : 'não divulgado')) + '"><span class="bar-label">' + esc(i.codigo === 'NAO_INFORMADO' ? 'Não informado' : i.codigo) + '<small>' + esc(i.nome) + '</small></span><span class="bar-track" style="--series:' + (ts ? colors[2] : colors[0]) + '" aria-hidden="true">' + (b ? '<i style="width:' + (graphMeasure === 'quantidade' ? b.min / max * 100 : perc?.min || 0) + '%"></i><i class="tail" style="width:' + (graphMeasure === 'quantidade' ? (b.max - b.min) / max * 100 : (perc?.max || 0) - (perc?.min || 0)) + '%"></i>' : '') + '</span><span class="bar-value">' + (b ? esc(graphMeasure === 'quantidade' ? M.metricLabel(values[k]) : M.shareLabel(perc)) : '—<small class="unavailable"> Não divulgado</small>') + '</span></button>';
    }).join('');
    return panel(ts ? 'Tempo de Serviço por modalidade' : 'Progressão por grupo do PCCR', ts ? 'Os sete serviços permanecem visíveis · selecione para filtrar' : 'Catálogo de 16 grupos · códigos sem confirmação não são equiparados', '<div class="bar-list">' + rows + '</div><p class="data-note">Decisões em faixas. % = intervalo entre agregados exibidos. — indica recorte preservado ou não disponível; não indica zero.</p>' + alternative(['Categoria', 'Decisões (faixa)', '% exibido (faixa)'], items.map((i, k) => [i.codigo + ' · ' + i.nome, M.metricLabel(values[k]), M.shareLabel(M.shareInterval(values[k], present))])), controls);
  }
  function results(kind = 'area') {
    const items = kind === 'ts' ? data.catalogo.subcategorias.map(i => ({ name: i.codigo + ' · ' + i.nome, key: i.codigo, attr: 'sub' })) : kind === 'grupos' ? [...data.catalogo.grupos, { codigo: 'NAO_INFORMADO', nome: 'Grupo não informado' }].map(i => ({ name: i.codigo + ' · ' + i.nome, key: i.codigo, attr: 'grupo' })) : series.map(s => ({ ...s, attr: 'serie' }));
    const body = '<div class="chart-legend"><span class="legend-item"><i class="swatch" style="--series:var(--green)"></i>Deferido</span><span class="legend-item"><i class="swatch" style="--series:var(--red)"></i>Indeferido</span><span class="legend-item"><i class="swatch" style="--series:#71849a"></i>Outros</span></div>' + items.map(i => '<div class="result-row"><button class="text-button" type="button" data-' + i.attr + '="' + i.key + '">' + esc(i.name) + '</button><span class="result-track stacked-swatch">Não verificado</span><span class="result-note">Resultado não divulgado</span></div>').join('') + '<p class="data-note">A fonte pública não discrimina resultados. Barras empilhadas e percentuais de deferimento dependem desses agregados; não foram inventados segmentos ou denominadores.</p>' + alternative(['Área / modalidade', 'Deferidos', 'Indeferidos', 'Outros'], items.map(i => [i.name, 'Não verificado', 'Não verificado', 'Não verificado']));
    return panel(kind === 'ts' ? 'Resultado por modalidade · Tempo de Serviço' : kind === 'grupos' ? 'Resultados por grupo do PCCR' : 'Resultados por área', 'Distribuição por resultado · disponibilidade da fonte', body, pill('Dados de resultado indisponíveis', 'neutral'));
  }
  function pageControls(info, target) {
    return '<div class="pagination"><button type="button" data-paginar="' + target + ':anterior" aria-label="Página anterior de ' + target + '"' + (info.page === 0 ? ' disabled' : '') + '>‹</button><span>' + (info.total ? (info.page * pageSize + 1) + '–' + Math.min((info.page + 1) * pageSize, info.total) + ' de ' + info.total : 'Nenhum agregado') + ' · ' + (info.page + 1) + '/' + info.pages + '</span><button type="button" data-paginar="' + target + ':proxima" aria-label="Próxima página de ' + target + '"' + (info.page + 1 >= info.pages ? ' disabled' : '') + '>›</button><label>Exibir<select data-tamanho aria-label="Itens por página"><option value="5"' + (pageSize === 5 ? ' selected' : '') + '>5</option><option value="10"' + (pageSize === 10 ? ' selected' : '') + '>10</option><option value="10000"' + (pageSize === 10000 ? ' selected' : '') + '>Todos</option></select></label></div>';
  }
  function queryPanel() {
    const items = M.sortCells(M.searchCells(visible, query, data.catalogo)), info = M.pagination(items, queryPage, pageSize);
    queryPage = info.page;
    const tabs = '<div class="query-tabs" role="group" aria-label="Forma de consulta">' + [['agregados', 'Agregados'], ['resenha', 'Por resenha'], ['processo', 'Por processo']].map(([key, name]) => '<button type="button" data-consulta="' + key + '" aria-pressed="' + (queryMode === key) + '">' + name + '</button>').join('') + '</div>';
    const search = '<div class="search-field"><label for="buscaLista">Pesquisar os agregados públicos</label><input type="search" id="buscaLista" autocomplete="off" maxlength="100" placeholder="Mês, grupo ou modalidade" value="' + esc(query) + '"></div><p class="field-note">Busca apenas nesta lista; use Exportar lista para este resultado. Consultas individuais ficam na área gerencial.</p>';
    let body;
    if (queryMode !== 'agregados') body = empty(queryMode === 'resenha' ? 'Resenhas não disponibilizadas' : 'Consulta por processo restrita', queryMode === 'resenha' ? 'A projeção pública atual não contém uma lista autorizada de resenhas ou atos. Os agregados mensais não foram convertidos em resenhas fictícias.' : 'Nome, matrícula, processo e evidências individuais exigem autenticação no servidor. Nenhum registro individual é enviado nesta versão.', true) + '<a class="button" href="#gerencial">Entender o acesso gerencial</a>';
    else body = search + '<div id="listaConsulta">' + (info.items.length ? '<div class="query-list">' + info.items.map(c => '<details class="query-item" data-item="' + esc(cellKey(c)) + '"' + (selected && cellKey(selected) === cellKey(c) ? ' open' : '') + '><summary><span><b>' + esc(monthLabel(c.periodo)) + '</b><small>' + esc(cellTitle(c)) + '</small></span><span>' + esc(M.metricLabel(c.decisoes)) + '<small>decisões</small></span></summary><div><p>' + esc(cellCategory(c)) + '</p>' + pill(c.situacao === 'conferido' ? 'Conferido' : 'Provisório', c.situacao) + '<p class="field-note">Agregado mensal protegido; não é uma resenha nem um processo.</p><button type="button" class="button" data-detalhe="' + esc(cellKey(c)) + '">Ver ficha do agregado →</button></div></details>').join('') + '</div>' : empty('Nenhum agregado encontrado', query ? 'Tente outro mês, grupo ou modalidade. A busca não consulta dados individuais.' : 'Dados preservados ou sem agregado publicável neste recorte.')) + pageControls(info, 'lista') + '</div><button class="text-button" type="button" data-exportar-lista' + (!items.length ? ' disabled' : '') + '>↓ Exportar lista (CSV)</button>';
    return panel('Publicações e consultas', 'Agregados públicos e acesso às consultas autorizadas', tabs + body, '<button type="button" class="button compact" data-expandir-lista aria-label="Ampliar a lista de agregados">⛶ Ampliar</button>');
  }
  function detailContent(c, expanded = false) {
    if (!c) return empty('Selecione um agregado na lista', 'Abra uma linha para consultar a ficha, o período e a situação dos dados.');
    let html = '<dl class="detail-list">' + definition('Período', monthLabel(c.periodo)) + definition('Eixo', M.EIXOS[c.eixo]) + definition('Modalidade', c.modalidade ? M.MODALIDADES[c.modalidade] : c.subcategoria ? c.subcategoria + ' · ' + subName(c.subcategoria) : 'Não extraído') + definition('Grupo', c.eixo === 'PROGRESSAO' ? groupName(c.grupo) : 'Não se aplica') + definition('Decisões', M.metricLabel(c.decisoes) + ' (faixa publicável)') + definition('Atos nesta célula', M.metricLabel(c.atos) + ' (não somar como atos distintos)') + definition('Conferência', c.situacao === 'conferido' ? 'Conferido' : 'Provisório · aguarda conferência') + definition('Resenha / ato', 'Não extraído na projeção pública') + definition('Página no DOE', 'Não extraído na projeção pública') + '</dl>';
    if (expanded) html += '<h3>Origem e limites desta ficha</h3><dl class="detail-list">' + definition('Fonte', 'Diário Oficial do Estado da Paraíba') + definition('Projeção gerada', timestamp(data.atualizado_em) + ' (Brasília)') + definition('Versão das regras', data.versao_regras) + definition('Arquivo público', 'dados.json · contrato público versão 1') + definition('Unidade', 'Decisão individual contada em agregado mensal; sem identidade individual') + definition('PDF e página oficial', 'Não extraído; nenhuma URL individual inferida') + definition('Evidência e revisão individual', 'Acesso gerencial seguro necessário') + '</dl><p class="data-note">Uma faixa não revela o valor exato. Um registro pode participar de várias ocorrências; atos, processos e pessoas não são unidades intercambiáveis.</p>';
    return html + '<div class="detail-actions">' + (!expanded ? '<button type="button" class="button primary" data-detalhe="' + esc(cellKey(c)) + '">Abrir ficha completa</button>' : '<button type="button" class="button" data-exportar-item="' + esc(cellKey(c)) + '">↓ Exportar agregado (CSV)</button>') + '<a class="button" href="#cobertura">Edições e fontes</a></div><p class="data-note">PDF oficial por registro: não disponível na projeção. Os dados de identificação permanecem restritos.</p>';
  }
  function recordsPanel() {
    const rows = M.sortCells(visible, tableSort, sortDirection), info = M.pagination(rows, tablePage, pageSize);
    tablePage = info.page;
    const headers = [['periodo', 'Mês'], ['eixo', 'Eixo / modalidade'], ['categoria', 'Grupo / serviço'], ['situacao', 'Conferência'], ['atos', 'Atos na célula'], ['decisoes', 'Decisões']];
    const body = '<div class="table-scroll"><table><caption>Agregados mensais publicáveis · faixas protegidas. Não são registros individuais.</caption><thead><tr>' + headers.map(([key, title]) => '<th scope="col" aria-sort="' + (tableSort === key ? sortDirection === 1 ? 'ascending' : 'descending' : 'none') + '"><button type="button" data-ordenar="' + key + '">' + esc(title) + (tableSort === key ? sortDirection === 1 ? ' ↑' : ' ↓' : ' ↕') + '</button></th>').join('') + '<th scope="col">Consulta</th></tr></thead><tbody>' + (info.items.length ? info.items.map(c => '<tr><td>' + esc(monthLabel(c.periodo)) + '</td><td>' + esc(cellTitle(c)) + '</td><td>' + esc(cellCategory(c)) + '</td><td>' + pill(c.situacao === 'conferido' ? 'Conferido' : 'Provisório', c.situacao) + '</td><td>' + esc(M.metricLabel(c.atos)) + '</td><td><b>' + esc(M.metricLabel(c.decisoes)) + '</b></td><td><button class="table-button" type="button" data-detalhe="' + esc(cellKey(c)) + '">Ver ficha →</button></td></tr>').join('') : '<tr><td colspan="7">Não há agregados publicáveis neste recorte. Isso não confirma ausência de publicações.</td></tr>') + '</tbody></table></div>' + pageControls(info, 'tabela') + '<p class="data-note">Os totais da base incluem recortes que não podem ser divulgados. Atos podem repetir entre células; não some esta coluna como atos distintos. Exportações incluem todas as páginas da seleção.</p>';
    return panel('Tabela dos agregados disponíveis', visible.length + ' agregado(s) neste recorte · ordenar, consultar ou exportar', body, '<button class="button compact" type="button" data-ver-todos>Ver todos os agregados</button>', 'records');
  }
  function coveragePanel() {
    const c = data.cobertura;
    return panel('Cobertura de leitura do Diário Oficial', 'Base documental da projeção inteira · estes números não são filtrados', '<div class="coverage-stats">' + [['Edições disponíveis', c.edicoes], ['Páginas disponíveis', c.paginas], ['Histórico desde 01/01/2026', 'Parcial']].map(([name, v]) => '<div class="coverage-stat"><b>' + esc(v) + '</b><span>' + esc(name) + '</span></div>').join('') + '</div><div class="coverage-notes"><div><b>Período documental disponível</b><p>' + esc(dayLabel(c.primeira_publicacao)) + ' a ' + esc(dayLabel(c.ultima_publicacao)) + '. O intervalo não comprova a existência de todas as edições entre essas datas.</p></div><div><b>Conferência de cobertura</b><p>' + esc(c.ausencia_tecnica_edicoes) + ' edições com ausência técnica proposta de atos pertinentes e ' + esc(c.inconclusivas) + ' inconclusiva(s). Isso não é ausência de edição nem homologação humana.</p></div><div><b>Histórico incompleto</b><p>Datas sem informação continuam não verificadas. Totais por dia, edição, quarentena e situação dependem da matriz documental autorizada.</p></div></div><div class="detail-actions"><a class="button" href="#historico">Ver calendário de cobertura</a><a class="button" href="#pendencias">Ver pendências de conferência</a></div>');
  }
  function overview() {
    const title = page === 'progressao' ? 'Progressão Funcional' : page === 'tempo' ? 'Tempo de Serviço' : 'Visão geral';
    const quick = '<div class="quick-actions"><a class="button primary" href="#progressao">↗ Consultar progressões</a><a class="button" href="#tempo">◷ Consultar Tempo de Serviço</a><a class="button" href="#dia">▤ Publicações do dia</a><a class="button" href="#pendencias">Ver pendências →</a></div>';
    let charts;
    if (page === 'tempo') charts = '<div class="chart-grid">' + bars(true) + results('ts') + evolution() + donut(true) + '</div>' + evolution(true);
    else if (page === 'progressao') charts = '<div class="chart-grid">' + evolution() + donut() + bars() + results('grupos') + '</div>' + evolution(true);
    else charts = '<div class="chart-grid">' + evolution() + donut() + '</div>' + results() + '<div class="chart-grid">' + bars(true) + donut(true) + '</div>' + evolution(true) + bars();
    return section(title, 'Escolha um período, acompanhe os indicadores e abra os detalhes disponíveis.', 'Dois eixos · cobertura parcial') + quick + qualityCards() + '<div class="overview-grid"><div class="charts-column">' + charts + '</div><aside class="query-column" aria-label="Consultas e detalhes">' + queryPanel() + '<section class="panel"><div class="panel-head"><div><h3>Detalhes da seleção</h3><p>Período, contagem, situação e origem</p></div></div><div id="detalheSelecao">' + detailContent(selected) + '</div></section></aside></div>' + recordsPanel() + coveragePanel();
  }
  function history() {
    const year = calendarMonth.slice(0, 4) || today().slice(0, 4), periods = Array.from({ length: 12 }, (_, i) => year + '-' + String(i + 1).padStart(2, '0'));
    const calendarMonths = '<div class="history-months">' + periods.map(p => { const has = data.celulas.some(c => c.periodo === p), inRange = data.cobertura.primeira_publicacao && p >= data.cobertura.primeira_publicacao.slice(0, 7) && p <= data.cobertura.ultima_publicacao.slice(0, 7); return '<button type="button" data-calendario="' + p + '" class="' + (has ? 'available' : '') + '"><b>' + esc(monthLabel(p)) + '</b><small>' + (has ? 'Agregados disponíveis' : inRange ? 'Cobertura diária não informada' : 'Não verificado') + '</small></button>'; }).join('') + '</div>';
    const [y, m] = calendarMonth.split('-').map(Number), first = new Date(Date.UTC(y, m - 1, 1, 12)).getUTCDay(), days = new Date(Date.UTC(y, m, 0, 12)).getUTCDate();
    const cells = Array.from({ length: first }, () => '<span aria-hidden="true"></span>').join('') + Array.from({ length: days }, (_, i) => { const d = calendarMonth + '-' + String(i + 1).padStart(2, '0'); return '<button type="button" data-dia="' + d + '" class="' + (selectedDay === d ? 'selected' : '') + '" aria-label="Consultar cobertura de ' + dayLabel(d) + ', não verificada por dia"><b>' + (i + 1) + '</b><small>Não verificado</small></button>'; }).join('');
    return section('Histórico e cobertura', 'Histórico previsto desde 01/01/2026. Lacunas nunca são apresentadas como ausência de atos.', 'Cobertura documental parcial') + coveragePanel() + panel('Mapa dos meses', 'Selecione um mês para examinar seu calendário; isso ainda não altera os filtros.', calendarMonths) + panel('Calendário de conferência', 'A projeção não inclui a situação de cada dia. Selecione uma data para consultar essa limitação.', '<div class="calendar-controls"><button class="button" type="button" data-mover-mes="-1" aria-label="Mês anterior">‹ Anterior</button><label>Mês <input type="month" id="mesCalendario" min="2026-01" value="' + calendarMonth + '"></label><button class="button" type="button" data-mover-mes="1" aria-label="Próximo mês">Próximo ›</button><button class="text-button" type="button" data-mes="' + calendarMonth + '">Aplicar mês aos indicadores</button></div><div class="calendar">' + ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map(x => '<span class="weekday">' + x + '</span>').join('') + cells + '</div><p class="data-note">Não verificado = sem confirmação diária nesta projeção. Não significa “sem publicação”. Não há calendário de edições ausentes homologado disponível.</p>') + evolution(true) + recordsPanel();
  }
  function daily() {
    return section('Publicações do dia', 'Consulte uma data e a disponibilidade de suas fontes.', dayLabel(selectedDay)) + panel('Consulta por data', 'A atualização relê a projeção disponível; não inicia coleta ou leitura de PDFs.', '<form id="formDia" class="day-picker"><label>Data da publicação<input type="date" id="dataDia" min="2026-01-01" value="' + selectedDay + '" required></label><button class="button primary" type="submit">Consultar este dia</button><button class="button" type="button" data-ultima-data>Última data da base</button></form>' + empty('Situação do dia: não verificada', 'A projeção disponível contém agregados mensais e um resumo de cobertura. Ela não informa a edição, o suplemento ou as publicações de cada dia. Isso não confirma ausência de publicação em ' + dayLabel(selectedDay) + '.') + '<div class="list-status"><div><b>Edição e suplemento</b><p>Identificação diária não extraída nesta projeção.</p></div>' + pill('Não extraído', 'neutral') + '</div><div class="list-status"><div><b>PDF oficial, integridade e leitura</b><p>URL, página, hash do PDF e estado de leitura exigem metadados documentais verificados.</p></div>' + pill('Não verificado', 'neutral') + '</div><div class="list-status"><div><b>Classificação e conferência</b><p>Não há resultados diários autorizados nesta projeção.</p></div>' + pill('Não verificado', 'neutral') + '</div><div class="detail-actions"><a class="button" href="#cobertura">Ver fontes e cobertura disponíveis</a><button class="button" type="button" data-mes="' + selectedDay.slice(0, 7) + '">Consultar o mês completo</button></div>') + coveragePanel();
  }
  function changes() {
    return section('Alterações / Refeitos', 'Republicações, retificações e atos tornados sem efeito são acompanhados separadamente dos dois eixos.', 'Vínculos não disponibilizados') + panel('Histórico de alterações', 'Cada evento precisa de publicação de origem, versão e data próprias.', empty('Eventos ainda não disponibilizados', 'O arquivo público atual não contém vínculos entre originais, republicações, retificações e anulações. Ausência de lista não significa zero eventos.') + tableHTML(['Natureza', 'Ato de origem', 'Data do evento', 'Versão / vínculo', 'Conferência'], [['Republicação / refeito', 'Não extraído', 'Não extraído', 'Não extraído', 'Não verificado'], ['Retificação', 'Não extraído', 'Não extraído', 'Não extraído', 'Não verificado'], ['Tornado sem efeito', 'Não extraído', 'Não extraído', 'Não extraído', 'Não verificado']]) + '<p class="data-note">Linhas acima descrevem os tipos acompanhados, não ocorrências reais. Uma anulação não é um indeferimento. Modificadores não entram nos gráficos de decisões originais.</p>');
  }
  function others() {
    const subjects = ['Publicações relacionadas à GEDIV / DEREH', 'Portarias e atos normativos', 'Alterações legais', 'Abono de permanência', 'Assuntos fora dos dois eixos'];
    return section('Outras publicações', 'Área de apoio para matérias relacionadas à GEDIV e à DEREH; não é um terceiro eixo de indicadores.', 'Triagem e conferência') + panel('Acompanhamento das matérias relacionadas', 'Menção à DEREH, isoladamente, não exclui vínculo com a GEDIV.', empty('Lista de matérias não disponibilizada', 'A projeção pública atual não inclui a triagem documental de outras publicações. Nenhum registro ou resultado foi criado para preencher esta tela.') + subjects.map(x => '<div class="list-status"><div><b>' + esc(x) + '</b><p>Depende de fonte e classificação documental autorizadas.</p></div>' + pill('Não verificado', 'neutral') + '</div>').join('') + '<p class="data-note">Vacância e licença-saúde ficam fora dos indicadores públicos. Abono de permanência depende de definição administrativa.</p><a class="button" href="#pendencias">Ver pendências e dúvidas de classificação</a>');
  }
  function pending() {
    const pendingMetric = M.qualityMetric(data, state, visible, 'publicacoes_pendentes');
    return section('Pendências de conferência', 'Extração automática, interpretação documental e conferência administrativa são etapas distintas.', 'Revisão por exceção') + '<div class="support-cards"><div class="support-card"><span>Publicações pendentes no recorte</span><b>' + esc(M.metricLabel(pendingMetric)) + '</b><small>Faixa autorizada; não é uma lista individual</small></div><div class="support-card"><span>Edições inconclusivas na base inteira</span><b>' + esc(data.cobertura.inconclusivas) + '</b><small>Resumo de cobertura, sem filtro</small></div></div>' + panel('O que precisa de conferência', 'Situação conhecida nesta projeção e limites de interpretação.', '<div class="list-status"><div><b>Resenha 562/2026 · publicação de 23/10/2026</b><p>Interpretação inconclusiva relatada na documentação de continuidade. A situação individual atual não está disponível nesta projeção.</p></div>' + pill('Não verificado', 'neutral') + '</div><div class="list-status"><div><b>Grupos e códigos sem homologação</b><p>TEC. ADM / AST, STF / SFT e denominação INT dependem de confirmação. Não são equiparados por aproximação.</p></div>' + pill('Confirmação necessária', 'provisorio') + '</div><div class="list-status"><div><b>Tempo de Serviço: células preservadas</b><p>Sete serviços sempre acessíveis. Recortes sem divulgação suficiente permanecem desconhecidos, mesmo quando existe um resumo geral do eixo.</p></div>' + pill('Preservado', 'neutral') + '</div><div class="list-status"><div><b>Revisão de registros e evidências</b><p>Consultas e alterações individuais exigem acesso gerencial autenticado e trilha de auditoria.</p></div><a class="button" href="#gerencial">Área gerencial</a></div>') + recordsPanel();
  }
  function sources() {
    return section('Edições e fontes', 'Confira de onde vêm os números e o que ainda não foi disponibilizado.', 'Proveniência dos dados') + coveragePanel() + panel('Situações da cobertura', 'Sem a matriz por edição, não há como repartir o total entre situações.', tableHTML(['Situação documental', 'Quantidade no recorte', 'Significado'], [['Verificada', 'Não verificado', 'Fonte e leitura documental confirmadas'], ['Pendente', 'Não verificado', 'Conferência ainda necessária'], ['Parcial', 'Não verificado', 'Leitura ou cobertura incompleta'], ['Não verificada', 'Não verificado', 'Sem confirmação suficiente'], ['Quarentena', 'Não verificado', 'Fonte separada para análise de integridade'], ['Ausência confirmada', 'Não verificado', 'Ausência de edição comprovada; não se presume a partir de uma lacuna']]) + '<p class="data-note">As ' + esc(data.cobertura.edicoes) + ' edições são o total disponível na projeção inteira. A distribuição por situação não foi inferida a partir desse total.</p>') + panel('Origem e atualização', 'Mesma fonte para indicadores, gráficos, tabelas e exportações.', '<dl class="detail-list">' + definition('Origem', 'Diário Oficial do Estado da Paraíba · dados reais') + definition('Arquivo da consulta', 'dados.json · projeção pública protegida versão 1') + definition('Gerada em', timestamp(data.atualizado_em) + ' (Brasília)') + definition('Versão de regras', data.versao_regras) + definition('Contagens publicáveis', 'Agregados mensais em faixas de cinco; recortes pequenos omitidos antes da publicação') + definition('Edições / PDFs individuais', 'Não extraído na projeção pública atual') + definition('Atualizar dados', 'Relê a projeção disponível. Não inicia coleta, OCR ou conferência.') + '</dl><p class="data-note">Um PDF específico só pode ser aberto quando sua URL e página forem verificadas. Esta projeção não fornece esses campos; não foram criados links presumidos.</p>');
  }
  function management() {
    const groups = [['Identificação e publicação', 'Nome, matrícula, processo, órgão, cargo, eixo, modalidade, resultado original, data da publicação, número de resenha / ato, página PDF, menção à GEDIV, tipo e natureza da publicação.'], ['Progressão Funcional', 'Grupo PCCR e descritor original; classes e níveis anteriores e posteriores, inclusive saltos oficiais sem normalização.'], ['Tempo de Serviço', 'Serviço TS-01 a TS-07, origem do tempo, período inicial e final, dias e demais campos publicados.'], ['Fonte, evidência e histórico', 'PDF oficial na página correta, evidência original, situação de validação, revisões, versões, vínculos e trilha de auditoria.']];
    return section('Área gerencial', 'Consultas individuais e revisão ficam separadas da consulta pública.', 'NÃO HABILITADA (SEGURANÇA)') + panel('Acesso individual ainda não habilitado', 'Esta prévia não possui uma conexão ativa com o servidor gerencial autenticado.', empty('NÃO HABILITADA (SEGURANÇA)', 'A pesquisa por nome, matrícula ou processo e as fichas individuais exigem autenticação no servidor, autorização por perfil e auditoria. Nenhum dado pessoal foi incluído no site para simular esse acesso.', true) + '<p class="data-note">A estrutura existente do sistema privado foi preservada. Sua ativação nesta interface depende de um serviço gerencial seguro e da conexão com a base privada autorizada.</p>') + panel('Consultas e fichas previstas na área segura', 'Resenha → tabela completa de ocorrências → processo → ficha documental e PDF.', '<div class="field-groups">' + groups.map(([title, text]) => '<details><summary>' + esc(title) + '</summary><p>' + esc(text) + '</p><p>Campos ausentes: “Não extraído”. Nenhuma ficha individual é carregada nesta prévia.</p></details>').join('') + '</div><p class="data-note">As consultas devem preservar filtros, ordenação, paginação, exportação autorizada e o caminho de volta à resenha. Nomes de campos acima descrevem a estrutura; não são dados de exemplo.</p>');
  }
  function syncForm() {
    M.CAMPOS.forEach(k => { $(k).value = state[k]; });
    document.querySelectorAll('[name=servico]').forEach(input => { input.checked = state.subcategorias.includes(input.value); });
    $('modalidade').disabled = $('grupo').disabled = state.eixo === 'TEMPO_SERVICO';
    document.querySelectorAll('[name=servico]').forEach(input => { input.disabled = state.eixo === 'PROGRESSAO'; });
    $('filtrosPendentes').textContent = '';
  }
  function render(sync = false) {
    cards();
    if (!data) return;
    visible = M.filterCells(data.celulas, state);
    if (selected && !visible.some(c => cellKey(c) === cellKey(selected))) selected = null;
    if (sync) syncForm();
    $('filtrosAtivos').textContent = describeFilters();
    const issue = M.selectionIssue(state);
    $('restricaoRecorte').hidden = !issue;
    $('restricaoRecorte').innerHTML = issue ? '<div><b>Este recorte não pode ser calculado</b><p>' + esc(issue) + '</p></div>' : '';
    const contents = { geral: overview, progressao: overview, tempo: overview, historico: history, dia: daily, alteracoes: changes, outras: others, cobertura: sources, pendencias: pending, gerencial: management };
    $('pagina').innerHTML = contents[page]();
    $('pagina').setAttribute('aria-busy', 'false');
    document.querySelectorAll('#abas a, #menuApoio a').forEach(a => { if (a.hash === '#' + page) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    $('contextoCurto').textContent = pages[page];
    $('situacaoResumo').textContent = state.situacao === 'conferido' ? 'Consulta de dados conferidos' : 'Dados reais · conferência parcial';
    document.title = pages[page] + ' | Painel Diário Oficial · GEDIV';
    cards();
    buildPrint();
  }
  function setFilters(patch) {
    state = { ...state, ...patch };
    queryPage = tablePage = 0;
    render(true);
    $('anuncio').textContent = 'Consulta atualizada. ' + (M.selectionIssue(state) || visible.length + ' agregados publicáveis na seleção.');
  }
  function monthFilter(p) { setFilters({ inicio: p + '-01', fim: M.monthEnd(p) }); }
  function populate() {
    $('grupo').innerHTML = '<option value="">Todos os grupos</option>' + data.catalogo.grupos.map(g => '<option value="' + g.codigo + '">' + esc(g.codigo + ' · ' + g.nome) + '</option>').join('') + '<option value="NAO_INFORMADO">Grupo não informado</option>';
    $('listaServicos').innerHTML = data.catalogo.subcategorias.map(s => '<label><input name="servico" type="checkbox" value="' + s.codigo + '"><span><small>' + s.codigo + '</small>' + esc(s.nome) + '</span></label>').join('');
    calendarMonth ||= data.cobertura.ultima_publicacao?.slice(0, 7) || today().slice(0, 7);
    selectedDay ||= today();
    $('atualizacao').textContent = timestamp(data.atualizado_em);
    $('versaoResumo').textContent = 'Mensal · faixas protegidas';
  }
  function route(initial = false) {
    const next = location.hash.slice(1).split('?')[0];
    page = Object.hasOwn(pages, next) ? next : 'geral';
    if (page === 'progressao') state = { ...state, eixo: 'PROGRESSAO', subcategorias: [] };
    if (page === 'tempo') state = { ...state, eixo: 'TEMPO_SERVICO', grupo: '', modalidade: '' };
    if (page === 'dia') { selectedDay ||= today(); state = { ...state, inicio: selectedDay, fim: selectedDay }; }
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
    const definitions = [ ['Conferido', 'Existe registro de conferência administrativa na base. Não se presume por haver um gráfico.'], ['Provisório', 'Extração real aguardando conferência. Não é resultado administrativo oficial.'], ['Não verificado', 'Informação ausente ou insuficiente. Nunca é substituída por zero.'], ['Preservado / não divulgado', 'O recorte pode estar suprimido para proteger pessoas. Não permite concluir ausência de atos.'], ['Quarentena', 'Documento separado para verificar integridade ou leitura. Não é publicação homologada.'], ['Sem edição', 'Só pode ser afirmado com confirmação documental. Uma lacuna não comprova ausência de edição.'], ['Unidades de contagem', 'Edição, resenha, ato, processo, decisão, ocorrência, pessoa e republicação são unidades diferentes.'], ['Faixas e percentuais', 'Contagens positivas são intervalos. As formas dos gráficos usam limites inferiores; percentuais são intervalos entre agregados exibidos.'] ];
    showDialog('Entenda os dados e as contagens', '<p>Esta consulta usa exclusivamente a projeção pública protegida. A cobertura é parcial e as contagens não são totais exatos.</p><div class="definition-list">' + definitions.map(([title, text]) => '<div><b>' + esc(title) + '</b><p>' + esc(text) + '</p></div>').join('') + '</div><p class="data-note">' + esc(data?.privacidade.observacao || '') + '</p>');
  }
  function exportRows(cells = visible, local = false) {
    const rows = [['Painel Diário Oficial | GEDIV · consulta pública'], ['Projeção gerada (Brasília)', timestamp(data.atualizado_em)], ['Versão de regras', data.versao_regras], ['Filtros aplicados', describeFilters()], ['Escopo', local ? 'Lista pesquisada de agregados públicos; sem registros individuais' : 'Todos os agregados publicáveis dos filtros aplicados, incluindo todas as páginas'], ['Limites', 'Faixas protegidas; ausência de agregado não confirma ausência de atos; atos nas células não são somáveis como distintos']];
    if (M.selectionIssue(state)) rows.push(['Recorte indisponível', M.selectionIssue(state)]);
    if (!cells.length) rows.push(['Resultado', 'Sem agregado publicável; isso não equivale a zero publicações']);
    return [...rows, [], ...M.cellsToRows(cells, data.catalogo)];
  }
  function download(blob, filename) { const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  function exportCsv(cells = visible, local = false) { if (data) download(new Blob(['\ufeff' + exportRows(cells, local).map(r => r.map(M.csvValue).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' }), local ? 'GEDIV_lista_publica.csv' : 'GEDIV_agregados_publicos.csv'); }
  function buildPrint() {
    if (!data) { $('impressao').innerHTML = ''; return; }
    const rows = M.cellsToRows(M.sortCells(visible, tableSort, sortDirection), data.catalogo), metric = M.decisionMetric(data, state, visible);
    $('impressao').innerHTML = '<h1>Painel Diário Oficial | GEDIV</h1><h2>Consulta pública · ' + esc(pages[page]) + '</h2><p>Projeção gerada em ' + esc(timestamp(data.atualizado_em)) + ' (Brasília) · ' + esc(data.versao_regras) + '</p><p><b>Filtros:</b> ' + esc(describeFilters()) + '</p><div class="print-metrics">' + kpis.map(([key, title]) => '<div>' + esc(title) + '<b>' + (key === 'decisoes' ? esc(M.metricLabel(metric)) : '— · Não verificado') + '</b></div>').join('') + '</div><div class="print-note">' + esc(M.selectionIssue(state) || 'Agregados mensais publicáveis em faixas. A consulta é parcial; dados suprimidos não são zero. Atos nas células podem repetir e não devem ser somados como atos distintos.') + '</div>' + tableHTML(rows[0], rows.slice(1)) + '<p><b>Cobertura da projeção inteira, sem filtro:</b> ' + data.cobertura.edicoes + ' edições · ' + data.cobertura.paginas + ' páginas · ' + esc(dayLabel(data.cobertura.primeira_publicacao)) + ' a ' + esc(dayLabel(data.cobertura.ultima_publicacao)) + '. Histórico parcial desde 01/01/2026.</p><p>Fonte: Diário Oficial do Estado da Paraíba. Prévia experimental. Não substitui a publicação oficial. Nenhum dado individual integra este relatório.</p>';
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
      const canvas = document.createElement('canvas'); canvas.width = 1400; canvas.height = 700;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = '#153452'; ctx.font = 'bold 24px Arial'; ctx.fillText('GEDIV · ' + button.closest('.panel').querySelector('h3').textContent, 32, 40); ctx.drawImage(img, 0, 70, 1400, 520); ctx.font = '16px Arial'; ctx.fillText('Agregados mensais parciais em faixas · partes sólidas: limites inferiores', 32, 625); ctx.fillText('Projeção: ' + timestamp(data.atualizado_em) + ' (Brasília)', 32, 654);
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
  $('abrirMenu').onclick = () => {
    if (window.matchMedia('(max-width:780px)').matches) {
      $('casca').classList.remove('menu-collapsed'); $('casca').classList.add('menu-open'); $('fundoMenu').hidden = false;
      $('conteudo').inert = true; document.querySelector('.topbar').inert = true;
      $('menuLateral').setAttribute('role', 'dialog'); $('menuLateral').setAttribute('aria-modal', 'true'); $('menuLateral').setAttribute('aria-label', 'Menu e filtros');
      $('recolherMenu').focus();
    } else { $('casca').classList.remove('menu-collapsed'); $('recolherMenu').focus(); }
    $('abrirMenu').setAttribute('aria-expanded', 'true');
  };
  $('recolherMenu').onclick = () => { if (window.matchMedia('(max-width:780px)').matches) closeMenu(); else { $('casca').classList.add('menu-collapsed'); $('abrirMenu').setAttribute('aria-expanded', 'false'); $('abrirMenu').focus(); } };
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
  $('abrirCalendario').onclick = () => { $('inicio').focus(); try { $('inicio').showPicker(); } catch (_) { /* o campo continua utilizável por teclado */ } };
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
  $('limpar').onclick = () => { state = M.novoEstado(); query = ''; selected = null; queryPage = tablePage = 0; $('fim').setCustomValidity(''); if (data) render(true); notify('Filtros limpos. Consulta de toda a base disponível.'); };
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-periodo],[data-mes],[data-grupo],[data-sub],[data-serie],[data-medida],[data-consulta],[data-detalhe],[data-paginar],[data-ordenar],[data-ver-todos],[data-exportar-lista],[data-exportar-item],[data-expandir-lista],[data-calendario],[data-dia],[data-mover-mes],[data-ultima-data],[data-kpi],[data-png]');
    if (!el || !data) return;
    const d = el.dataset;
    if (d.periodo) {
      const t = today(), month = t.slice(0, 7);
      const patch = d.periodo === 'hoje' ? { inicio: t, fim: t } : d.periodo === 'mes' ? { inicio: month + '-01', fim: M.monthEnd(month) } : d.periodo === 'ano' ? { inicio: t.slice(0, 4) + '-01-01', fim: t.slice(0, 4) + '-12-31' } : { inicio: '', fim: '' };
      setFilters(patch); notify(d.periodo === 'hoje' ? 'Consulta diária selecionada. A fonte mensal não fornece total por dia.' : 'Período aplicado aos indicadores.');
    }
    else if (d.mes) { monthFilter(d.mes); notify('Mês aplicado: ' + monthLabel(d.mes) + '.'); }
    else if (d.grupo) setFilters({ eixo: 'PROGRESSAO', grupo: state.grupo === d.grupo ? '' : d.grupo, subcategorias: [] });
    else if (d.sub) setFilters({ eixo: 'TEMPO_SERVICO', modalidade: '', grupo: '', subcategorias: state.subcategorias.includes(d.sub) ? state.subcategorias.filter(x => x !== d.sub) : [...state.subcategorias, d.sub] });
    else if (d.serie) setFilters(d.serie === 'TEMPO_SERVICO' ? { eixo: 'TEMPO_SERVICO', modalidade: '', grupo: '' } : { eixo: 'PROGRESSAO', modalidade: d.serie, subcategorias: [] });
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
    else if (d.dia) { selectedDay = d.dia; if (location.hash === '#dia') { setFilters({ inicio: selectedDay, fim: selectedDay }); } else location.hash = 'dia'; }
    else if (d.moverMes) { const [y, m] = calendarMonth.split('-').map(Number); const date = new Date(Date.UTC(y, m - 1 + Number(d.moverMes), 1, 12)); if (date.getUTCFullYear() >= 2026 && date.getUTCFullYear() <= 2099) { calendarMonth = date.toISOString().slice(0, 7); render(); } }
    else if (Object.hasOwn(d, 'ultimaData') && data.cobertura.ultima_publicacao) { selectedDay = data.cobertura.ultima_publicacao; setFilters({ inicio: selectedDay, fim: selectedDay }); }
    else if (d.kpi) { const entry = kpis.find(x => x[0] === d.kpi); showDialog(entry[1], '<p>' + esc(entry[2]) + '</p><p>' + (d.kpi === 'decisoes' ? 'Contagem do recorte: <b>' + esc(M.metricLabel(M.decisionMetric(data, state, visible))) + '</b>. O total geral e os agregados publicáveis têm escopos diferentes; células pequenas ficam preservadas.' : 'Este indicador não pode ser calculado a partir dos agregados disponíveis. — significa “Não verificado / não divulgado”, nunca zero presumido.') + '</p><p class="data-note">Período e filtros: ' + esc(describeFilters()) + '</p>'); }
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
    searchTimer = setTimeout(() => { const focused = document.activeElement?.id === 'buscaLista'; const selectionStart = $('buscaLista')?.selectionStart; const wrapper = $('buscaLista')?.closest('.panel'); if (!wrapper) return; wrapper.outerHTML = queryPanel(); if (focused) { $('buscaLista').focus({ preventScroll: true }); try { $('buscaLista').setSelectionRange(selectionStart, selectionStart); } catch (_) { /* campo de busca */ } } }, 180);
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
      titulo: 'Painel Diário Oficial | GEDIV',
      metadados: [...exportRows().slice(1, 6),
        ['Recorte', M.selectionIssue(state) || 'Agregados publicáveis parciais. Nenhum dado individual.'],
        ['Indicadores', 'Processos, resenhas, deferidos, indeferidos, refeitos e tornados sem efeito: não verificado / não divulgado.'],
        ['Decisões (faixa)', M.metricLabel(M.decisionMetric(data, state, visible))]],
      cabecalho: table[0], linhas: table.slice(1)
    });
  };
  $('imprimir').onclick = () => { if (data) { buildPrint(); window.print(); } };
  window.addEventListener('beforeprint', buildPrint);
  window.addEventListener('hashchange', () => route());
  window.addEventListener('resize', () => { if (!window.matchMedia('(max-width:780px)').matches) closeMenu(false); });
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
      $('estado').innerHTML = '<span aria-hidden="true">i</span><div><b>Dados reais · prévia pública em conferência</b><p>Contagens em faixas para preservar pessoas. Resultados ainda sujeitos à conferência administrativa. Agregados pequenos e registros individuais não são divulgados.</p></div>';
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
      $('exportarCsv').disabled = $('exportarXlsx').disabled = $('exportarPdf').disabled = $('imprimir').disabled = true;
      $('pagina').setAttribute('aria-busy', 'false'); buildPrint();
    } finally { clearTimeout(timeout); loading = false; $('atualizar').disabled = false; }
  }
  $('atualizar').onclick = () => load(true);
  $('tentarNovamente').onclick = () => load(true);
  route(true); cards(); load();
})(typeof window !== 'undefined' ? window : globalThis);
