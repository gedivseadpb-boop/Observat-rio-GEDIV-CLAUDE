/* Contrato da consulta pública. Não recebe nem deriva registros individuais. */
(function (root) {
  'use strict';
  const EIXOS = { PROGRESSAO: 'Progressão Funcional', TEMPO_SERVICO: 'Tempo de Serviço' };
  const MODALIDADES = { HORIZONTAL: 'Horizontal', VERTICAL: 'Vertical' };
  const CAMPOS = ['inicio', 'fim', 'eixo', 'modalidade', 'grupo', 'situacao', 'resultado', 'tipo', 'coberturaFiltro'];
  const vazio = () => ({ valor: null, minimo: null, maximo: null, rotulo: '—', protegido: true });
  const zero = () => ({ valor: 0, minimo: 0, maximo: 0, rotulo: '0', protegido: false });
  const novoEstado = () => ({ ...Object.fromEntries(CAMPOS.map(k => [k, ''])), subcategorias: [] });
  function numberBounds(m) {
    if (!m || typeof m !== 'object') return null;
    if (Number.isFinite(m.minimo) && Number.isFinite(m.maximo) && m.minimo >= 0 && m.maximo >= m.minimo) return { min: m.minimo, max: m.maximo };
    return null;
  }
  const metricLabel = m => numberBounds(m) ? (m.rotulo || '—') : '—';
  function sumMetrics(metrics, allowZero = false) {
    if (!metrics.length) return allowZero ? zero() : vazio();
    const b = metrics.map(numberBounds);
    if (b.some(x => !x)) return vazio();
    const min = b.reduce((a, x) => a + x.min, 0), max = b.reduce((a, x) => a + x.max, 0);
    return { valor: min === max ? min : null, minimo: min, maximo: max, rotulo: min === max ? String(min) : min + '–' + max, protegido: min !== max };
  }
  function validDate(s) {
    if (!/^20\d\d-\d\d-\d\d$/.test(s || '')) return false;
    const d = new Date(s + 'T12:00:00Z');
    return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s;
  }
  function monthEnd(p) {
    const [y, m] = p.split('-').map(Number);
    return new Date(Date.UTC(y, m, 0, 12)).toISOString().slice(0, 10);
  }
  function selectionIssue(s) {
    if ((s.inicio && !validDate(s.inicio)) || (s.fim && !validDate(s.fim))) return 'Confira as datas informadas.';
    if (s.inicio && s.fim && s.inicio > s.fim) return 'A data final deve ser igual ou posterior à data inicial.';
    if ((s.inicio && !s.inicio.endsWith('-01')) || (s.fim && s.fim !== monthEnd(s.fim.slice(0, 7)))) return 'Este recorte exige dados diários. A projeção disponível é mensal; escolha meses completos ou consulte a cobertura do dia. Nenhum total mensal foi atribuído ao dia.';
    if (s.resultado) return 'A projeção pública não discrimina deferimentos, indeferimentos ou outros resultados. Este filtro não pode ser calculado com os dados disponíveis.';
    if (s.tipo && s.tipo !== 'ORIGINAL') return 'Os agregados de decisões disponíveis abrangem publicações originais. As alterações e outras naturezas ainda não foram disponibilizadas nesta projeção.';
    if (s.coberturaFiltro) return 'A cobertura por edição e por situação ainda não foi disponibilizada. Os números gerais de documentos não permitem calcular este recorte.';
    if (s.situacao === 'pendente') return 'Pendências e não verificados não são decisões publicáveis. Consulte a área Pendências para ver a situação disponível.';
    return '';
  }
  function filterCells(cells, s) {
    if (selectionIssue(s)) return [];
    const subs = s.subcategorias || (s.subcategoria ? [s.subcategoria] : []);
    return cells.filter(c => (!s.inicio || c.periodo >= s.inicio.slice(0, 7)) && (!s.fim || c.periodo <= s.fim.slice(0, 7))
      && (!s.eixo || c.eixo === s.eixo) && (!s.modalidade || c.modalidade === s.modalidade)
      && (!s.grupo || (s.grupo === 'NAO_INFORMADO' ? c.grupo === null : c.grupo === s.grupo))
      && (!subs.length || subs.includes(c.subcategoria)) && (!s.situacao || c.situacao === s.situacao));
  }
  function summaryFor(data, s) {
    if (selectionIssue(s) || s.inicio || s.fim || s.modalidade || s.grupo || s.subcategorias?.length) return null;
    return s.eixo ? data.resumo_eixos[s.eixo] || null : data.resumo;
  }
  function decisionMetric(data, s, cells) {
    if (selectionIssue(s)) return vazio();
    const summary = summaryFor(data, s);
    if (summary) {
      if (s.situacao === 'conferido') return summary.conferidos;
      if (s.situacao === 'provisorio') return summary.provisorios;
      return sumMetrics([summary.conferidos, summary.provisorios]);
    }
    const noConfirmed = numberBounds(data.resumo.conferidos)?.max === 0;
    return sumMetrics(cells.map(c => c.decisoes), s.situacao === 'conferido' && noConfirmed);
  }
  function qualityMetric(data, s, cells, key) {
    if (selectionIssue(s)) return vazio();
    if ((s.situacao || s.tipo) && ['atos', 'publicacoes_pendentes'].includes(key)) return vazio();
    if (s.situacao && ((key === 'conferidos' && s.situacao !== 'conferido') || (key === 'provisorios' && s.situacao !== 'provisorio'))) return vazio();
    const summary = summaryFor(data, s);
    if (summary) return summary[key];
    if (key === 'conferidos' || key === 'provisorios') return sumMetrics(cells.filter(c => c.situacao === (key === 'conferidos' ? 'conferido' : 'provisorio')).map(c => c.decisoes), key === 'conferidos' && numberBounds(data.resumo.conferidos)?.max === 0);
    // Um ato pode estar em mais de uma célula. Nunca somar células como atos distintos.
    return vazio();
  }
  function shareInterval(metric, metrics) {
    const b = numberBounds(metric), rest = metrics.filter(x => x !== metric).map(numberBounds);
    if (!b || rest.some(x => !x) || b.max === 0) return null;
    const minRest = rest.reduce((n, x) => n + x.min, 0), maxRest = rest.reduce((n, x) => n + x.max, 0);
    if (b.min + maxRest <= 0 || b.max + minRest <= 0) return null;
    return { min: Math.floor(100 * b.min / (b.min + maxRest)), max: Math.ceil(100 * b.max / (b.max + minRest)) };
  }
  const shareLabel = p => p ? (p.min === p.max ? p.min + '%' : p.min + '–' + p.max + '%') : '—';
  function csvValue(v) { const t = String(v ?? ''); return '"' + (/^[=+@\-\t\r]/.test(t) ? "'" + t : t).replace(/"/g, '""') + '"'; }
  function cellsToRows(cells, catalogo) {
    const name = (list, code) => (list || []).find(x => x.codigo === code)?.nome || code || 'Não informado';
    const rows = [['Mês de publicação', 'Eixo', 'Modalidade', 'Grupo PCCR', 'Assunto TS', 'Situação', 'Atos na célula (faixa, não somar)', 'Decisões (faixa)', 'Escopo']];
    cells.forEach(c => rows.push([c.periodo, EIXOS[c.eixo], MODALIDADES[c.modalidade] || '', c.eixo === 'PROGRESSAO' ? name(catalogo.grupos, c.grupo) : '', c.eixo === 'TEMPO_SERVICO' ? name(catalogo.subcategorias, c.subcategoria) : '', c.situacao === 'conferido' ? 'Conferido' : 'Provisório', metricLabel(c.atos), metricLabel(c.decisoes), 'Agregados publicáveis parciais; faixas, sem contagens individuais']));
    return rows;
  }
  function cellsToCsv(cells, catalogo) { return '\ufeff' + cellsToRows(cells, catalogo).map(r => r.map(csvValue).join(';')).join('\r\n'); }
  function searchCells(cells, text, catalogo) {
    const normal = v => String(v).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const q = normal(text).trim();
    return !q ? [...cells] : cells.filter(c => normal([c.periodo, EIXOS[c.eixo], MODALIDADES[c.modalidade], c.grupo || 'Não informado', c.subcategoria, c.situacao, catalogo.grupos.find(g => g.codigo === c.grupo)?.nome, catalogo.subcategorias.find(x => x.codigo === c.subcategoria)?.nome].join(' ')).includes(q));
  }
  function sortCells(cells, key = 'periodo', direction = -1) {
    return [...cells].sort((a, b) => {
      if (key === 'decisoes' || key === 'atos') return direction * ((numberBounds(a[key])?.min ?? -1) - (numberBounds(b[key])?.min ?? -1));
      if (key === 'categoria') return direction * String(a.subcategoria || a.grupo || '').localeCompare(String(b.subcategoria || b.grupo || ''), 'pt-BR', { numeric: true });
      return direction * String(a[key] ?? '').localeCompare(String(b[key] ?? ''), 'pt-BR', { numeric: true });
    });
  }
  function pagination(items, page, size) {
    const count = Math.max(1, Math.ceil(items.length / size)), current = Math.max(0, Math.min(count - 1, page));
    return { items: items.slice(current * size, (current + 1) * size), page: current, pages: count, total: items.length };
  }
  function validateProjection(d) {
    const fail = () => { throw new Error('A projeção não corresponde ao contrato público protegido. Os dados não foram exibidos.'); };
    const keys = (o, expected) => o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).sort().join('|') === [...expected].sort().join('|');
    const metric = m => {
      if (!keys(m, ['valor', 'minimo', 'maximo', 'rotulo', 'protegido'])) return false;
      if (m.valor === 0 && m.minimo === 0 && m.maximo === 0 && m.rotulo === '0' && m.protegido === false) return true;
      return m.valor === null && Number.isInteger(m.minimo) && m.minimo >= 0 && m.minimo % 5 === 0 && m.maximo === m.minimo + 4 && m.rotulo === m.minimo + '–' + m.maximo && m.protegido === true;
    };
    if (!keys(d, ['schema_version', 'atualizado_em', 'origem', 'experimental', 'versao_regras', 'catalogo', 'cobertura', 'privacidade', 'resumo', 'resumo_eixos', 'celulas'])) fail();
    if (d.schema_version !== 1 || d.origem !== 'dados_reais' || d.experimental !== true || !/^gediv-\d{4}\.\d{2}\.\d{2}-\d+$/.test(d.versao_regras) || !Number.isFinite(Date.parse(d.atualizado_em))) fail();
    if (!keys(d.catalogo, ['grupos', 'subcategorias']) || !Array.isArray(d.catalogo.grupos) || !Array.isArray(d.catalogo.subcategorias)) fail();
    const expectedGroups = ['MAG', 'SSA', 'GAJ', 'FAP', 'AST', 'ANS', 'ESP', 'DPS', 'SFT', 'OSPB', 'GPC', 'SEI', 'SAT', 'ACI', 'PPGG', 'INT'];
    const checkList = (list, codes) => list.length === codes.length && list.every((x, i) => keys(x, ['codigo', 'nome']) && x.codigo === codes[i] && typeof x.nome === 'string' && x.nome.length < 150);
    if (!checkList(d.catalogo.grupos, expectedGroups) || !checkList(d.catalogo.subcategorias, Array.from({ length: 7 }, (_, i) => 'TS-0' + (i + 1)))) fail();
    if (!keys(d.cobertura, ['inicio_historico', 'primeira_publicacao', 'ultima_publicacao', 'edicoes', 'paginas', 'ausencia_tecnica_edicoes', 'inconclusivas', 'historico_completo', 'observacao'])) fail();
    const c = d.cobertura;
    if (c.inicio_historico !== '2026-01-01' || c.historico_completo !== false || ['edicoes', 'paginas', 'ausencia_tecnica_edicoes', 'inconclusivas'].some(k => !Number.isInteger(c[k]) || c[k] < 0) || ['primeira_publicacao', 'ultima_publicacao'].some(k => c[k] !== null && !validDate(c[k]))) fail();
    const resumoKeys = ['conferidos', 'provisorios', 'atos', 'publicacoes_pendentes'];
    const summary = s => keys(s, resumoKeys) && Object.values(s).every(metric);
    if (!summary(d.resumo) || !d.resumo_eixos || Object.entries(d.resumo_eixos).some(([k, v]) => !EIXOS[k] || !summary(v))) fail();
    if (!keys(d.privacidade, ['limiar', 'faixa', 'cobertura_parcial', 'observacao']) || d.privacidade.limiar !== 5 || d.privacidade.faixa !== 5 || d.privacidade.cobertura_parcial !== true || !Array.isArray(d.celulas)) fail();
    const seen = new Set();
    d.celulas.forEach(x => {
      if (!keys(x, ['periodo', 'eixo', 'modalidade', 'grupo', 'subcategoria', 'situacao', 'atos', 'decisoes']) || !/^20\d\d-(0[1-9]|1[0-2])$/.test(x.periodo) || !EIXOS[x.eixo] || !['conferido', 'provisorio'].includes(x.situacao) || !metric(x.atos) || !metric(x.decisoes) || x.decisoes.minimo < 5) fail();
      if (x.eixo === 'PROGRESSAO' ? (x.subcategoria !== null || (x.modalidade !== null && !MODALIDADES[x.modalidade]) || (x.grupo !== null && !expectedGroups.includes(x.grupo))) : (x.modalidade !== null || x.grupo !== null || (x.subcategoria !== null && !d.catalogo.subcategorias.some(s => s.codigo === x.subcategoria)))) fail();
      const key = JSON.stringify([x.periodo, x.eixo, x.modalidade, x.grupo, x.subcategoria, x.situacao]);
      if (seen.has(key)) fail();
      seen.add(key);
    });
    return d;
  }
  const api = { EIXOS, MODALIDADES, CAMPOS, novoEstado, vazio, zero, numberBounds, metricLabel, sumMetrics, validDate, monthEnd, selectionIssue, filterCells, summaryFor, decisionMetric, qualityMetric, shareInterval, shareLabel, csvValue, cellsToRows, cellsToCsv, searchCells, sortCells, pagination, validateProjection };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.GedivModelo = api;
})(typeof window !== 'undefined' ? window : globalThis);
