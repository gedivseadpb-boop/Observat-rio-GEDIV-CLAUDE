/* Painel Diário Oficial | GEDIV — nova interface (em desenvolvimento).
   Lê SOMENTE a projeção pública agregada (mesmo arquivo e mesmo validador do painel atual).
   Não recebe, não deriva e não exibe registros individuais. Não altera o painel publicado. */
(function () {
  'use strict';
  const M = window.GedivModelo, G = window.GedivGraficos;
  const $ = id => document.getElementById(id);
  const meta = nome => document.querySelector(`meta[name="${nome}"]`)?.content || '';

  /* ---------- utilidades de DOM (sem innerHTML com dados) ---------- */
  function h(tag, atributos, ...filhos) {
    const e = document.createElement(tag);
    Object.entries(atributos || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === 'class') e.className = v;
      else if (k === 'texto') e.textContent = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : String(v));
    });
    filhos.flat().forEach(f => { if (f !== null && f !== undefined && f !== false) e.appendChild(typeof f === 'string' ? document.createTextNode(f) : f); });
    return e;
  }

  /* ---------- textos fixos ---------- */
  const NOMES_MES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  const rotuloMes = p => { const [a, m] = p.split('-').map(Number); return NOMES_MES[m - 1] + ' de ' + a; };
  const rotuloMesCurto = p => { const [a, m] = p.split('-').map(Number); return NOMES_MES[m - 1].slice(0, 3) + '/' + a; };
  const data = iso => iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4) : '—';
  const dataHora = iso => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleString('pt-BR', { timeZone: 'America/Fortaleza', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };
  const CORES = { HORIZONTAL: 'var(--verde)', VERTICAL: 'var(--azul)', PROGRESSAO: 'var(--azul)', TEMPO_SERVICO: 'var(--laranja)' };

  const ESTADOS = {
    provisorio: { rotulo: 'Provisório', texto: 'Extraído automaticamente do Diário Oficial; ainda sem conferência humana. Não é resultado oficial.' },
    conferido: { rotulo: 'Conferido', texto: 'Revisado pela GEDIV.' },
    zero: { rotulo: 'Zero confirmado', texto: 'A base confirma que não há registros nesta situação.' },
    faixa: { rotulo: 'Faixa protegida', texto: 'Mostrado como intervalo (por exemplo, 40–44) para não permitir identificar pessoas. Não é uma contagem exata.' },
    semAgregado: { rotulo: 'Sem agregado publicável', texto: 'Não há número público para este recorte: pode não haver registros ou o recorte foi protegido por ter menos de 5 pessoas. Isso não significa zero.' },
    semDado: { rotulo: 'Sem dado público', texto: 'Este detalhamento não está disponível na base pública atual.' },
    naoVerificado: { rotulo: 'Não verificado', texto: 'Ainda não há informação conferida para esta categoria; isso não significa zero.' },
    gerencial: { rotulo: 'Só na área gerencial', texto: 'Consulta individual indisponível nesta versão pública; exige autenticação e autorização no servidor.' },
    mensal: { rotulo: 'Só mensal', texto: 'Os dados publicados são mensais; não há números por dia.' }
  };
  const etiqueta = (chave, extra) => h('span', { class: 'etiqueta etiqueta-' + chave, title: ESTADOS[chave].texto }, ESTADOS[chave].rotulo + (extra ? ' · ' + extra : ''));

  /* ---------- estado da aplicação ---------- */
  let dados = null;
  let rotaAnterior = null;
  const ROTAS = {
    inicio: { titulo: 'Visão geral', grupo: 'assunto' },
    progressao: { titulo: 'Progressão Funcional', grupo: 'assunto' },
    tempo: { titulo: 'Tempo de Serviço', grupo: 'assunto' },
    edicoes: { titulo: 'Edições e fontes', grupo: 'documento' },
    dia: { titulo: 'Publicações do dia', grupo: 'documento' },
    historico: { titulo: 'Histórico', grupo: 'documento' },
    alteracoes: { titulo: 'Alterações e refeitos', grupo: 'documento' },
    outras: { titulo: 'Outras publicações', grupo: 'documento' },
    ajuda: { titulo: 'Entenda os dados', grupo: 'apoio' },
    gerencial: { titulo: 'Área gerencial', grupo: 'apoio' }
  };

  function lerRota() {
    const bruto = location.hash.replace(/^#\/?/, '');
    const [nome, consulta] = bruto.split('?');
    const rota = ROTAS[nome] ? nome : 'inicio';
    const p = new URLSearchParams(consulta || '');
    const filtros = {};
    // Só aceita valores que existem no catálogo / na base: filtros inválidos são descartados.
    const meses = mesesCobertos();
    if (meses.includes(p.get('mes'))) filtros.mes = p.get('mes');
    if (M.MODALIDADES[p.get('mod')]) filtros.mod = p.get('mod');
    if (p.get('grupo') === 'NAO_INFORMADO' || dados?.catalogo.grupos.some(g => g.codigo === p.get('grupo'))) filtros.grupo = p.get('grupo');
    if (dados?.catalogo.subcategorias.some(s => s.codigo === p.get('ts'))) filtros.ts = p.get('ts');
    if (/^20\d\d-\d\d-\d\d$/.test(p.get('dia') || '') && M.validDate(p.get('dia'))) filtros.dia = p.get('dia');
    return { rota, filtros };
  }
  function endereco(rota, filtros) {
    const q = new URLSearchParams();
    ['mes', 'mod', 'grupo', 'ts', 'dia'].forEach(k => { if (filtros[k]) q.set(k, filtros[k]); });
    const s = q.toString();
    return '#/' + rota + (s ? '?' + s : '');
  }
  function mudarFiltros(mudanca) {
    const { rota, filtros } = lerRota();
    const novo = { ...filtros, ...mudanca };
    Object.keys(novo).forEach(k => { if (!novo[k]) delete novo[k]; });
    location.hash = endereco(rota, novo);
  }

  function mesesCobertos() {
    if (!dados) return [];
    const c = dados.cobertura, meses = new Set(dados.celulas.map(x => x.periodo));
    if (c.primeira_publicacao && c.ultima_publicacao) {
      let [a, m] = c.primeira_publicacao.slice(0, 7).split('-').map(Number);
      const fim = c.ultima_publicacao.slice(0, 7);
      for (let i = 0; i < 60; i++) {
        const p = a + '-' + String(m).padStart(2, '0');
        meses.add(p);
        if (p >= fim) break;
        m++; if (m > 12) { m = 1; a++; }
      }
    }
    return [...meses].sort();
  }

  /* ---------- seleção de células com o mesmo modelo do painel atual ---------- */
  function celulas({ eixo, mes, mod, grupo, ts } = {}) {
    const s = M.novoEstado();
    if (mes) { s.inicio = mes + '-01'; s.fim = M.monthEnd(mes); }
    if (eixo) s.eixo = eixo;
    if (mod) s.modalidade = mod;
    if (grupo) s.grupo = grupo;
    if (ts) s.subcategorias = [ts];
    return M.filterCells(dados.celulas, s);
  }
  const soma = (lista, chave = 'decisoes') => M.sumMetrics(lista.map(c => c[chave]));
  const faixaDe = m => { const b = M.numberBounds(m); return b ? { min: b.min, max: b.max } : null; };
  const nomeGrupo = codigo => codigo === 'NAO_INFORMADO' || codigo === null ? 'Grupo não informado' : (dados.catalogo.grupos.find(g => g.codigo === codigo)?.nome || codigo);
  const nomeServico = codigo => dados.catalogo.subcategorias.find(s => s.codigo === codigo)?.nome || codigo;

  /* ---------- componentes ---------- */
  function cabecalho(titulo, descricao, ...extra) {
    return h('header', { class: 'cabecalho-pagina' },
      h('div', {}, h('p', { class: 'sobretitulo', texto: ROTAS[lerRota().rota].grupo === 'documento' ? 'Navegação por documento' : ROTAS[lerRota().rota].grupo === 'apoio' ? 'Apoio' : 'Navegação por assunto' }),
        h('h1', { id: 'tituloPagina', tabindex: '-1', texto: titulo }),
        h('p', { class: 'descricao', texto: descricao })),
      frescor(), ...extra);
  }
  function frescor() {
    const c = dados.cobertura;
    return h('div', { class: 'frescor' },
      h('span', { class: 'frescor-ponto', 'aria-hidden': 'true' }),
      h('div', {},
        h('b', { texto: `Dados até ${data(c.ultima_publicacao)}` }),
        h('span', { texto: `Projeção gerada em ${dataHora(dados.atualizado_em)}. Esta página não faz coleta do Diário Oficial.` })));
  }
  function kpi({ titulo, metrica, estado, unidade, explicacao, acao }) {
    const bounds = metrica ? M.numberBounds(metrica) : null;
    const valor = bounds ? metrica.rotulo : '—';
    return h('article', { class: 'kpi' + (bounds ? '' : ' kpi-sem-dado') },
      h('h3', { texto: titulo }),
      h('p', { class: 'kpi-valor' }, h('span', { texto: valor }), unidade ? h('small', { texto: ' ' + unidade }) : null),
      h('div', { class: 'kpi-etiquetas' }, estado.map(e => etiqueta(e))),
      h('p', { class: 'kpi-explicacao', texto: explicacao }),
      acao || null);
  }
  function painel({ titulo, subtitulo, conteudo, tabela, interpretacao, id }) {
    return h('section', { class: 'painel', 'aria-labelledby': id },
      h('h2', { id, texto: titulo }),
      subtitulo ? h('p', { class: 'painel-subtitulo', texto: subtitulo }) : null,
      conteudo,
      interpretacao ? h('p', { class: 'interpretacao' }, h('b', { texto: 'Como ler: ' }), interpretacao) : null,
      tabela ? h('details', { class: 'ver-tabela' }, h('summary', { texto: 'Ver estes números em tabela' }), tabela) : null);
  }
  function tabela(cabecalhos, linhas, legenda) {
    return h('div', { class: 'tabela-rolagem', tabindex: '0', role: 'region', 'aria-label': legenda || 'Tabela' },
      h('table', {},
        legenda ? h('caption', { texto: legenda }) : null,
        h('thead', {}, h('tr', {}, cabecalhos.map(c => h('th', { scope: 'col', texto: c })))),
        h('tbody', {}, linhas.map(l => h('tr', {}, l.map((v, i) => i === 0 ? h('th', { scope: 'row' }, v) : h('td', {}, v)))))));
  }
  function vazio(chave, texto, ...acoes) {
    return h('div', { class: 'vazio vazio-' + chave },
      etiqueta(chave), h('p', { texto: texto || ESTADOS[chave].texto }), ...acoes);
  }
  function botaoLink(texto, href, primario) { return h('a', { class: 'botao' + (primario ? ' botao-primario' : ''), href, texto }); }
  function aviso(tipo, titulo, texto) { return h('div', { class: 'estado estado-' + tipo, role: 'note' }, h('b', { texto: titulo }), h('p', { texto })); }

  /* Barra de filtros da seção, sempre visível, com filtros ativos e "Limpar". */
  function barraFiltros(rota, filtros, campos) {
    const form = h('form', { class: 'filtros', 'aria-label': 'Filtros desta seção', onsubmit: e => e.preventDefault() });
    if (campos.includes('mes')) {
      const sel = h('select', { id: 'filtroMes', onchange: e => mudarFiltros({ mes: e.target.value }) },
        h('option', { value: '', texto: 'Todo o período disponível' }),
        mesesCobertos().map(m => h('option', { value: m, selected: filtros.mes === m, texto: rotuloMes(m)[0].toUpperCase() + rotuloMes(m).slice(1) })));
      form.appendChild(h('label', { class: 'campo' }, h('span', { texto: 'Mês de publicação' }), sel));
    }
    if (campos.includes('grupo')) {
      const sel = h('select', { id: 'filtroGrupo', onchange: e => mudarFiltros({ grupo: e.target.value }) },
        h('option', { value: '', texto: 'Todos os grupos PCCR' }),
        dados.catalogo.grupos.map(g => h('option', { value: g.codigo, selected: filtros.grupo === g.codigo, texto: g.codigo + ' — ' + g.nome })),
        h('option', { value: 'NAO_INFORMADO', selected: filtros.grupo === 'NAO_INFORMADO', texto: 'Grupo não informado' }));
      form.appendChild(h('label', { class: 'campo' }, h('span', { texto: 'Grupo ocupacional (PCCR)' }), sel));
    }
    if (campos.includes('ts')) {
      const sel = h('select', { id: 'filtroServico', onchange: e => mudarFiltros({ ts: e.target.value }) },
        h('option', { value: '', texto: 'Os sete serviços' }),
        dados.catalogo.subcategorias.map(s => h('option', { value: s.codigo, selected: filtros.ts === s.codigo, texto: s.codigo + ' — ' + s.nome })));
      form.appendChild(h('label', { class: 'campo' }, h('span', { texto: 'Serviço de Tempo de Serviço' }), sel));
    }
    const ativos = [];
    if (filtros.mes) ativos.push(['mes', 'Mês: ' + rotuloMes(filtros.mes)]);
    if (filtros.mod && campos.includes('mod')) ativos.push(['mod', 'Modalidade: ' + M.MODALIDADES[filtros.mod]]);
    if (filtros.grupo && campos.includes('grupo')) ativos.push(['grupo', 'Grupo: ' + nomeGrupo(filtros.grupo)]);
    if (filtros.ts && campos.includes('ts')) ativos.push(['ts', 'Serviço: ' + nomeServico(filtros.ts)]);
    const chips = h('div', { class: 'filtros-ativos', 'aria-label': 'Filtros aplicados' },
      h('b', { texto: ativos.length ? 'Filtros aplicados:' : 'Sem filtros: mostrando todo o período disponível.' }),
      ativos.map(([k, t]) => h('button', { type: 'button', class: 'chip', 'aria-label': `Remover filtro ${t}`, onclick: () => mudarFiltros({ [k]: '' }) }, t, h('span', { 'aria-hidden': 'true', texto: ' ✕' }))),
      ativos.length ? h('button', { type: 'button', class: 'botao-texto', id: 'limparFiltros', onclick: () => { location.hash = endereco(rota, {}); }, texto: 'Limpar filtros' }) : null);
    return h('div', { class: 'barra-filtros' }, form, chips);
  }

  /* Exportação: só o recorte mostrado, com cabeçalho de contexto. */
  function exportacao(nomeBase, lista, contexto) {
    const linhas = () => [
      ['Painel Diário Oficial | GEDIV — agregados públicos protegidos'],
      ['Recorte: ' + contexto],
      ['Cobertura: ' + data(dados.cobertura.primeira_publicacao) + ' a ' + data(dados.cobertura.ultima_publicacao) + ' · ' + dados.cobertura.edicoes + ' edições · ' + dados.cobertura.paginas + ' páginas · histórico de 2026 incompleto'],
      ['Projeção: ' + dataHora(dados.atualizado_em) + ' · regras ' + dados.versao_regras],
      ['Faixas não são contagens exatas; recortes com menos de 5 pessoas não são divulgados; dados provisórios não são resultados oficiais.'],
      [],
      ...M.cellsToRows(lista, dados.catalogo)
    ];
    const baixar = (conteudo, tipo, nome) => {
      const url = URL.createObjectURL(new Blob([conteudo], { type: tipo }));
      const a = h('a', { href: url, download: nome }); document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    const semDados = !lista.length;
    return h('div', { class: 'exportar', role: 'group', 'aria-label': 'Exportar o recorte mostrado' },
      h('span', { texto: semDados ? 'Nada para exportar neste recorte.' : 'Exportar o que está na tela:' }),
      h('button', { type: 'button', class: 'botao', disabled: semDados, onclick: () => baixar('﻿' + linhas().map(r => r.map(M.csvValue).join(';')).join('\r\n'), 'text/csv;charset=utf-8', nomeBase + '.csv') }, 'CSV'),
      h('button', { type: 'button', class: 'botao', disabled: semDados || !window.GEDIVXLSX, onclick: () => window.GEDIVXLSX.baixar(linhas(), nomeBase + '.xlsx') }, 'Excel'),
      h('button', { type: 'button', class: 'botao', disabled: semDados || !window.GEDIVPDF, onclick: () => { const t = M.cellsToRows(lista, dados.catalogo); window.GEDIVPDF.baixar({ titulo: 'Painel Diário Oficial | GEDIV', metadados: linhas().slice(1, 5).map(r => r[0]), cabecalho: t[0], linhas: t.slice(1) }, nomeBase + '.pdf'); } }, 'PDF'),
      h('button', { type: 'button', class: 'botao', disabled: semDados, onclick: () => imprimir(contexto, lista) }, 'Imprimir'));
  }
  function imprimir(contexto, lista) {
    const alvo = $('impressao'); alvo.replaceChildren();
    const t = M.cellsToRows(lista, dados.catalogo);
    alvo.append(h('h1', { texto: 'Painel Diário Oficial | GEDIV' }), h('p', { texto: 'Recorte: ' + contexto }),
      h('p', { texto: `Cobertura: ${data(dados.cobertura.primeira_publicacao)} a ${data(dados.cobertura.ultima_publicacao)}; ${dados.cobertura.edicoes} edições; projeção de ${dataHora(dados.atualizado_em)}. Faixas não são contagens exatas.` }),
      tabela(t[0], t.slice(1)));
    window.print();
  }

  function explicarAgregado(c) {
    const titulo = 'Entender este agregado';
    const corpo = h('div', {},
      h('p', { texto: 'Esta linha é um AGREGADO MENSAL: soma várias decisões publicadas no mês. Não é uma resenha, um processo nem uma ficha individual.' }),
      tabela(['Campo', 'Valor'], [
        ['Mês de publicação', rotuloMes(c.periodo)],
        ['Eixo', M.EIXOS[c.eixo]],
        ['Modalidade', M.MODALIDADES[c.modalidade] || '—'],
        ['Grupo PCCR', c.eixo === 'PROGRESSAO' ? nomeGrupo(c.grupo) : '—'],
        ['Serviço', c.eixo === 'TEMPO_SERVICO' ? nomeServico(c.subcategoria) : '—'],
        ['Decisões (faixa)', c.decisoes.rotulo],
        ['Atos em que aparecem (faixa)', c.atos.rotulo],
        ['Situação', c.situacao === 'conferido' ? 'Conferido' : 'Provisório (sem conferência humana)']
      ], 'Detalhes do agregado'),
      h('h3', { texto: 'O que não está aqui, e por quê' }),
      h('ul', {},
        h('li', { texto: 'Quais resenhas, processos e pessoas compõem o número: só na área gerencial, com autenticação.' }),
        h('li', { texto: 'Número exato: a faixa protege contra identificação de pessoas.' }),
        h('li', { texto: 'Link para a página do PDF oficial: ainda não há vínculo verificado na base pública.' })));
    abrirDialogo(titulo, corpo);
  }
  function abrirDialogo(titulo, corpo) {
    $('dialogoTitulo').textContent = titulo;
    $('dialogoCorpo').replaceChildren(corpo);
    if ($('dialogo').showModal) $('dialogo').showModal(); else $('dialogo').setAttribute('open', '');
  }

  function tabelaCelulas(lista, legenda) {
    if (!lista.length) return vazio('semAgregado', 'Nenhum agregado divulgável para estes filtros; isso não prova que não houve publicações.');
    const ordenadas = M.sortCells(lista, 'periodo', 1);
    return tabela(['Mês', 'Eixo / modalidade', 'Grupo ou serviço', 'Decisões (faixa)', 'Situação', 'Detalhes'],
      ordenadas.map(c => [
        rotuloMesCurto(c.periodo),
        M.EIXOS[c.eixo] + (c.modalidade ? ' · ' + M.MODALIDADES[c.modalidade] : ''),
        c.eixo === 'PROGRESSAO' ? nomeGrupo(c.grupo) : nomeServico(c.subcategoria),
        c.decisoes.rotulo,
        etiqueta(c.situacao === 'conferido' ? 'conferido' : 'provisorio'),
        h('button', { type: 'button', class: 'botao-texto', onclick: () => explicarAgregado(c), texto: 'Entender este agregado' })
      ]), legenda);
  }

  /* ---------- páginas ---------- */
  function paginaInicio(f) {
    const c = dados.cobertura, r = dados.resumo;
    const comMes = !!f.mes;
    const lista = celulas({ mes: f.mes });
    const out = [cabecalho('Visão geral', 'O que foi encontrado no Diário Oficial sobre Progressão Funcional e Tempo de Serviço, em que período, e com que grau de conferência.')];

    out.push(h('section', { class: 'cobertura', 'aria-labelledby': 'tCobertura' },
      h('h2', { id: 'tCobertura', texto: 'O que esta base cobre' }),
      h('div', { class: 'cobertura-grade' },
        h('div', {}, h('span', { texto: 'Período lido' }), h('b', { texto: `${data(c.primeira_publicacao)} a ${data(c.ultima_publicacao)}` })),
        h('div', {}, h('span', { texto: 'Edições do Diário Oficial' }), h('b', { texto: String(c.edicoes) })),
        h('div', {}, h('span', { texto: 'Páginas lidas' }), h('b', { texto: c.paginas.toLocaleString('pt-BR') })),
        h('div', {}, h('span', { texto: 'Histórico de 2026' }), h('b', { texto: c.historico_completo ? 'Completo' : 'Incompleto' }), h('small', { texto: `começa em ${data(c.inicio_historico)}` }))),
      h('p', { class: 'cobertura-nota' },
        `${c.ausencia_tecnica_edicoes} edição(ões) com ausência técnica e ${c.inconclusivas} inconclusiva(s). `,
        'Ausência de dados não confirma ausência de atos. ',
        h('a', { href: '#/edicoes', texto: 'Ver edições e fontes' }))));

    out.push(barraFiltros('inicio', f, ['mes']));

    const kpis = h('section', { class: 'kpis', 'aria-label': 'Indicadores principais' });
    if (!comMes) {
      kpis.append(
        kpi({ titulo: 'Decisões encontradas', metrica: r.provisorios, unidade: 'decisões', estado: ['provisorio', 'faixa'], explicacao: 'Decisões individuais extraídas das resenhas, nos dois eixos. Ainda sem conferência humana.' }),
        kpi({ titulo: 'Atos publicados com essas decisões', metrica: r.atos, unidade: 'atos', estado: ['faixa'], explicacao: 'Resenhas e atos do Diário Oficial em que as decisões aparecem. Um ato pode ter várias decisões.' }),
        kpi({ titulo: 'Decisões conferidas pela GEDIV', metrica: r.conferidos, unidade: 'decisões', estado: [M.numberBounds(r.conferidos)?.max === 0 ? 'zero' : 'conferido'], explicacao: 'Nenhuma decisão passou ainda pela conferência humana. Por isso, os números acima são provisórios.' }));
    } else {
      kpis.append(
        kpi({ titulo: 'Decisões em agregados publicáveis do mês', metrica: soma(lista), unidade: 'decisões', estado: ['provisorio', 'faixa'], explicacao: 'Soma só dos recortes com 5 pessoas ou mais. Recortes protegidos não entram, por isso pode ficar abaixo do total real do mês.' }),
        kpi({ titulo: 'Atos do mês', metrica: null, estado: ['semDado'], explicacao: 'A base pública não informa o total de atos por mês sem risco de identificação.' }),
        kpi({ titulo: 'Decisões conferidas pela GEDIV', metrica: r.conferidos, unidade: 'decisões', estado: ['zero'], explicacao: 'Nenhuma decisão foi conferida em todo o período, portanto também neste mês.' }));
    }
    out.push(kpis);

    // Composição por eixo
    let itensEixo;
    if (!comMes) {
      itensEixo = Object.keys(M.EIXOS).map(e => ({ rotulo: M.EIXOS[e], cor: CORES[e], estado: 'ok', ...faixaDe(dados.resumo_eixos[e].provisorios) }));
    } else {
      itensEixo = Object.keys(M.EIXOS).map(e => {
        const l = celulas({ mes: f.mes, eixo: e }), m = soma(l);
        return l.length ? { rotulo: M.EIXOS[e], cor: CORES[e], estado: 'ok', ...faixaDe(m) } : { rotulo: M.EIXOS[e], estado: 'sem-dado', nota: 'Sem agregado publicável neste mês' };
      });
    }
    out.push(h('div', { class: 'duas-colunas' },
      painel({ id: 'tEixos', titulo: 'Como as decisões se dividem entre os dois eixos',
        subtitulo: `Decisões provisórias · ${comMes ? rotuloMes(f.mes) : 'todo o período disponível'} · faixas`,
        conteudo: G.barrasFaixa(itensEixo, { titulo: 'Decisões por eixo', aoClicar: item => { location.hash = item.rotulo === M.EIXOS.PROGRESSAO ? endereco('progressao', { mes: f.mes }) : endereco('tempo', { mes: f.mes }); } }),
        interpretacao: 'A parte escura da barra é o mínimo garantido; a parte clara mostra até onde a faixa pode ir. Clique numa barra para abrir o eixo.',
        tabela: tabela(['Eixo', 'Decisões (faixa)'], itensEixo.map(i => [i.rotulo, i.estado === 'ok' ? G.rotuloFaixa(i.min, i.max) : ESTADOS.semAgregado.rotulo]), 'Decisões por eixo') }),
      painelEvolucao(f, null)));

    out.push(h('section', { class: 'atalhos', 'aria-labelledby': 'tAtalhos' },
      h('h2', { id: 'tAtalhos', texto: 'Por onde começar' }),
      h('div', { class: 'atalhos-grade' },
        atalho('↗', 'Ver Progressão Funcional', 'Horizontal e Vertical, por grupo do PCCR e por mês.', endereco('progressao', { mes: f.mes })),
        atalho('◷', 'Ver Tempo de Serviço', 'Os sete serviços e o que já pode ser mostrado.', endereco('tempo', { mes: f.mes })),
        atalho('▤', 'Ver edições e fontes', 'Quais edições foram lidas e onde está o documento oficial.', '#/edicoes'),
        atalho('?', 'Entender os números', 'Por que aparecem faixas, o que é provisório e o que é protegido.', '#/ajuda'))));

    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tOutros' },
      h('h2', { id: 'tOutros', texto: 'Outros indicadores — aguardando dados' }),
      h('p', { class: 'painel-subtitulo', texto: 'Estes indicadores fazem parte do painel, mas a base pública atual ainda não permite calculá-los com segurança.' }),
      h('ul', { class: 'lista-pendentes' },
        pendente('Processos distintos', 'semDado', 'O número do processo é dado individual; a contagem pública depende de uma projeção específica.'),
        pendente('Deferidos e indeferidos', 'semDado', 'A base pública ainda não separa resultados. Nenhum número foi estimado.'),
        pendente('Refeitos (retificações e republicações)', 'semDado', 'Eventos de alteração ainda não constam da base pública.', '#/alteracoes'),
        pendente('Tornados sem efeito', 'semDado', 'Idem: depende do vínculo verificado entre o ato original e o ato que o altera.', '#/alteracoes'),
        pendente('Publicações de um dia específico', 'mensal', 'A base pública é mensal.', '#/dia'))));

    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tTabela' },
      h('h2', { id: 'tTabela', texto: 'Agregados publicáveis deste recorte' }),
      h('p', { class: 'painel-subtitulo', texto: 'Cada linha é um total mensal protegido. Não é uma resenha nem um processo.' }),
      tabelaCelulas(lista, 'Agregados mensais publicáveis'),
      exportacao('GEDIV_visao_geral' + (f.mes ? '_' + f.mes : ''), lista, f.mes ? rotuloMes(f.mes) : 'todo o período disponível')));
    return out;
  }
  function atalho(simbolo, titulo, texto, href) {
    return h('a', { class: 'atalho', href }, h('span', { class: 'atalho-simbolo', 'aria-hidden': 'true', texto: simbolo }), h('b', { texto: titulo }), h('span', { texto }));
  }
  function pendente(nome, estado, texto, href) {
    return h('li', {}, h('b', { texto: nome }), etiqueta(estado), h('span', { texto: ' ' + texto }), href ? h('a', { href, texto: ' Saiba mais' }) : null);
  }

  function painelEvolucao(f, mod, grupo) {
    const meses = mesesCobertos();
    const series = (mod ? [mod] : ['HORIZONTAL', 'VERTICAL']).map(m => ({
      nome: 'Progressão ' + M.MODALIDADES[m], cor: CORES[m],
      porMes: Object.fromEntries(meses.map(p => { const l = celulas({ mes: p, eixo: 'PROGRESSAO', mod: m, grupo }); return [p, l.length ? faixaDe(soma(l)) : null]; }))
    }));
    const tsLinha = Object.fromEntries(meses.map(p => { const l = celulas({ mes: p, eixo: 'TEMPO_SERVICO' }); return [p, l.length ? faixaDe(soma(l)) : null]; }));
    const temTs = Object.values(tsLinha).some(Boolean) && !mod && !grupo;
    if (temTs) series.push({ nome: 'Tempo de Serviço', cor: CORES.TEMPO_SERVICO, porMes: tsLinha });
    const algum = series.some(s => Object.values(s.porMes).some(Boolean));
    return painel({ id: 'tEvolucao' + (mod || '') + (grupo || ''), titulo: 'Evolução mês a mês',
      subtitulo: 'Decisões em agregados publicáveis, por mês de publicação · faixas · não há números por dia',
      conteudo: algum ? h('div', {}, G.colunasMensais(meses, series, { titulo: 'Evolução mensal das decisões', rotuloMes: rotuloMesCurto }),
        h('ul', { class: 'legenda' }, series.map(s => h('li', {}, h('span', { class: 'legenda-cor', style: `--cor:${s.cor}` }), s.nome))))
        : vazio('semAgregado', 'Nenhum mês tem agregado publicável para este recorte.'),
      interpretacao: (temTs ? '' : 'Tempo de Serviço não aparece porque nenhum mês tem recorte com 5 pessoas ou mais. ') + 'Um traço (—) indica mês sem agregado publicável, não zero.',
      tabela: tabela(['Mês', ...series.map(s => s.nome)], meses.map(p => [rotuloMes(p), ...series.map(s => s.porMes[p] ? G.rotuloFaixa(s.porMes[p].min, s.porMes[p].max) : 'sem agregado publicável')]), 'Evolução mensal') });
  }

  function paginaProgressao(f) {
    const out = [cabecalho('Progressão Funcional', 'Mudança de nível (Horizontal) ou de classe (Vertical) na carreira. Veja por modalidade, por grupo ocupacional do PCCR e por mês.')];
    out.push(h('nav', { class: 'sub-abas', 'aria-label': 'Modalidade da progressão' },
      [['', 'Todas'], ['HORIZONTAL', 'Horizontal'], ['VERTICAL', 'Vertical']].map(([v, t]) =>
        h('a', { href: endereco('progressao', { ...f, mod: v }), 'aria-current': (f.mod || '') === v ? 'page' : null, texto: t }))));
    out.push(barraFiltros('progressao', f, ['mes', 'mod', 'grupo']));

    const lista = celulas({ eixo: 'PROGRESSAO', mes: f.mes, mod: f.mod, grupo: f.grupo });
    const semFiltro = !f.mes && !f.mod && !f.grupo;
    const re = dados.resumo_eixos.PROGRESSAO;
    out.push(h('section', { class: 'kpis', 'aria-label': 'Indicadores da Progressão' },
      kpi({ titulo: semFiltro ? 'Decisões de Progressão' : 'Decisões neste recorte', metrica: semFiltro ? re.provisorios : soma(lista), unidade: 'decisões', estado: ['provisorio', 'faixa'],
        explicacao: semFiltro ? 'Total do eixo no período disponível.' : 'Soma só dos agregados publicáveis do recorte; recortes protegidos não entram.' }),
      kpi({ titulo: 'Atos (resenhas) de Progressão', metrica: semFiltro ? re.atos : null, unidade: 'atos', estado: semFiltro ? ['faixa'] : ['semDado'],
        explicacao: semFiltro ? 'Resenhas do Diário Oficial com decisões de Progressão.' : 'O total de atos não é divulgado para recortes menores.' }),
      kpi({ titulo: 'Conferidas pela GEDIV', metrica: re.conferidos, unidade: 'decisões', estado: ['zero'], explicacao: 'Ainda não houve conferência humana nesta base.' })));

    const modItens = ['HORIZONTAL', 'VERTICAL'].map(m => {
      const l = celulas({ eixo: 'PROGRESSAO', mes: f.mes, mod: m, grupo: f.grupo });
      return l.length ? { codigo: m, rotulo: M.MODALIDADES[m], cor: CORES[m], estado: 'ok', ...faixaDe(soma(l)) } : { codigo: m, rotulo: M.MODALIDADES[m], estado: 'sem-dado', nota: ESTADOS.semAgregado.rotulo };
    });
    const grupos = [...dados.catalogo.grupos.map(g => g.codigo), 'NAO_INFORMADO'];
    const grupoItens = grupos.map(g => {
      const l = celulas({ eixo: 'PROGRESSAO', mes: f.mes, mod: f.mod, grupo: g });
      return l.length ? { codigo: g, rotulo: g === 'NAO_INFORMADO' ? 'Não informado' : g, cor: f.grupo === g ? 'var(--laranja)' : CORES[f.mod || 'PROGRESSAO'], estado: 'ok', ...faixaDe(soma(l)) }
        : { codigo: g, rotulo: g === 'NAO_INFORMADO' ? 'Não informado' : g, estado: 'sem-dado', nota: 'Sem agregado publicável' };
    }).sort((a, b) => (b.estado === 'ok') - (a.estado === 'ok') || (b.min || 0) - (a.min || 0));
    out.push(h('div', { class: 'duas-colunas' },
      painel({ id: 'tModalidades', titulo: 'Horizontal × Vertical', subtitulo: 'Decisões provisórias em agregados publicáveis · faixas',
        conteudo: G.barrasFaixa(modItens, { titulo: 'Decisões por modalidade', aoClicar: i => mudarFiltros({ mod: i.codigo }) }),
        interpretacao: 'Clique numa modalidade para filtrar a página toda. A soma das modalidades pode ficar abaixo do total do eixo, porque recortes protegidos não entram.',
        tabela: tabela(['Modalidade', 'Decisões (faixa)'], modItens.map(i => [i.rotulo, i.estado === 'ok' ? G.rotuloFaixa(i.min, i.max) : i.nota]), 'Decisões por modalidade') }),
      painelEvolucao(f, f.mod, f.grupo)));
    out.push(painel({ id: 'tGrupos', titulo: 'Por grupo ocupacional (PCCR)', subtitulo: `Os 16 grupos oficiais e “não informado” · ${f.mod ? M.MODALIDADES[f.mod] : 'Horizontal e Vertical'} · ${f.mes ? rotuloMes(f.mes) : 'todo o período'}`,
      conteudo: h('div', {},
        grupoItens.some(i => i.estado === 'ok') ? G.barrasFaixa(grupoItens.filter(i => i.estado === 'ok'), { titulo: 'Decisões por grupo PCCR', aoClicar: i => mudarFiltros({ grupo: i.codigo }) }) : vazio('semAgregado'),
        h('p', { class: 'sem-agregado-lista' }, h('b', { texto: 'Sem agregado publicável (não significa zero): ' }),
          grupoItens.filter(i => i.estado !== 'ok').map(i => i.codigo === 'NAO_INFORMADO' ? 'não informado' : i.codigo).join(', ') || 'nenhum')),
      interpretacao: '“Sem agregado publicável” não quer dizer zero: pode ser um recorte protegido (menos de 5 pessoas). Expressões como “TEC. ADM” e “STF” não são convertidas em grupos; ficam em “não informado” até decisão da GEDIV.',
      tabela: tabela(['Grupo', 'Nome', 'Decisões (faixa)'], grupoItens.map(i => [i.rotulo, i.codigo === 'NAO_INFORMADO' ? 'Grupo não informado ou sem equivalência homologada' : nomeGrupo(i.codigo), i.estado === 'ok' ? G.rotuloFaixa(i.min, i.max) : i.nota]), 'Decisões por grupo PCCR') }));
    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tTabProg' },
      h('h2', { id: 'tTabProg', texto: 'Agregados de Progressão neste recorte' }),
      h('p', { class: 'painel-subtitulo', texto: 'Totais mensais protegidos. A lista de resenhas e processos fica na área gerencial.' }),
      tabelaCelulas(lista, 'Agregados mensais de Progressão'),
      exportacao('GEDIV_progressao' + (f.mod ? '_' + f.mod.toLowerCase() : '') + (f.grupo ? '_' + f.grupo : '') + (f.mes ? '_' + f.mes : ''), lista,
        ['Progressão Funcional', f.mod ? M.MODALIDADES[f.mod] : 'Horizontal e Vertical', f.grupo ? nomeGrupo(f.grupo) : 'todos os grupos', f.mes ? rotuloMes(f.mes) : 'todo o período'].join(' · '))));
    return out;
  }

  const DESCRICAO_TS = {
    'TS-01': 'Registro de tempo trabalhado antes, em outro órgão ou regime, para contar na vida funcional.',
    'TS-02': 'Retirada de um tempo que havia sido averbado.',
    'TS-03': 'Afastamento sem remuneração, a pedido, por interesse pessoal.',
    'TS-04': 'Volta antecipada de quem estava em licença para tratar de interesses particulares.',
    'TS-05': 'Licença concedida após período de efetivo exercício previsto em lei.',
    'TS-06': 'Licença especial não usufruída convertida em tempo de serviço.',
    'TS-07': 'Conversão de férias, nos termos da legislação.'
  };
  function paginaTempo(f) {
    const out = [cabecalho('Tempo de Serviço', 'Os sete serviços ligados ao tempo de serviço e de contribuição. Todos aparecem sempre, mesmo sem número público.')];
    out.push(barraFiltros('tempo', f, ['mes', 'ts']));
    const re = dados.resumo_eixos.TEMPO_SERVICO;
    const semFiltro = !f.mes && !f.ts;
    const lista = celulas({ eixo: 'TEMPO_SERVICO', mes: f.mes, ts: f.ts });
    out.push(h('section', { class: 'kpis', 'aria-label': 'Indicadores do Tempo de Serviço' },
      kpi({ titulo: semFiltro ? 'Decisões de Tempo de Serviço' : 'Decisões neste recorte', metrica: semFiltro ? re.provisorios : (lista.length ? soma(lista) : null), unidade: 'decisões', estado: semFiltro || lista.length ? ['provisorio', 'faixa'] : ['semAgregado'],
        explicacao: semFiltro ? 'Total do eixo no período disponível, nos sete serviços.' : 'Nenhum agregado publicável para este recorte. Não significa zero.' }),
      kpi({ titulo: 'Atos de Tempo de Serviço', metrica: semFiltro ? re.atos : null, unidade: 'atos', estado: semFiltro ? ['faixa'] : ['semDado'], explicacao: 'Resenhas do Diário Oficial com decisões de Tempo de Serviço.' }),
      kpi({ titulo: 'Conferidas pela GEDIV', metrica: re.conferidos, unidade: 'decisões', estado: ['zero'], explicacao: 'Ainda não houve conferência humana nesta base.' })));

    const servicos = dados.catalogo.subcategorias.map(s => {
      const l = celulas({ eixo: 'TEMPO_SERVICO', mes: f.mes, ts: s.codigo });
      return { s, l, m: l.length ? soma(l) : null };
    });
    const algum = servicos.some(x => x.l.length);
    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tServicos' },
      h('h2', { id: 'tServicos', texto: 'Os sete serviços' }),
      h('p', { class: 'painel-subtitulo', texto: `${f.mes ? rotuloMes(f.mes) : 'Todo o período disponível'} · clique num serviço para filtrar` }),
      h('div', { class: 'servicos-grade' }, servicos.map(({ s, m }) =>
        h('a', { class: 'servico' + (f.ts === s.codigo ? ' selecionado' : ''), href: endereco('tempo', { ...f, ts: f.ts === s.codigo ? '' : s.codigo }), 'aria-current': f.ts === s.codigo ? 'true' : null },
          h('span', { class: 'servico-codigo', texto: s.codigo }),
          h('b', { texto: s.nome }),
          h('span', { class: 'servico-descricao', texto: DESCRICAO_TS[s.codigo] || '' }),
          h('span', { class: 'servico-valor', texto: m ? m.rotulo + ' decisões' : '—' }),
          etiqueta(m ? 'provisorio' : 'semAgregado'))))));
    out.push(painel({ id: 'tDistTs', titulo: 'Distribuição entre os serviços', subtitulo: 'Decisões provisórias em agregados publicáveis · faixas',
      conteudo: algum ? G.barrasFaixa(servicos.map(({ s, m }) => m ? { codigo: s.codigo, rotulo: s.codigo, cor: CORES.TEMPO_SERVICO, estado: 'ok', ...faixaDe(m) } : { codigo: s.codigo, rotulo: s.codigo, estado: 'sem-dado', nota: 'Sem agregado publicável' }), { titulo: 'Decisões por serviço', aoClicar: i => mudarFiltros({ ts: i.codigo }) })
        : vazio('semAgregado', `Há ${re.provisorios.rotulo} decisões de Tempo de Serviço no total, mas nenhum serviço, isoladamente, chega a 5 pessoas em um mês. Para proteger as pessoas, a divisão por serviço não é mostrada. Nenhum gráfico foi desenhado com números estimados.`),
      interpretacao: 'Percentuais entre serviços não são mostrados porque os recortes protegidos não entram no total.',
      tabela: tabela(['Código', 'Serviço', 'Decisões (faixa)'], servicos.map(({ s, m }) => [s.codigo, s.nome, m ? m.rotulo : ESTADOS.semAgregado.rotulo]), 'Decisões por serviço') }));
    out.push(painel({ id: 'tResTs', titulo: 'Resultado por serviço (deferido / indeferido)', conteudo: vazio('semDado', 'A base pública ainda não separa deferimentos e indeferimentos. Nenhum número foi estimado.') }));
    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tTabTs' },
      h('h2', { id: 'tTabTs', texto: 'Agregados de Tempo de Serviço neste recorte' }),
      tabelaCelulas(lista, 'Agregados mensais de Tempo de Serviço'),
      exportacao('GEDIV_tempo_servico' + (f.ts ? '_' + f.ts : '') + (f.mes ? '_' + f.mes : ''), lista, ['Tempo de Serviço', f.ts ? nomeServico(f.ts) : 'os sete serviços', f.mes ? rotuloMes(f.mes) : 'todo o período'].join(' · '))));
    return out;
  }

  function paginaEdicoes() {
    const c = dados.cobertura;
    const out = [cabecalho('Edições e fontes', 'Como o Diário Oficial foi lido: da edição até a decisão. Mostra o que pode ser consultado aqui e o que depende do documento oficial ou da área gerencial.')];
    out.push(h('section', { class: 'cobertura', 'aria-labelledby': 'tCob2' },
      h('h2', { id: 'tCob2', texto: 'Cobertura da leitura' }),
      h('div', { class: 'cobertura-grade' },
        h('div', {}, h('span', { texto: 'Primeira edição lida' }), h('b', { texto: data(c.primeira_publicacao) })),
        h('div', {}, h('span', { texto: 'Última edição lida' }), h('b', { texto: data(c.ultima_publicacao) })),
        h('div', {}, h('span', { texto: 'Edições' }), h('b', { texto: String(c.edicoes) })),
        h('div', {}, h('span', { texto: 'Páginas' }), h('b', { texto: c.paginas.toLocaleString('pt-BR') })),
        h('div', {}, h('span', { texto: 'Com ausência técnica' }), h('b', { texto: String(c.ausencia_tecnica_edicoes) }), h('small', { texto: 'arquivo indisponível ou incompleto' })),
        h('div', {}, h('span', { texto: 'Inconclusivas' }), h('b', { texto: String(c.inconclusivas) }))),
      h('p', { class: 'cobertura-nota', texto: c.observacao })));

    const niveis = [
      ['Ano e mês', 'Disponível', 'ok', `${mesesCobertos().map(rotuloMes).join(' e ')} (de ${data(c.primeira_publicacao)} a ${data(c.ultima_publicacao)}).`],
      ['Edição do Diário Oficial', 'Só contagem', 'parcial', `${c.edicoes} edições identificadas. A lista individual de edições ainda não foi disponibilizada nesta base pública.`],
      ['Arquivo PDF e suplemento', 'Não disponível', 'nao', 'O vínculo com cada arquivo oficial (e sua impressão digital SHA-256) existe na base interna, mas ainda não foi liberado para consulta pública.'],
      ['Página do PDF', 'Só contagem', 'parcial', `${c.paginas.toLocaleString('pt-BR')} páginas lidas no total. Não há link público verificado para cada página.`],
      ['Resenha ou ato', 'Só contagem', 'parcial', `${dados.resumo.atos.rotulo} atos com decisões, em faixa protegida.`],
      ['Decisão e processo', 'Área gerencial', 'gerencial', 'Nome, matrícula, processo e resultado individual só com autenticação no servidor.'],
      ['Alterações posteriores', 'Não disponível', 'nao', 'Retificações, republicações e atos tornados sem efeito ainda não constam da base pública.']
    ];
    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tCadeia' },
      h('h2', { id: 'tCadeia', texto: 'Do documento à decisão: o que se pode consultar' }),
      h('p', { class: 'painel-subtitulo', texto: 'Cada nível depende do anterior. Uma resenha pode ter várias decisões; um processo pode aparecer em mais de uma edição.' }),
      h('ol', { class: 'cadeia' }, niveis.map(([nome, estado, classe, texto], i) =>
        h('li', { class: 'cadeia-nivel cadeia-' + classe },
          h('span', { class: 'cadeia-numero', 'aria-hidden': 'true', texto: String(i + 1) }),
          h('div', {}, h('b', { texto: nome }), h('span', { class: 'cadeia-estado', texto: estado }), h('p', { texto })))))));

    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tFonte' },
      h('h2', { id: 'tFonte', texto: 'Onde está o documento oficial' }),
      h('p', { texto: 'O Diário Oficial do Estado da Paraíba é publicado no portal de A União. Para ler uma edição completa, use o portal oficial e escolha a data desejada.' }),
      h('a', { class: 'botao botao-primario', href: 'https://auniao.pb.gov.br/', rel: 'noopener noreferrer', target: '_blank', texto: 'Abrir o portal oficial de A União ↗' }),
      h('p', { class: 'nota', texto: 'Link externo, para o site oficial. Este painel não tem, ainda, link verificado para a página exata de cada ato.' })));
    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tUnidades' },
      h('h2', { id: 'tUnidades', texto: 'O que cada número conta' }),
      tabela(['Unidade', 'O que representa', 'Cuidado ao comparar'], [
        ['Edição', 'Um número do Diário Oficial, de uma data.', 'Uma edição pode ter suplementos e vários PDFs.'],
        ['Página', 'Uma página de um arquivo PDF.', 'Uma página pode ter vários atos, e um ato pode ocupar mais de uma página.'],
        ['Ato / resenha', 'Texto administrativo publicado.', 'Uma resenha pode ter muitas decisões.'],
        ['Decisão', 'Resultado para uma pessoa, extraído da resenha.', 'Pode haver duas pessoas no mesmo processo.'],
        ['Processo', 'Número administrativo do pedido.', 'Pode aparecer em mais de um ato.']
      ], 'Unidades de contagem')));
    return out;
  }

  function paginaDia(f) {
    const c = dados.cobertura;
    const out = [cabecalho('Publicações do dia', 'Escolha uma data para saber o que a base pública pode mostrar sobre ela.')];
    const campo = h('input', { type: 'date', id: 'dataDia', min: c.inicio_historico, max: c.ultima_publicacao || undefined, value: f.dia || '' });
    out.push(h('form', { class: 'painel filtros', onsubmit: e => { e.preventDefault(); mudarFiltros({ dia: campo.value }); } },
      h('label', { class: 'campo' }, h('span', { texto: 'Data da publicação' }), campo),
      h('button', { type: 'submit', class: 'botao botao-primario', texto: 'Ver esta data' })));
    if (f.dia) {
      const mes = f.dia.slice(0, 7), coberto = c.primeira_publicacao && f.dia >= c.primeira_publicacao && f.dia <= c.ultima_publicacao;
      out.push(h('section', { class: 'painel', 'aria-labelledby': 'tDia' },
        h('h2', { id: 'tDia', texto: 'Data escolhida: ' + data(f.dia) }),
        coberto
          ? vazio('mensal', `A base pública só tem totais mensais. Não há como dizer quantas decisões saíram no dia ${data(f.dia)} — e nenhum total do mês foi atribuído ao dia. O mês de ${rotuloMes(mes)} está no período lido.`,
            botaoLink('Ver ' + rotuloMes(mes), endereco('inicio', { mes }), true), botaoLink('Ver edições e fontes', '#/edicoes'))
          : vazio('semDado', `A data ${data(f.dia)} está fora do período lido nesta base (${data(c.primeira_publicacao)} a ${data(c.ultima_publicacao)}). Isso não significa que não houve publicações.`, botaoLink('Ver edições e fontes', '#/edicoes'))));
    } else {
      out.push(aviso('info', 'Como funciona', `Os números públicos são mensais. Ao escolher um dia, o painel mostra a que mês ele pertence e se a data está no período lido (${data(c.primeira_publicacao)} a ${data(c.ultima_publicacao)}).`));
    }
    return out;
  }

  function paginaHistorico() {
    const c = dados.cobertura, ano = Number(c.inicio_historico.slice(0, 4));
    const meses = Array.from({ length: 12 }, (_, i) => ano + '-' + String(i + 1).padStart(2, '0'));
    const cobertos = mesesCobertos();
    const linhas = meses.map(m => {
      const l = celulas({ mes: m });
      const situacao = cobertos.includes(m) ? (l.length ? 'Lido · com agregados publicáveis' : 'Lido · sem agregado publicável') : (m > (c.ultima_publicacao || '').slice(0, 7) ? 'Ainda não lido' : 'Ainda não lido (histórico pendente)');
      return { m, l, situacao, coberto: cobertos.includes(m) };
    });
    const out = [cabecalho('Histórico', 'Linha do tempo de 2026: quais meses já foram lidos e quando os dados foram atualizados. A data da publicação no Diário Oficial é diferente da data em que este painel foi atualizado.')];
    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tLinha' },
      h('h2', { id: 'tLinha', texto: `Meses de ${ano}` }),
      h('ol', { class: 'linha-tempo' }, linhas.map(x => h('li', { class: x.coberto ? 'lido' : 'nao-lido' },
        h('b', { texto: rotuloMes(x.m)[0].toUpperCase() + rotuloMes(x.m).slice(1) }),
        h('span', { texto: x.situacao }),
        x.l.length ? h('span', { class: 'linha-valor', texto: soma(x.l).rotulo + ' decisões em agregados publicáveis' }) : null,
        x.coberto ? h('a', { href: endereco('inicio', { mes: x.m }), texto: 'Ver este mês' }) : null)))));
    out.push(h('section', { class: 'painel', 'aria-labelledby': 'tDatas' },
      h('h2', { id: 'tDatas', texto: 'Três datas diferentes' }),
      tabela(['Data', 'Valor', 'O que significa'], [
        ['Publicação no Diário Oficial', `${data(c.primeira_publicacao)} a ${data(c.ultima_publicacao)}`, 'Quando os atos foram publicados.'],
        ['Atualização deste painel', dataHora(dados.atualizado_em), 'Quando a base pública foi gerada.'],
        ['Conferência pela GEDIV', 'Nenhuma ainda', 'Quando uma pessoa da gerência revisou as decisões.']
      ], 'Datas')));
    return out;
  }

  function paginaAlteracoes() {
    return [cabecalho('Alterações e refeitos', 'Atos publicados depois para corrigir, repetir ou anular um ato anterior. Não são um terceiro eixo: sempre se referem a uma Progressão ou a um Tempo de Serviço.'),
      h('section', { class: 'painel', 'aria-labelledby': 'tTipos' }, h('h2', { id: 'tTipos', texto: 'Tipos de alteração' }),
        tabela(['Tipo', 'O que é', 'Na base pública'], [
          ['Retificação', 'Corrige parte de um ato publicado.', etiqueta('semDado')],
          ['Republicação por incorreção', 'Publica de novo o ato, corrigido.', etiqueta('semDado')],
          ['Refeito', 'Ato refeito depois de uma correção.', etiqueta('semDado')],
          ['Tornado sem efeito', 'Anula um ato anterior.', etiqueta('semDado')]
        ], 'Tipos de alteração')),
      vazio('semDado', 'Os eventos de alteração existem na base interna, mas só contam depois que a gerência confirma a qual ato original cada um se refere. Por isso ainda não há números públicos aqui.', botaoLink('Ver a área gerencial', '#/gerencial'))];
  }
  function paginaOutras() {
    return [cabecalho('Outras publicações', 'Portarias e outros atos ligados à GEDIV ou à DEREH que não são decisões de Progressão nem de Tempo de Serviço.'),
      vazio('semDado', 'Estas publicações ainda não fazem parte da base pública. Elas não são contadas nos indicadores dos dois eixos.'),
      aviso('info', 'Por que ficam separadas', 'Uma portaria pode tratar de assunto relacionado sem ser uma decisão individual. Misturá-las aos indicadores aumentaria os números sem que houvesse decisões.')];
  }
  function paginaGerencial() {
    return [cabecalho('Área gerencial', 'Consulta por resenha, processo e decisão, com ficha documental e página do Diário Oficial. Reservada à equipe da GEDIV.'),
      h('div', { class: 'estado estado-aviso', role: 'note' }, h('b', { texto: 'Indisponível nesta versão pública' }), h('p', { texto: ESTADOS.gerencial.texto })),
      h('section', { class: 'painel', 'aria-labelledby': 'tGerOferece' }, h('h2', { id: 'tGerOferece', texto: 'O que a área gerencial vai oferecer' }),
        h('ol', { class: 'lista-simples' },
          h('li', { texto: 'Resenha → lista de processos → decisão → ficha com o trecho do Diário Oficial.' }),
          h('li', { texto: 'Conferir, corrigir ou rejeitar decisões, com registro de quem fez e por quê.' }),
          h('li', { texto: 'Vincular retificações e atos tornados sem efeito ao ato original.' }),
          h('li', { texto: 'Exportar planilha gerencial com dados individuais.' }))),
      h('section', { class: 'painel', 'aria-labelledby': 'tGerExige' }, h('h2', { id: 'tGerExige', texto: 'O que é preciso antes de ligar' }),
        h('ul', { class: 'lista-simples' },
          h('li', { texto: 'Autenticação verificada no servidor (não basta esconder telas no navegador).' }),
          h('li', { texto: 'Perfis de acesso e registro de cada consulta.' }),
          h('li', { texto: 'Fonte de dados autorizada e hospedagem com acesso restrito.' }),
          h('li', { texto: 'Aprovação específica da responsável pelo projeto.' })))];
  }
  function paginaAjuda() {
    const p = dados.privacidade;
    return [cabecalho('Entenda os dados', 'Respostas curtas às dúvidas mais comuns sobre os números deste painel.'),
      h('section', { class: 'painel perguntas', 'aria-labelledby': 'tFaq' }, h('h2', { id: 'tFaq', texto: 'Perguntas frequentes' }),
        pergunta('Por que aparecem faixas como “40–44”?', `Para proteger as pessoas. Um número exato pequeno permitiria descobrir quem foi atendido. Recortes com menos de ${p.limiar} pessoas não são mostrados, e os demais aparecem em faixas de ${p.faixa}.`),
        pergunta('O que quer dizer “provisório”?', ESTADOS.provisorio.texto),
        pergunta('“Sem agregado publicável” é o mesmo que zero?', 'Não. ' + ESTADOS.semAgregado.texto),
        pergunta('Qual a diferença entre resenha, decisão e processo?', 'A resenha é o texto publicado no Diário Oficial. Ela traz uma lista de decisões, uma para cada pessoa. Cada decisão tem um número de processo. Uma resenha pode ter dezenas de decisões.'),
        pergunta('Por que não vejo meu processo?', 'Esta é a consulta pública: só mostra totais protegidos. A consulta por pessoa ou processo será feita na área gerencial, com acesso controlado.'),
        pergunta('Os dados estão completos?', dados.cobertura.observacao),
        pergunta('Este painel coleta o Diário Oficial sozinho?', 'Não. Ele mostra a última base gerada. A data aparece no topo de cada página.')),
      h('section', { class: 'painel', 'aria-labelledby': 'tLegenda' }, h('h2', { id: 'tLegenda', texto: 'Legenda das situações' }),
        h('ul', { class: 'legenda-estados' }, Object.keys(ESTADOS).map(k => h('li', {}, etiqueta(k), h('span', { texto: ' ' + ESTADOS[k].texto }))))),
      h('section', { class: 'painel', 'aria-labelledby': 'tTarefas' }, h('h2', { id: 'tTarefas', texto: 'Cinco coisas que você pode fazer' }),
        h('ol', { class: 'lista-simples' },
          h('li', {}, 'Ver o resumo e a cobertura: ', h('a', { href: '#/inicio', texto: 'Visão geral' })),
          h('li', {}, 'Comparar Horizontal e Vertical e escolher um grupo: ', h('a', { href: '#/progressao', texto: 'Progressão Funcional' })),
          h('li', {}, 'Ver os sete serviços: ', h('a', { href: '#/tempo', texto: 'Tempo de Serviço' })),
          h('li', {}, 'Saber quais edições foram lidas: ', h('a', { href: '#/edicoes', texto: 'Edições e fontes' })),
          h('li', {}, 'Entender por que não aparece um processo: ', h('a', { href: '#/gerencial', texto: 'Área gerencial' }))))];
  }
  const pergunta = (q, r) => h('details', { class: 'pergunta' }, h('summary', { texto: q }), h('p', { texto: r }));

  /* ---------- trilha, menu e renderização ---------- */
  function trilha(rota, filtros) {
    const itens = [['Início', '#/inicio']];
    if (rota !== 'inicio') itens.push([ROTAS[rota].titulo, endereco(rota, {})]);
    if (rota === 'progressao' && filtros.mod) itens.push([M.MODALIDADES[filtros.mod], endereco(rota, { mod: filtros.mod })]);
    if (rota === 'progressao' && filtros.grupo) itens.push([nomeGrupo(filtros.grupo), endereco(rota, filtros)]);
    if (rota === 'tempo' && filtros.ts) itens.push([filtros.ts, endereco(rota, filtros)]);
    if (filtros.mes && ['inicio', 'progressao', 'tempo'].includes(rota)) itens.push([rotuloMes(filtros.mes), endereco(rota, filtros)]);
    $('trilha').replaceChildren(...itens.map(([t, href], i) => h('li', {}, i === itens.length - 1 ? h('span', { 'aria-current': 'page', texto: t }) : h('a', { href, texto: t }))));
  }
  function render() {
    if (!dados) return;
    const { rota, filtros } = lerRota();
    const paginas = { inicio: paginaInicio, progressao: paginaProgressao, tempo: paginaTempo, edicoes: paginaEdicoes, dia: paginaDia, historico: paginaHistorico, alteracoes: paginaAlteracoes, outras: paginaOutras, gerencial: paginaGerencial, ajuda: paginaAjuda };
    $('pagina').replaceChildren(...paginas[rota](filtros));
    trilha(rota, filtros);
    document.querySelectorAll('#menuPrincipal a[data-rota]').forEach(a => { if (a.dataset.rota === rota) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    document.title = ROTAS[rota].titulo + ' · Painel Diário Oficial | GEDIV';
    $('anuncio').textContent = ROTAS[rota].titulo + ' carregada';
    if (rotaAnterior !== null && rotaAnterior !== rota) { $('tituloPagina')?.focus(); window.scrollTo(0, 0); }
    rotaAnterior = rota;
    fecharMenu();
  }

  function abrirMenu() {
    $('menuPrincipal').classList.add('aberto'); $('fundoMenu').hidden = false;
    $('abrirMenu').setAttribute('aria-expanded', 'true');
    $('menuPrincipal').querySelector('a')?.focus();
  }
  function fecharMenu() {
    if (!$('menuPrincipal').classList.contains('aberto')) return;
    $('menuPrincipal').classList.remove('aberto'); $('fundoMenu').hidden = true;
    $('abrirMenu').setAttribute('aria-expanded', 'false');
  }

  /* ---------- tema ---------- */
  function aplicarTema(tema) {
    document.documentElement.dataset.theme = tema;
    $('tema').setAttribute('aria-pressed', String(tema === 'dark'));
    $('tema').querySelector('.tema-rotulo').textContent = tema === 'dark' ? 'Modo claro' : 'Modo escuro';
  }
  function temaInicial() {
    try { const t = localStorage.getItem('gediv-v2-tema'); if (t === 'dark' || t === 'light') return t; } catch (e) { /* armazenamento indisponível */ }
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  /* ---------- carregamento ---------- */
  async function estadoDoSite() {
    // Mecanismo reversível de desativação: um arquivo opcional ao lado da página. Ausente = site ativo.
    const url = meta('gediv-estado-site');
    if (!url) return { ativo: true };
    try {
      const r = await fetch(url, { cache: 'no-store' });
      if (!r.ok) return { ativo: true };
      const e = await r.json();
      return e && e.ativo === false ? { ativo: false, mensagem: typeof e.mensagem === 'string' ? e.mensagem.slice(0, 400) : '', desde: typeof e.desde === 'string' ? e.desde.slice(0, 40) : '' } : { ativo: true };
    } catch (erro) { return { ativo: true }; }
  }
  async function carregar() {
    $('falha').hidden = true; $('carregando').hidden = false; $('pagina').replaceChildren(); dados = null;
    const estado = await estadoDoSite();
    if (!estado.ativo) {
      $('carregando').hidden = true;
      $('desativado').hidden = false;
      $('desativado').replaceChildren(h('h2', { texto: 'Painel temporariamente fora do ar' }),
        h('p', { texto: estado.mensagem || 'Esta consulta foi desativada temporariamente pela equipe responsável. Os dados e o código estão preservados.' }),
        estado.desde ? h('p', { class: 'nota', texto: 'Desde: ' + estado.desde }) : null);
      document.body.classList.add('site-desativado');
      return;
    }
    try {
      const r = await fetch(meta('gediv-dados'), { cache: 'no-store' });
      if (!r.ok) throw new Error('A base pública não respondeu (código ' + r.status + ').');
      dados = M.validateProjection(await r.json());
    } catch (erro) {
      dados = null;
      $('carregando').hidden = true;
      $('falhaMensagem').textContent = (erro && erro.message ? erro.message + ' ' : '') + 'Nenhum número antigo está sendo mostrado e as exportações estão desativadas.';
      $('falha').hidden = false;
      return;
    }
    $('carregando').hidden = true;
    render();
  }

  function iniciar() {
    aplicarTema(temaInicial());
    $('tema').addEventListener('click', () => {
      const novo = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      aplicarTema(novo);
      try { localStorage.setItem('gediv-v2-tema', novo); } catch (e) { /* sem armazenamento: só nesta visita */ }
    });
    $('abrirMenu').addEventListener('click', () => ($('menuPrincipal').classList.contains('aberto') ? fecharMenu() : abrirMenu()));
    $('fecharMenu').addEventListener('click', () => { fecharMenu(); $('abrirMenu').focus(); });
    $('fundoMenu').addEventListener('click', fecharMenu);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('menuPrincipal').classList.contains('aberto')) { fecharMenu(); $('abrirMenu').focus(); } });
    $('fecharDialogo').addEventListener('click', () => $('dialogo').close ? $('dialogo').close() : $('dialogo').removeAttribute('open'));
    $('tentarDeNovo').addEventListener('click', carregar);
    window.addEventListener('hashchange', render);
    if (!location.hash) history.replaceState(null, '', '#/inicio');
    carregar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
