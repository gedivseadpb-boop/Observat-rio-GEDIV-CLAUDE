/* Gráficos SVG acessíveis para contagens em FAIXAS (mínimo–máximo).
   A parte sólida vai até o mínimo garantido; a parte clara mostra a incerteza até o máximo da faixa.
   Nenhum valor exato é inventado: o rótulo é sempre a faixa publicada. */
(function (raiz) {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  function el(nome, atributos = {}, filhos = []) {
    const e = document.createElementNS(NS, nome);
    Object.entries(atributos).forEach(([k, v]) => e.setAttribute(k, String(v)));
    filhos.forEach(f => e.appendChild(typeof f === 'string' ? document.createTextNode(f) : f));
    return e;
  }
  const rotuloFaixa = (min, max) => (min === max ? String(min) : min + '–' + max);

  /* itens: [{rotulo, min, max, cor, estado: 'ok'|'sem-dado', nota, valor}] — 'sem-dado' não desenha barra. */
  function barrasFaixa(itens, { titulo, descricao, aoClicar } = {}) {
    const largura = 520, alturaLinha = 40, margemRotulo = 170, margemValor = 96;
    const altura = Math.max(1, itens.length) * alturaLinha + 12;
    const maximo = Math.max(1, ...itens.filter(i => i.estado === 'ok').map(i => i.max));
    const util = largura - margemRotulo - margemValor;
    const svg = el('svg', { viewBox: `0 0 ${largura} ${altura}`, width: largura, role: 'img', class: 'grafico', 'aria-labelledby': '' });
    const idTitulo = 'g' + Math.random().toString(36).slice(2, 9);
    svg.setAttribute('aria-labelledby', idTitulo);
    svg.appendChild(el('title', { id: idTitulo }, [titulo + (descricao ? '. ' + descricao : '')]));
    itens.forEach((item, i) => {
      const y = 6 + i * alturaLinha;
      const grupo = el('g', { class: 'linha-grafico' + (aoClicar && item.estado === 'ok' ? ' clicavel' : '') });
      grupo.appendChild(el('text', { x: margemRotulo - 10, y: y + 22, 'text-anchor': 'end', class: 'rotulo-eixo' }, [item.rotulo]));
      if (item.estado === 'ok') {
        const wMin = util * item.min / maximo, wMax = util * item.max / maximo;
        grupo.appendChild(el('rect', { x: margemRotulo, y: y + 6, width: Math.max(wMax, 2), height: 22, rx: 4, class: 'barra-incerteza', style: `--cor:${item.cor}` }));
        grupo.appendChild(el('rect', { x: margemRotulo, y: y + 6, width: Math.max(wMin, 2), height: 22, rx: 4, class: 'barra-solida', style: `--cor:${item.cor}` }));
        grupo.appendChild(el('text', { x: margemRotulo + Math.max(wMax, 2) + 8, y: y + 22, class: 'rotulo-valor' }, [rotuloFaixa(item.min, item.max)]));
        grupo.appendChild(el('title', {}, [`${item.rotulo}: ${rotuloFaixa(item.min, item.max)}${item.nota ? ' — ' + item.nota : ''}`]));
        if (aoClicar) {
          grupo.setAttribute('tabindex', '0');
          grupo.setAttribute('role', 'button');
          grupo.setAttribute('aria-label', `${item.rotulo}: ${rotuloFaixa(item.min, item.max)}. Filtrar por este item`);
          grupo.addEventListener('click', () => aoClicar(item));
          grupo.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); aoClicar(item); } });
        }
      } else {
        grupo.appendChild(el('text', { x: margemRotulo, y: y + 22, class: 'rotulo-sem-dado' }, [item.nota || 'Sem agregado publicável']));
      }
      svg.appendChild(grupo);
    });
    return svg;
  }

  /* meses: ['2026-10', ...]; series: [{nome, cor, porMes: {'2026-10': {min,max}|null}}] */
  function colunasMensais(meses, series, { titulo, rotuloMes } = {}) {
    const largura = 520, altura = 280, base = 230, topo = 28, esquerda = 44;
    const util = largura - esquerda - 16;
    const maximo = Math.max(1, ...series.flatMap(s => meses.map(m => s.porMes[m]?.max || 0)));
    const svg = el('svg', { viewBox: `0 0 ${largura} ${altura}`, width: largura, role: 'img', class: 'grafico' });
    const idTitulo = 'g' + Math.random().toString(36).slice(2, 9);
    svg.setAttribute('aria-labelledby', idTitulo);
    svg.appendChild(el('title', { id: idTitulo }, [titulo || 'Evolução mensal']));
    [0, 0.5, 1].forEach(f => {
      const y = base - (base - topo) * f;
      svg.appendChild(el('line', { x1: esquerda, x2: largura - 8, y1: y, y2: y, class: 'grade' }));
      svg.appendChild(el('text', { x: esquerda - 8, y: y + 4, 'text-anchor': 'end', class: 'rotulo-eixo pequeno' }, [String(Math.round(maximo * f))]));
    });
    const larguraMes = util / Math.max(1, meses.length);
    const larguraBarra = Math.min(54, (larguraMes - 24) / Math.max(1, series.length));
    meses.forEach((m, i) => {
      const x0 = esquerda + i * larguraMes + (larguraMes - larguraBarra * series.length) / 2;
      series.forEach((s, j) => {
        const v = s.porMes[m];
        const x = x0 + j * larguraBarra;
        if (!v) {
          svg.appendChild(el('text', { x: x + larguraBarra / 2, y: base - 6, 'text-anchor': 'middle', class: 'rotulo-sem-dado pequeno' }, ['—']));
          return;
        }
        const hMax = (base - topo) * v.max / maximo, hMin = (base - topo) * v.min / maximo;
        const g = el('g', {});
        g.appendChild(el('rect', { x: x + 3, y: base - hMax, width: larguraBarra - 6, height: hMax, rx: 3, class: 'barra-incerteza', style: `--cor:${s.cor}` }));
        g.appendChild(el('rect', { x: x + 3, y: base - hMin, width: larguraBarra - 6, height: hMin, rx: 3, class: 'barra-solida', style: `--cor:${s.cor}` }));
        g.appendChild(el('text', { x: x + larguraBarra / 2, y: base - hMax - 6, 'text-anchor': 'middle', class: 'rotulo-valor pequeno' }, [rotuloFaixa(v.min, v.max)]));
        g.appendChild(el('title', {}, [`${s.nome}, ${rotuloMes ? rotuloMes(m) : m}: ${rotuloFaixa(v.min, v.max)}`]));
        svg.appendChild(g);
      });
      svg.appendChild(el('text', { x: esquerda + i * larguraMes + larguraMes / 2, y: base + 22, 'text-anchor': 'middle', class: 'rotulo-eixo' }, [rotuloMes ? rotuloMes(m) : m]));
    });
    svg.appendChild(el('line', { x1: esquerda, x2: largura - 8, y1: base, y2: base, class: 'eixo' }));
    return svg;
  }

  const api = { barrasFaixa, colunasMensais, rotuloFaixa };
  raiz.GedivGraficos = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
