/* Painel Diário Oficial | GEDIV — dashboard.
   Toda contagem vem da API (/api/painel): cartões, gráficos, tabela e exportações usam a mesma projeção.
   Sem bibliotecas externas e sem estilos embutidos (compatível com a política de segurança do servidor). */
(function () {
  'use strict';
  const $ = s => document.querySelector(s), $$ = s => Array.from(document.querySelectorAll(s));
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const dataBR = d => d ? d.split('-').reverse().join('/') : 'data não informada';
  const POR_PAGINA = 12;
  const NOMES = {
    eixo: { PROGRESSAO: 'Progressão Funcional', TEMPO_SERVICO: 'Tempo de Serviço' },
    modalidade: { HORIZONTAL: 'Horizontal', VERTICAL: 'Vertical' },
    resultado: { DEFERIDO: 'Deferido', INDEFERIDO: 'Indeferido', NAO_INFORMADO: 'Não informado' },
    condicao: { PLENA: 'Plena', CONDICIONAL: 'Condicional', NAO_INFORMADA: 'Não informada' },
    alteracao: { RETIFICACAO: 'Retificação', CORRECAO: 'Correção', REPUBLICACAO: 'Republicação', TORNADO_SEM_EFEITO: 'Tornado sem efeito' },
    estado: { PENDENTE_VINCULACAO: 'Pendente de vinculação', SUGERIDO: 'Vínculo sugerido (a validar)', VALIDADO: 'Vínculo validado', REJEITADO: 'Rejeitado' },
    cartao: { processos: 'Total de processos', resenhas: 'Total de resenhas', decisoes: 'Total de decisões individuais', deferidos: 'Deferidos', indeferidos: 'Indeferidos', refeitos: 'Refeitos', sem_efeito: 'Tornados sem efeito' }
  };
  const AJUDA = {
    processos: 'Processos distintos · data da publicação original', resenhas: 'Resenhas originais distintas', decisoes: 'Decisões individuais originais',
    deferidos: 'Decisões com resultado deferido', indeferidos: 'Decisões com resultado indeferido',
    refeitos: 'Atos com retificação, correção ou republicação validada · data do evento', sem_efeito: 'Atos tornados sem efeito, com vínculo validado · data do evento'
  };
  const VISOES = {
    geral: {}, progressao: { eixo: 'PROGRESSAO' }, tempo: { eixo: 'TEMPO_SERVICO' }, dia: {}, historico: {}, alteracoes: {}, outras: {}
  };

  const S = { visao: 'geral', escopo: 'conferido', inicio: '', fim: '', eixo: '', modalidade: '', condicao: '', grupo: [], subcategoria: [], resultado: '', vinculo: '', busca: '', cartao: '',
    modo: 'resenha', pagina: 0, selecionado: null, tipoOutras: '' };
  let token = '', catalogo = null, P = null, outras = [];
  try { token = sessionStorage.getItem('gediv_token') || ''; } catch (e) { /* armazenamento indisponível */ }

  async function api(caminho, opcoes = {}) {
    const cab = Object.assign({}, opcoes.headers || {});
    if (token) cab.Authorization = 'Bearer ' + token;
    const r = await fetch(caminho, Object.assign({}, opcoes, { headers: cab, cache: 'no-store' }));
    if (!r.ok) {
      let msg = 'Falha ' + r.status;
      try { msg = (await r.json()).erro || msg; } catch (e) { /* sem corpo */ }
      const erro = new Error(msg); erro.status = r.status; throw erro;
    }
    return r;
  }

  function consulta() {
    const q = new URLSearchParams();
    for (const k of ['escopo', 'inicio', 'fim', 'eixo', 'modalidade', 'condicao', 'resultado', 'vinculo', 'busca', 'cartao']) if (S[k]) q.set(k, S[k]);
    if (S.grupo.length) q.set('grupo', S.grupo.join(','));
    if (S.subcategoria.length) q.set('subcategoria', S.subcategoria.join(','));
    return q.toString();
  }

  async function carregar() {
    $('#btnAtualizar').disabled = true;
    try {
      if (!catalogo) { catalogo = await (await api('/api/catalogo')).json(); montarFiltros(); }
      P = await (await api('/api/painel?' + consulta())).json();
      document.body.classList.toggle('gerencia', P.meta.dados_individuais);
      if (S.visao === 'dia' && !S.inicio && P.meta.cobertura.ultima_data) {
        S.inicio = S.fim = P.meta.cobertura.ultima_data; $('#fInicio').value = $('#fFim').value = S.inicio; return carregar();
      }
      if (S.visao === 'outras') outras = (await (await api('/api/outras')).json()).itens;
      desenhar();
    } catch (e) {
      if (e.status === 403 || e.status === 401) { sair(false); return carregar(); }
      aviso('Não foi possível carregar os dados: ' + e.message, 'erro');
    } finally { $('#btnAtualizar').disabled = false; }
  }

  function aviso(texto, classe) { const a = $('#aviso'); a.textContent = texto; a.className = 'aviso ' + (classe || ''); }

  function montarFiltros() {
    $('#fGrupos').innerHTML = catalogo.grupos.map(g => `<label><input type="checkbox" value="${esc(g.codigo)}"> <span>${esc(g.codigo)} · ${esc(g.nome)}${g.estado === 'CONFIRMADA' ? '' : ' <em>(a confirmar em publicação)</em>'}</span></label>`).join('')
      + '<label><input type="checkbox" value="NAO_INFORMADO"> <span>Grupo não informado</span></label>';
    $('#fSubs').innerHTML = catalogo.subcategorias.map(s => `<label><input type="checkbox" value="${esc(s.codigo)}"> <span>${esc(s.nome)}</span></label>`).join('');
    $$('#fGrupos input').forEach(i => i.addEventListener('change', () => { S.grupo = $$('#fGrupos input:checked').map(x => x.value); mudou(); }));
    $$('#fSubs input').forEach(i => i.addEventListener('change', () => { S.subcategoria = $$('#fSubs input:checked').map(x => x.value); mudou(); }));
  }

  function sincronizarControles() {
    $('#fInicio').value = S.inicio; $('#fFim').value = S.fim; $('#fEixo').value = S.eixo; $('#fModalidade').value = S.modalidade;
    $('#fCondicao').value = S.condicao; $('#fResultado').value = S.resultado; $('#fVinculo').value = S.vinculo; $('#fBusca').value = S.busca; $('#fEscopo').value = S.escopo;
    $$('#fGrupos input').forEach(i => { i.checked = S.grupo.includes(i.value); });
    $$('#fSubs input').forEach(i => { i.checked = S.subcategoria.includes(i.value); });
    $('#blocoProgressao').classList.toggle('inativo', S.eixo === 'TEMPO_SERVICO');
    $('#blocoTempo').classList.toggle('inativo', S.eixo === 'PROGRESSAO');
    $$('#abas button').forEach(b => b.classList.toggle('ativa', b.dataset.visao === S.visao));
  }

  function mudou() { S.pagina = 0; S.selecionado = null; carregar(); }

  function nomeGrupo(c) { const g = catalogo.grupos.find(x => x.codigo === c); return g ? g.codigo + ' · ' + g.nome : 'Grupo não informado'; }
  function nomeSub(c) { const s = catalogo.subcategorias.find(x => x.codigo === c); return s ? s.nome : ''; }
  function assunto(l) {
    if (l.eixo === 'TEMPO_SERVICO') return 'Tempo de Serviço · ' + nomeSub(l.subcategoria);
    return 'Progressão ' + (NOMES.modalidade[l.modalidade] || '(modalidade não informada)') + ' · ' + (l.grupo ? nomeGrupo(l.grupo) : 'grupo não informado');
  }
  function classeAssunto(l) { return l.eixo === 'TEMPO_SERVICO' ? 'tempo' : l.modalidade === 'VERTICAL' ? 'vertical' : l.modalidade === 'HORIZONTAL' ? 'horizontal' : ''; }

  /* ---------- desenho ---------- */
  function desenhar() {
    sincronizarControles();
    const m = P.meta, cob = m.cobertura;
    $('#situacaoTitulo').textContent = m.dados_individuais ? 'Gerência · ' + m.rotulo : 'Consulta pública · agregados conferidos';
    $('#situacaoDetalhe').textContent = cob.edicoes_no_acervo ? `${cob.edicoes_no_acervo} edição(ões) · ${dataBR(cob.primeira_data)} a ${dataBR(cob.ultima_data)}` : 'Nenhuma edição carregada';
    $('#btnAcesso').textContent = m.dados_individuais ? 'Gerência (sair)' : 'Acesso da gerência';
    $('#rodape').textContent = `${cob.parecer} Regras ${m.versao_regras}.`;
    const pend = P.apoio.decisoes_pendentes;
    if (m.preliminar) aviso('Dados PRELIMINARES, em conferência: ainda não foram homologados pela GEDIV e não devem ser divulgados como resultado oficial.', 'preliminar');
    else if (!P.apoio.decisoes_conferidas) aviso(`Nenhuma decisão conferida até agora${pend ? ` — há ${pend} candidata(s) aguardando revisão humana` : ''}. Os indicadores só contam registros conferidos.`, 'preliminar');
    else aviso(`Indicadores calculados somente com decisões conferidas (${P.apoio.decisoes_conferidas}). ${pend ? pend + ' candidata(s) ainda aguardam revisão e não estão contadas.' : ''}`);
    $('#visaoPainel').hidden = S.visao === 'outras'; $('#visaoOutras').hidden = S.visao !== 'outras';
    $('#cartaoGrupos').hidden = S.eixo === 'TEMPO_SERVICO'; $('#cartaoSubs').hidden = S.eixo === 'PROGRESSAO';
    filtrosAtivos();
    if (S.visao === 'outras') return desenharOutras();
    cartoes(); apoio(); evolucao(); porAssunto(); porGrupo(); porSubcategoria(); cobertura(); tabela(); detalhes();
  }

  function filtrosAtivos() {
    const itens = [];
    const add = (rotulo, limpar) => itens.push({ rotulo, limpar });
    if (S.inicio || S.fim) add(`Período: ${S.inicio ? dataBR(S.inicio) : '…'} a ${S.fim ? dataBR(S.fim) : '…'}`, () => { S.inicio = S.fim = ''; });
    if (S.eixo) add('Eixo: ' + NOMES.eixo[S.eixo], () => { S.eixo = ''; });
    if (S.modalidade) add('Modalidade: ' + NOMES.modalidade[S.modalidade], () => { S.modalidade = ''; });
    if (S.condicao) add('Condição: ' + NOMES.condicao[S.condicao], () => { S.condicao = ''; });
    S.grupo.forEach(g => add('Grupo: ' + (g === 'NAO_INFORMADO' ? 'não informado' : g), () => { S.grupo = S.grupo.filter(x => x !== g); }));
    S.subcategoria.forEach(s => add(nomeSub(s), () => { S.subcategoria = S.subcategoria.filter(x => x !== s); }));
    if (S.resultado) add('Resultado: ' + NOMES.resultado[S.resultado], () => { S.resultado = ''; });
    if (S.vinculo) add('Vínculo: ' + (S.vinculo === 'EXPRESSO' ? 'expresso' : 'não expresso'), () => { S.vinculo = ''; });
    if (S.busca) add('Busca: ' + S.busca, () => { S.busca = ''; });
    if (S.cartao) add('Indicador: ' + NOMES.cartao[S.cartao], () => { S.cartao = ''; });
    const caixa = $('#ativos'); caixa.innerHTML = '';
    itens.forEach(i => { const b = document.createElement('button'); b.type = 'button'; b.textContent = i.rotulo + '  ✕'; b.title = 'Remover este filtro'; b.onclick = () => { i.limpar(); mudou(); }; caixa.appendChild(b); });
  }

  function cartoes() {
    const caixa = $('#cartoes'); caixa.innerHTML = '';
    Object.keys(NOMES.cartao).forEach(c => {
      const v = P.indicadores[c], b = document.createElement('button');
      b.type = 'button'; b.className = 'kpi' + (S.cartao === c ? ' selecionado' : '') + (c === 'deferidos' ? ' bom' : c === 'indeferidos' ? ' critico' : '');
      b.setAttribute('aria-pressed', S.cartao === c);
      const marca = c === 'deferidos' ? '<i class="marca-estado">✓ deferido</i>' : c === 'indeferidos' ? '<i class="marca-estado">✕ indeferido</i>' : '';
      b.innerHTML = `<span>${esc(NOMES.cartao[c])}</span><b>${v === null ? '—' : v.toLocaleString('pt-BR')}</b>${marca}<small>${esc(v === null ? 'Não calculado em dados preliminares' : AJUDA[c])}</small>`;
      b.title = (S.cartao === c ? 'Clique para desfazer a seleção. ' : 'Clique para ver somente este universo. ') + AJUDA[c];
      b.onclick = () => { S.cartao = S.cartao === c ? '' : c; mudou(); };
      caixa.appendChild(b);
    });
  }

  function apoio() {
    const a = P.apoio, itens = [
      ['Eventos de alteração validados', a.eventos_de_alteracao === null ? '—' : a.eventos_de_alteracao, false],
      ['Eventos sem vínculo validado', a.eventos_sem_vinculo, a.eventos_sem_vinculo > 0],
      ['Decisões aguardando revisão', a.decisoes_pendentes, a.decisoes_pendentes > 0],
      ['Pendentes sem GEDIV expressa', a.vinculo_nao_expresso_pendente, a.vinculo_nao_expresso_pendente > 0],
      ['Conferidas', a.decisoes_conferidas, false], ['Rejeitadas', a.decisoes_rejeitadas, false]];
    $('#apoio').innerHTML = itens.map(([r, v, at]) => `<div class="${at ? 'atencao' : ''}">${esc(r)}<b>${esc(v)}</b></div>`).join('');
  }

  function dica(el, texto) {
    el.addEventListener('mousemove', ev => { const d = $('#dica'); d.textContent = texto; d.hidden = false; d.style.left = Math.min(ev.clientX + 12, window.innerWidth - 290) + 'px'; d.style.top = (ev.clientY + 14) + 'px'; });
    el.addEventListener('mouseleave', () => { $('#dica').hidden = true; });
  }

  function evolucao() {
    const dados = P.series.por_data, caixa = $('#gEvolucao');
    if (!dados.length) { caixa.innerHTML = '<p class="vazio">Sem decisões neste recorte.</p>'; return; }
    const L = 720, A = 220, me = 34, mb = 30, mt = 10, largura = L - me - 8, altura = A - mb - mt;
    const max = Math.max(1, ...dados.map(d => d.total)), passo = largura / dados.length, lb = Math.max(4, Math.min(34, passo - 6));
    const cores = { vertical: '#2a78d6', horizontal: '#1baf7a', tempo: '#eb6834' }, ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', `0 0 ${L} ${A}`); svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Decisões por data de publicação');
    const el = (nome, at, texto) => { const e = document.createElementNS(ns, nome); for (const k in at) e.setAttribute(k, at[k]); if (texto != null) e.textContent = texto; svg.appendChild(e); return e; };
    const marcas = [...new Set([0, Math.ceil(max / 2), max])];
    marcas.forEach(v => { const y = mt + altura - (v / max) * altura; el('line', { x1: me, x2: L - 8, y1: y, y2: y, stroke: v ? '#e1e0d9' : '#c3c2b7', 'stroke-width': 1 }); el('text', { x: me - 6, y: y + 4, 'text-anchor': 'end' }, v); });
    const cadaRotulo = Math.ceil(dados.length / 10);
    dados.forEach((d, i) => {
      const x = me + i * passo + (passo - lb) / 2; let y = mt + altura;
      ['vertical', 'horizontal', 'tempo'].forEach(k => {
        if (!d[k]) return; const h = (d[k] / max) * altura; y -= h;
        el('rect', { x, y: y + 1, width: lb, height: Math.max(1, h - 2), rx: 2, fill: cores[k] });
      });
      const alvo = el('rect', { x: me + i * passo, y: mt, width: passo, height: altura, fill: 'transparent', tabindex: 0 });
      dica(alvo, `${dataBR(d.data)}\nVertical: ${d.vertical}\nHorizontal: ${d.horizontal}\nTempo de Serviço: ${d.tempo}\nTotal: ${d.total}`);
      alvo.addEventListener('click', () => { S.inicio = S.fim = d.data; mudou(); });
      if (i % cadaRotulo === 0) el('text', { x: me + i * passo + passo / 2, y: A - 10, 'text-anchor': 'middle' }, d.data ? d.data.slice(8) + '/' + d.data.slice(5, 7) : '—');
      if (dados.length <= 16) el('text', { x: me + i * passo + passo / 2, y: y - 3, 'text-anchor': 'middle' }, d.total);
    });
    caixa.innerHTML = ''; caixa.appendChild(svg);
  }

  function barras(caixa, linhas, max) {
    caixa.innerHTML = ''; caixa.className = 'barras';
    if (!linhas.length) { caixa.innerHTML = '<p class="vazio">Sem decisões neste recorte.</p>'; return; }
    linhas.forEach(l => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'barra-linha' + (l.selecionada ? ' selecionada' : '');
      b.innerHTML = `<span class="rotulo">${esc(l.rotulo)}${l.sub ? `<small>${esc(l.sub)}</small>` : ''}</span><span class="pista"></span><span class="valor"></span>`;
      const pista = b.querySelector('.pista');
      l.partes.forEach(p => { if (!p.valor) return; const i = document.createElement('i'); i.className = p.classe; i.style.width = (p.valor / max * 100) + '%'; pista.appendChild(i); });
      b.querySelector('.valor').innerHTML = l.total ? `<b>${l.total}</b>${l.pct != null ? ' · ' + l.pct + '%' : ''}` : `<span class="pendente-cobertura">${esc(l.vazio || '0')}</span>`;
      dica(b, l.dica); b.onclick = l.clique; caixa.appendChild(b);
    });
  }

  const partesResultado = d => [{ classe: 'c-deferido', valor: d.deferido }, { classe: 'c-indeferido', valor: d.indeferido }, { classe: 'c-neutro', valor: d.nao_informado }];
  const dicaResultado = (nome, d) => `${nome}\nDeferidos: ${d.deferido}\nIndeferidos: ${d.indeferido}\nNão informado: ${d.nao_informado}\nTotal: ${d.total}`;

  function porAssunto() {
    const s = P.series.por_assunto, total = s.reduce((n, x) => n + x.total, 0), max = Math.max(1, ...s.map(x => x.total));
    const classe = { VERTICAL: 'c-vertical', HORIZONTAL: 'c-horizontal', TEMPO_SERVICO: 'c-tempo' };
    barras($('#gAssunto'), total ? s.map(x => ({
      rotulo: x.rotulo, sub: x.chave === 'TEMPO_SERVICO' ? 'Eixo Tempo de Serviço/Contribuição' : 'Eixo Progressão Funcional', total: x.total, pct: Math.round(x.total / total * 100),
      partes: [{ classe: classe[x.chave], valor: x.total }], dica: dicaResultado(x.rotulo, x),
      selecionada: x.chave === 'TEMPO_SERVICO' ? S.eixo === 'TEMPO_SERVICO' : S.modalidade === x.chave,
      clique: () => { if (x.chave === 'TEMPO_SERVICO') { S.eixo = S.eixo === 'TEMPO_SERVICO' ? '' : 'TEMPO_SERVICO'; S.modalidade = ''; S.grupo = []; }
        else { const mesma = S.modalidade === x.chave; S.eixo = mesma ? '' : 'PROGRESSAO'; S.modalidade = mesma ? '' : x.chave; S.subcategoria = []; } mudou(); }
    })) : [], max);
    if (P.series.progressao_sem_modalidade) $('#gAssunto').insertAdjacentHTML('beforeend', `<p class="pendente-cobertura">${P.series.progressao_sem_modalidade} decisão(ões) de Progressão sem modalidade identificada.</p>`);
  }

  function porGrupo() {
    const g = P.series.por_grupo, max = Math.max(1, ...g.map(x => x.total)), total = g.reduce((n, x) => n + x.total, 0);
    barras($('#gGrupos'), g.map(x => ({
      rotulo: x.grupo === 'NAO_INFORMADO' ? 'Grupo não informado' : x.grupo + ' · ' + x.nome, sub: `Horizontal ${x.horizontal} · Vertical ${x.vertical}`, total: x.total, pct: Math.round(x.total / total * 100),
      partes: partesResultado(x), dica: dicaResultado(x.nome, x) + `\nHorizontal: ${x.horizontal} · Vertical: ${x.vertical}`, selecionada: S.grupo.includes(x.grupo),
      clique: () => { S.grupo = S.grupo.includes(x.grupo) ? S.grupo.filter(c => c !== x.grupo) : [...S.grupo, x.grupo]; mudou(); }
    })), max);
  }

  function porSubcategoria() {
    const s = P.series.por_subcategoria, max = Math.max(1, ...s.map(x => x.total)), total = s.reduce((n, x) => n + x.total, 0);
    barras($('#gSubs'), s.map(x => ({
      rotulo: x.nome, sub: x.codigo, total: x.total, pct: total ? Math.round(x.total / total * 100) : null, vazio: x.situacao, partes: partesResultado(x),
      dica: x.total ? dicaResultado(x.nome, x) : `${x.nome}\n${x.situacao}`, selecionada: S.subcategoria.includes(x.codigo),
      clique: () => { S.subcategoria = S.subcategoria.includes(x.codigo) ? S.subcategoria.filter(c => c !== x.codigo) : [...S.subcategoria, x.codigo]; mudou(); }
    })), max);
  }

  function cobertura() {
    const c = P.meta.cobertura;
    $('#gCobertura').innerHTML = [['Edições no acervo', c.edicoes_no_acervo], ['Edições lidas', c.edicoes_lidas], ['Com pendência de leitura', c.edicoes_com_pendencia_de_leitura],
      ['Páginas lidas', c.paginas_lidas], ['Páginas com pendência', c.paginas_com_pendencia]].map(([r, v]) => `<div><b>${esc(v)}</b><span>${esc(r)}</span></div>`).join('')
      + `<p>${esc(c.parecer)}</p>`;
  }

  /* ---------- tabela e detalhes ---------- */
  function itensDaTabela() {
    if (S.visao === 'alteracoes') return P.eventos.map(e => ({ tipo: 'evento', id: e.id, e }));
    if (S.modo === 'processo' && P.meta.dados_individuais) return P.linhas.map(l => ({ tipo: 'decisao', id: l.id, l }));
    return P.resenhas.map(r => ({ tipo: 'ato', id: r.ato_id, r }));
  }

  function tabela() {
    const itens = itensDaTabela(), paginas = Math.max(1, Math.ceil(itens.length / POR_PAGINA));
    S.pagina = Math.min(S.pagina, paginas - 1);
    const caixa = $('#tabela'); caixa.innerHTML = '';
    $('#modoProcesso').disabled = !P.meta.dados_individuais || S.visao === 'alteracoes'; $('#modoResenha').disabled = S.visao === 'alteracoes';
    const ev = S.visao === 'alteracoes';
    $('#modoResenha').classList.toggle('ativa', !ev && (S.modo === 'resenha' || !P.meta.dados_individuais)); $('#modoProcesso').classList.toggle('ativa', !ev && S.modo === 'processo' && P.meta.dados_individuais);
    $('#tituloTabela').textContent = S.visao === 'alteracoes' ? 'Eventos de alteração' : S.cartao ? NOMES.cartao[S.cartao] : 'Publicações e processos';
    $('#contagemTabela').textContent = S.visao === 'alteracoes' ? `${itens.length} evento(s)` : `${P.resenhas.length} resenha(s) · ${P.resenhas.reduce((n, r) => n + r.decisoes, 0)} decisão(ões)`;
    if (!itens.length) caixa.innerHTML = `<p class="vazio">${P.meta.dados_individuais || S.visao !== 'alteracoes' ? 'Nenhum registro neste recorte.' : 'Nenhum evento validado.'}</p>`;
    itens.slice(S.pagina * POR_PAGINA, (S.pagina + 1) * POR_PAGINA).forEach(it => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'item' + (S.selecionado && S.selecionado.id === it.id ? ' selecionado' : '');
      if (it.tipo === 'ato') {
        const r = it.r;
        b.innerHTML = `<b>Resenha ${esc(r.resenha || 's/ nº')}</b><span class="selo ${classeAssunto(r)}">${esc(r.eixo === 'TEMPO_SERVICO' ? 'Tempo de Serviço' : NOMES.modalidade[r.modalidade] || 'Progressão')}</span>`
          + `<small>${dataBR(r.data)} · p. ${r.pagina} · ${r.decisoes} decisão(ões) · ${esc(assunto(r))}${r.vinculo !== 'EXPRESSO' ? ' · <span class="selo alerta">GEDIV não expressa</span>' : ''}${r.refeito ? ' · <span class="selo alerta">refeito</span>' : ''}${r.sem_efeito ? ' · <span class="selo alerta">sem efeito</span>' : ''}</small>`;
      } else if (it.tipo === 'decisao') {
        const l = it.l;
        b.innerHTML = `<b>${esc(l.processo || 'processo não informado')}</b><span class="selo ${l.resultado === 'DEFERIDO' ? 'deferido' : l.resultado === 'INDEFERIDO' ? 'indeferido' : ''}">${l.resultado === 'DEFERIDO' ? '✓ ' : l.resultado === 'INDEFERIDO' ? '✕ ' : ''}${esc(NOMES.resultado[l.resultado])}</span>`
          + `<small>${esc(l.servidor || 'servidor não identificado')} · mat. ${esc(l.matricula || 'não informada')} · Resenha ${esc(l.resenha)} · ${dataBR(l.data)}</small>`;
      } else {
        const e = it.e;
        b.innerHTML = `<b>${esc(NOMES.alteracao[e.tipo] || e.tipo)}${e.subtipo === 'POR_INCORRECAO' ? ' por incorreção' : ''}</b><span class="selo ${e.estado === 'VALIDADO' ? 'deferido' : 'alerta'}">${esc(NOMES.estado[e.estado] || e.estado)}</span>`
          + `<small>${dataBR(e.data_publicacao)} · p. ${e.pagina} · ${esc(e.modificador || '')}${e.resenhas_citadas.length ? ' · cita resenha ' + esc(e.resenhas_citadas.join(', ')) : ''}</small>`;
      }
      b.onclick = () => { S.selecionado = it; tabela(); detalhes(); };
      caixa.appendChild(b);
    });
    $('#pgTexto').textContent = `Página ${S.pagina + 1} de ${paginas}`; $('#pgAnt').disabled = S.pagina === 0; $('#pgProx').disabled = S.pagina >= paginas - 1;
  }

  const fonteHTML = o => (o.url_oficial ? `<a class="botao" href="${esc(o.url_oficial)}" target="_blank" rel="noopener noreferrer">Abrir no DOE oficial ↗</a>` : '<span class="selo alerta">Endereço oficial não informado</span>')
    + (o.pdf_no_acervo ? ` <button type="button" class="botao" data-pdf="${esc(o.pdf_no_acervo)}">Abrir PDF do acervo (p. ${esc(o.pdf_no_acervo.split('=')[1] || '')})</button>` : '');
  const linhaDL = (t, v) => `<dt>${esc(t)}</dt><dd>${v}</dd>`;
  const detalheTexto = d => Object.keys(d || {}).length ? Object.entries(d).map(([k, v]) => `${esc(k.replace(/_/g, ' '))}: <b>${esc(v)}</b>`).join(' · ') : '<span class="pendente-cobertura">não informado</span>';

  async function detalhes() {
    const caixa = $('#detalhes'), it = S.selecionado;
    if (!it) { caixa.innerHTML = '<p class="vazio">Selecione uma resenha, um processo ou um evento.</p>'; return; }
    if (it.tipo === 'evento') {
      const e = it.e;
      caixa.innerHTML = '<dl>' + linhaDL('Tipo', esc(NOMES.alteracao[e.tipo] || e.tipo)) + linhaDL('Data do evento', dataBR(e.data_publicacao)) + linhaDL('Ato modificador', esc(e.modificador || 'não informado'))
        + linhaDL('Página', esc(e.pagina)) + linhaDL('Resenhas citadas', esc(e.resenhas_citadas.join(', ') || 'nenhuma')) + linhaDL('Estado', esc(NOMES.estado[e.estado] || e.estado))
        + linhaDL('Ato original', esc(e.ato_original_id || (e.ato_sugerido_id ? e.ato_sugerido_id + ' (sugestão, não validada)' : 'não vinculado'))) + linhaDL('Fundamento', esc(e.fundamento || '—')) + '</dl>'
        + (e.texto ? `<blockquote>${esc(e.texto)}</blockquote>` : '') + (P.meta.dados_individuais ? `<div class="acoes-detalhe">${fonteHTML(e)}`
          + (e.estado !== 'VALIDADO' ? '<button type="button" class="botao primario" data-rev="evento:VINCULAR">Validar vínculo…</button><button type="button" class="botao perigo" data-rev="evento:REJEITAR">Rejeitar…</button>' : '<button type="button" class="botao" data-rev="evento:REABRIR">Reabrir…</button>') + '</div>' : '');
      return ligarAcoes(caixa, it);
    }
    const base = it.tipo === 'ato' ? it.r : it.l;
    let html = '<dl>' + linhaDL('Resenha', esc(base.resenha || 'não informada') + (base.sufixo ? ' ' + esc(base.sufixo) : '')) + linhaDL('Publicação', dataBR(base.data) + ' · página ' + esc(base.pagina))
      + linhaDL('Eixo', esc(NOMES.eixo[base.eixo] || 'não classificado'));
    if (base.eixo === 'PROGRESSAO') html += linhaDL('Modalidade', esc(NOMES.modalidade[base.modalidade] || 'não informada')) + linhaDL('Grupo do PCCR', esc(base.grupo ? nomeGrupo(base.grupo) : 'não informado')) + linhaDL('Condição', esc(NOMES.condicao[base.condicao] || 'Não informada'));
    else html += linhaDL('Subcategoria', esc(nomeSub(base.subcategoria)));
    html += linhaDL('Vínculo GEDIV', base.vinculo === 'EXPRESSO' ? 'Expresso no ato' : '<span class="selo alerta">Não expresso — só DEREH</span>');
    if (it.tipo === 'decisao') {
      const l = it.l;
      html += linhaDL('Processo', esc(l.processo || 'não informado')) + linhaDL('Servidor', esc(l.servidor || 'não identificado')) + linhaDL('Matrícula', esc(l.matricula || 'não informada'))
        + linhaDL('Lotação', esc(l.lotacao || 'não informada')) + linhaDL('Cargo', esc(l.cargo || 'não informado')) + linhaDL('Classe / nível', detalheTexto(l.detalhe))
        + linhaDL('Resultado', esc(NOMES.resultado[l.resultado])) + linhaDL('Validação', esc(l.validacao) + (l.revisor ? ` · ${esc(l.revisor)} em ${esc(l.revisado_em)}` : '')) + '</dl>'
        + `<blockquote>${esc(l.trecho)}</blockquote><div class="acoes-detalhe">${fonteHTML(l)}`
        + (l.validacao === 'PENDENTE' ? '<button type="button" class="botao primario" data-rev="decisao:CONFERIR">Conferir…</button><button type="button" class="botao perigo" data-rev="decisao:REJEITAR">Rejeitar…</button>' : '<button type="button" class="botao" data-rev="decisao:REABRIR">Reabrir…</button>') + '</div>';
      caixa.innerHTML = html; return ligarAcoes(caixa, it);
    }
    const r = it.r;
    html += linhaDL('Decisões', `${r.decisoes} (✓ ${r.deferido} deferida(s) · ✕ ${r.indeferido} indeferida(s))`) + '</dl>';
    if (!P.meta.dados_individuais) { caixa.innerHTML = html + `<div class="acoes-detalhe">${fonteHTML(r)}</div><p class="vazio">Dados individualizados são restritos à gerência.</p>`; return; }
    caixa.innerHTML = html + '<p class="vazio">Carregando o ato…</p>';
    try {
      const d = await (await api('/api/ato/' + r.ato_id)).json();
      if (S.selecionado !== it) return;
      const pendentes = d.decisoes.filter(x => x.validacao === 'PENDENTE').length;
      html += (d.ato.pendencias.length ? '<b>Pontos de atenção</b><ul>' + d.ato.pendencias.map(p => `<li>${esc(p)}</li>`).join('') + '</ul>' : '')
        + '<table><thead><tr><th>Processo</th><th>Servidor</th><th>Matrícula</th><th>Classe / nível</th><th>Resultado</th><th>Validação</th></tr></thead><tbody>'
        + d.decisoes.map(x => `<tr><td>${esc(x.processo || '—')}</td><td>${esc(x.servidor || 'não identificado')}</td><td>${esc(x.matricula || '—')}</td><td>${detalheTexto(JSON.parse(x.detalhe || '{}'))}</td><td>${esc(NOMES.resultado[x.resultado])}</td><td>${esc(x.validacao)}</td></tr>`).join('')
        + `</tbody></table><b>Texto do ato (como lido)</b><blockquote>${esc(d.ato.texto)}</blockquote><div class="acoes-detalhe">${fonteHTML(d.ato)}`
        + (pendentes ? `<button type="button" class="botao primario" data-rev="ato:CONFERIR">Conferir as ${pendentes} pendente(s)…</button><button type="button" class="botao perigo" data-rev="ato:REJEITAR">Rejeitar as pendentes…</button>` : '<button type="button" class="botao" data-rev="ato:REABRIR">Reabrir revisão…</button>') + '</div>'
        + (d.trilha.length ? '<b>Trilha de auditoria</b><table><tbody>' + d.trilha.slice(0, 8).map(t => `<tr><td>${esc(t.momento)}</td><td>${esc(t.autor)}</td><td>${esc(t.acao)}</td><td>${esc(t.justificativa || '')}</td></tr>`).join('') + '</tbody></table>' : '');
      caixa.innerHTML = html; ligarAcoes(caixa, it);
    } catch (e) { caixa.innerHTML = html + `<p class="erro">${esc(e.message)}</p>`; }
  }

  function ligarAcoes(caixa, it) {
    caixa.querySelectorAll('[data-pdf]').forEach(b => { b.onclick = () => abrirPdf(b.dataset.pdf); });
    caixa.querySelectorAll('[data-rev]').forEach(b => { b.onclick = () => abrirRevisao(it, b.dataset.rev.split(':')[1]); });
  }

  async function abrirPdf(caminho) {
    try {
      const [rota, ancora] = caminho.split('#');
      const blob = await (await api(rota)).blob();
      window.open(URL.createObjectURL(blob) + (ancora ? '#' + ancora : ''), '_blank', 'noopener');
    } catch (e) { aviso('Não foi possível abrir o PDF: ' + e.message, 'erro'); }
  }

  /* ---------- revisão ---------- */
  let revisaoAtual = null;
  function abrirRevisao(it, decisao) {
    revisaoAtual = { it, decisao };
    const base = it.tipo === 'ato' ? it.r : it.tipo === 'decisao' ? it.l : it.e;
    const verbo = { CONFERIR: 'Conferir', REJEITAR: 'Rejeitar', REABRIR: 'Reabrir', VINCULAR: 'Validar vínculo de' }[decisao];
    $('#revTitulo').textContent = `${verbo} ${it.tipo === 'ato' ? 'resenha ' + (base.resenha || '') : it.tipo === 'decisao' ? 'processo ' + (base.processo || '') : 'evento'}`;
    $('#revResumo').textContent = decisao === 'CONFERIR' ? 'Ao conferir, os registros passam a contar nos indicadores. A decisão fica registrada na trilha de auditoria.' : 'A decisão fica registrada na trilha de auditoria e pode ser reaberta.';
    const precisaFonte = decisao === 'CONFERIR' || decisao === 'VINCULAR';
    $('#revFonteLinha').hidden = !precisaFonte; $('#revFonte').checked = false;
    $('#revVinculoLinha').hidden = !(decisao === 'CONFERIR' && base.vinculo !== 'EXPRESSO'); $('#revVinculo').checked = false;
    const vinc = decisao === 'VINCULAR'; $('#revAtoLinha').hidden = $('#revAto').hidden = !vinc; $('#revAto').value = vinc ? (base.ato_original_id || base.ato_sugerido_id || '') : '';
    $('#revJustificativa').value = ''; $('#erroRevisao').textContent = '';
    try { $('#revResponsavel').value = sessionStorage.getItem('gediv_responsavel') || ''; } catch (e) { /* sem armazenamento */ }
    $('#dlgRevisao').showModal();
  }

  async function confirmarRevisao() {
    const { it, decisao } = revisaoAtual, corpo = { alvo: it.tipo, id: it.id, decisao, responsavel: $('#revResponsavel').value, justificativa: $('#revJustificativa').value,
      confirma_fonte: $('#revFonte').checked, confirma_vinculo: $('#revVinculo').checked, ato_original_id: $('#revAto').value.trim() || null };
    try {
      await api('/api/revisao', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
      try { sessionStorage.setItem('gediv_responsavel', corpo.responsavel); } catch (e) { /* sem armazenamento */ }
      $('#dlgRevisao').close(); S.selecionado = null; carregar();
    } catch (e) { $('#erroRevisao').textContent = e.message; }
  }

  /* ---------- outras publicações ---------- */
  function desenharOutras() {
    const tipos = [['', 'Todas']].concat(catalogo.outras.map(o => [o.codigo, o.nome]));
    const barra = $('#tiposOutras'); barra.innerHTML = '';
    tipos.forEach(([c, n]) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = `${n} (${outras.filter(o => !c || o.tipo === c).length})`; b.className = S.tipoOutras === c ? 'ativa' : ''; b.onclick = () => { S.tipoOutras = c; desenharOutras(); }; barra.appendChild(b); });
    const lista = outras.filter(o => !S.tipoOutras || o.tipo === S.tipoOutras), caixa = $('#listaOutras');
    caixa.innerHTML = lista.length ? '' : '<p class="vazio">Nenhuma publicação desse tipo foi encontrada nas edições carregadas. Isso não comprova que não existam.</p>';
    lista.forEach(o => {
      const d = document.createElement('div'); d.className = 'item';
      d.innerHTML = `<b>${esc(o.titulo)}</b><span class="selo">${esc(o.nome_tipo)}</span><small>${dataBR(o.data)} · p. ${esc(o.pagina)} · ${o.vinculo === 'EXPRESSO' ? 'GEDIV expressa' : 'relação com a GEDIV a confirmar'} · ${esc(o.situacao)}</small>`
        + (o.trecho ? `<small>${esc(o.trecho)}</small>` : '') + `<small>${fonteHTML(o)}</small>`;
      d.querySelectorAll('[data-pdf]').forEach(b => { b.onclick = () => abrirPdf(b.dataset.pdf); });
      caixa.appendChild(d);
    });
  }

  /* ---------- exportação e acesso ---------- */
  async function exportar(formato) {
    try {
      const r = await api(`/api/exportar?formato=${formato}&` + consulta()), blob = await r.blob(), a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = (/filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '') || [])[1] || 'painel-gediv.' + formato;
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) { aviso('Exportação não realizada: ' + e.message, 'erro'); }
  }

  function sair(recarregar = true) { token = ''; try { sessionStorage.removeItem('gediv_token'); } catch (e) { /* sem armazenamento */ } S.escopo = 'conferido'; S.busca = ''; S.vinculo = ''; S.modo = 'resenha'; if (recarregar) carregar(); }

  async function entrar() {
    const candidato = $('#campoToken').value.trim();
    try {
      const r = await fetch('/api/auditoria', { headers: { Authorization: 'Bearer ' + candidato }, cache: 'no-store' });
      if (!r.ok) throw new Error('Credencial não aceita.');
      token = candidato; try { sessionStorage.setItem('gediv_token', token); } catch (e) { /* sem armazenamento */ }
      $('#campoToken').value = ''; $('#dlgAcesso').close(); carregar();
    } catch (e) { $('#erroAcesso').textContent = e.message; }
  }

  /* ---------- eventos ---------- */
  const liga = (id, campo) => $(id).addEventListener('change', ev => { S[campo] = ev.target.value; if (campo === 'eixo') { if (S.eixo === 'TEMPO_SERVICO') { S.modalidade = S.condicao = ''; S.grupo = []; } if (S.eixo === 'PROGRESSAO') S.subcategoria = []; } mudou(); });
  liga('#fInicio', 'inicio'); liga('#fFim', 'fim'); liga('#fEixo', 'eixo'); liga('#fModalidade', 'modalidade'); liga('#fCondicao', 'condicao'); liga('#fResultado', 'resultado'); liga('#fVinculo', 'vinculo'); liga('#fEscopo', 'escopo');
  let espera; $('#fBusca').addEventListener('input', ev => { clearTimeout(espera); espera = setTimeout(() => { S.busca = ev.target.value; mudou(); }, 350); });
  $('#btnLimpar').onclick = () => { Object.assign(S, { inicio: '', fim: '', eixo: VISOES[S.visao].eixo || '', modalidade: '', condicao: '', grupo: [], subcategoria: [], resultado: '', vinculo: '', busca: '', cartao: '' }); mudou(); };
  $$('#abas button').forEach(b => { b.onclick = () => {
    const v = b.dataset.visao; S.visao = v; S.cartao = v === 'alteracoes' ? S.cartao : S.cartao; S.inicio = S.fim = '';
    S.eixo = VISOES[v].eixo || ''; if (v === 'tempo') { S.modalidade = S.condicao = ''; S.grupo = []; } if (v === 'progressao') S.subcategoria = []; mudou(); }; });
  $('#btnAtualizar').onclick = carregar; $('#btnXlsx').onclick = () => exportar('xlsx'); $('#btnCsv').onclick = () => exportar('csv'); $('#btnPdf').onclick = () => window.print();
  $('#btnRecolher').onclick = () => $('#casca').classList.add('recolhida'); $('#btnExpandir').onclick = () => $('#casca').classList.remove('recolhida');
  $('#modoResenha').onclick = () => { S.modo = 'resenha'; S.pagina = 0; S.selecionado = null; tabela(); detalhes(); };
  $('#modoProcesso').onclick = () => { S.modo = 'processo'; S.pagina = 0; S.selecionado = null; tabela(); detalhes(); };
  $('#pgAnt').onclick = () => { S.pagina--; tabela(); }; $('#pgProx').onclick = () => { S.pagina++; tabela(); };
  $('#btnTelaCheia').onclick = () => { const c = document.querySelector('.explorador'); if (document.fullscreenElement) document.exitFullscreen(); else if (c.requestFullscreen) c.requestFullscreen().catch(() => c.classList.toggle('cheia')); else c.classList.toggle('cheia'); };
  $('#btnAcesso').onclick = () => { $('#erroAcesso').textContent = ''; $('#btnSair').hidden = !token; $('#dlgAcesso').showModal(); };
  $('#btnEntrar').onclick = entrar; $('#btnSair').onclick = () => { $('#dlgAcesso').close(); sair(); };
  $('#campoToken').addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); entrar(); } });
  $('#btnConfirmarRevisao').onclick = confirmarRevisao;
  carregar();
})();
