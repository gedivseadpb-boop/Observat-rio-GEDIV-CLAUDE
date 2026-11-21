/* Painel do admin GEDIV. Página estática SEM dados: depois do login (conferido no servidor), tudo vem da API
   gerencial. O token de sessão fica só nesta aba (sessionStorage) e é apagado ao sair. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const CHAVE = 'gediv-admin-sessao';
  let api = '', sessao = null, abaAtual = 'fila', aoConfirmar = null;

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
  const trocar = (...itens) => $('area').replaceChildren(...itens.flat().filter(x => x !== null && x !== undefined && x !== false));
  const data = iso => iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4) : '—';
  const dataHora = iso => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? (iso || '—') : d.toLocaleString('pt-BR', { timeZone: 'America/Fortaleza' }); };
  const EIXO = { PROGRESSAO: 'Progressão Funcional', TEMPO_SERVICO: 'Tempo de Serviço' };
  const ESTADO_DECISAO = { PENDENTE: 'Pendente', CONFERIDO: 'Conferida', REJEITADO: 'Rejeitada' };
  const valorLegivel = v => { try { const x = JSON.parse(v); return x === null ? 'vazio' : String(x); } catch (e) { return String(v ?? '—'); } };

  function aviso(tipo, texto) {
    const a = $('aviso');
    if (!texto) { a.hidden = true; a.replaceChildren(); return; }
    a.className = 'estado estado-' + tipo; a.hidden = false; a.replaceChildren(h('p', { texto }));
  }
  function guardar(s) { sessao = s; try { s ? sessionStorage.setItem(CHAVE, JSON.stringify(s)) : sessionStorage.removeItem(CHAVE); } catch (e) { /* só em memória */ } }
  function lerGuardada() { try { return JSON.parse(sessionStorage.getItem(CHAVE) || 'null'); } catch (e) { return null; } }

  /* ---------- API ---------- */
  async function pedir(caminho, { metodo = 'GET', corpo, binario } = {}) {
    const cab = {};
    if (sessao) cab.Authorization = 'Bearer ' + sessao.token;
    if (corpo !== undefined) cab['Content-Type'] = 'application/json';
    let r;
    try {
      r = await fetch(api + caminho, { method: metodo, headers: cab, body: corpo !== undefined ? JSON.stringify(corpo) : undefined, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer' });
    } catch (e) {
      throw new Error('O servidor gerencial não respondeu. Verifique a conexão e tente de novo.');
    }
    if ((r.status === 401 || r.status === 403) && caminho !== '/api/login') {
      guardar(null); mostrarLogin('Sua sessão terminou ou não é mais válida. Entre de novo.');
      throw new Error('sessao');
    }
    if (!r.ok) {
      let msg = 'Erro ' + r.status;
      try { msg = (await r.json()).erro || msg; } catch (e) { /* corpo vazio */ }
      throw new Error(msg);
    }
    return binario ? r : r.json();
  }

  /* ---------- login ---------- */
  function mostrarLogin(mensagem) {
    $('telaApp').hidden = true; $('telaLogin').hidden = false; $('sair').hidden = true; $('quemEsta').hidden = true;
    $('senha').value = '';
    $('erroLogin').textContent = mensagem || '';
    $('usuario').focus();
  }
  async function entrar(e) {
    e.preventDefault();
    const usuario = $('usuario').value.trim(), senha = $('senha').value;
    if (!usuario || !senha) { $('erroLogin').textContent = 'Informe usuário e senha.'; return; }
    $('entrar').disabled = true; $('erroLogin').textContent = '';
    try {
      const s = await pedir('/api/login', { metodo: 'POST', corpo: { usuario, senha } });
      guardar({ token: s.token, usuario: s.usuario, nome: s.nome, expira_em: s.expira_em });
      $('senha').value = '';
      abrirApp();
    } catch (erro) {
      $('erroLogin').textContent = erro.message === 'sessao' ? '' : erro.message;
      $('senha').value = ''; $('senha').focus();
    } finally { $('entrar').disabled = false; }
  }
  async function sair() {
    try { await pedir('/api/logout', { metodo: 'POST', corpo: {} }); } catch (e) { /* encerra localmente de qualquer forma */ }
    guardar(null); mostrarLogin('Você saiu do painel do admin.');
  }

  /* ---------- aplicação ---------- */
  function abrirApp() {
    $('telaLogin').hidden = true; $('telaApp').hidden = false;
    $('quemEsta').hidden = false; $('quemEsta').textContent = 'Conectado: ' + sessao.nome;
    $('sair').hidden = false;
    irAba((location.hash || '#fila').slice(1));
  }
  function irAba(aba) {
    const abas = { fila: telaFila, conferidas: telaConferidas, conflitos: telaConflitos, historico: telaHistorico };
    abaAtual = abas[aba.split('/')[0]] ? aba.split('/')[0] : 'fila';
    document.querySelectorAll('[data-aba]').forEach(a => a.dataset.aba === abaAtual ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
    const ato = aba.match(/^(?:fila|conferidas)\/ato\/([0-9a-f]{20})$/);
    trocar(h('p', { class: 'carregando', texto: 'Carregando…' }));
    (ato ? telaAto(ato[1]) : abas[abaAtual]()).catch(erro => { if (erro.message !== 'sessao') trocar(h('div', { class: 'estado estado-erro' }, h('p', { texto: erro.message }))); });
  }

  async function listaResenhas(escopo, titulo, descricao) {
    const p = await pedir('/api/painel?escopo=' + escopo);
    const apoio = p.apoio || {};
    const resenhas = p.resenhas || [];
    const exportar = h('button', { type: 'button', class: 'botao', onclick: () => baixarPlanilha(escopo) }, 'Baixar planilha gerencial');
    return [
      h('div', { class: 'cabeca-aba' }, h('div', {}, h('h1', { tabindex: '-1', id: 'tituloAba', texto: titulo }), h('p', { class: 'descricao', texto: descricao })), exportar),
      h('div', { class: 'resumo-admin' },
        h('div', {}, h('span', { texto: 'Decisões aguardando revisão' }), h('b', { texto: String(apoio.decisoes_pendentes ?? '—') })),
        h('div', {}, h('span', { texto: 'Conferidas' }), h('b', { texto: String(apoio.decisoes_conferidas ?? '—') })),
        h('div', {}, h('span', { texto: 'Rejeitadas' }), h('b', { texto: String(apoio.decisoes_rejeitadas ?? '—') })),
        h('div', {}, h('span', { texto: 'Conflitos abertos' }), h('b', { texto: String(apoio.conflitos_abertos ?? '—') }))),
      resenhas.length ? h('div', { class: 'tabela-rolagem', role: 'region', tabindex: '0', 'aria-label': titulo },
        h('table', {}, h('thead', {}, h('tr', {}, ['Resenha', 'Publicação', 'Assunto', 'Decisões', 'Situação', ''].map(t => h('th', { scope: 'col', texto: t })))),
          h('tbody', {}, resenhas.map(r => h('tr', {},
            h('th', { scope: 'row' }, 'Resenha ' + r.resenha, r.sufixo ? h('small', { texto: ' ' + r.sufixo }) : null),
            h('td', { texto: data(r.data) + ' · p. ' + r.pagina }),
            h('td', { texto: (EIXO[r.eixo] || '—') + (r.modalidade ? ' · ' + r.modalidade.toLowerCase() : '') + (r.grupo ? ' · ' + r.grupo : '') + (r.subcategoria ? ' · ' + r.subcategoria : '') }),
            h('td', { texto: String(r.decisoes) }),
            h('td', {}, r.conflito_aberto ? h('span', { class: 'etiqueta etiqueta-provisorio', texto: 'Com conflito' }) : null, r.vinculo && r.vinculo !== 'EXPRESSO' ? h('span', { class: 'etiqueta etiqueta-semDado', texto: 'GEDIV não expressa' }) : null),
            h('td', {}, h('a', { class: 'botao', href: '#' + abaAtual + '/ato/' + r.ato_id, texto: 'Abrir' }))))))) :
        h('div', { class: 'vazio' }, h('p', { texto: escopo === 'pendente' ? 'Nenhuma resenha aguardando revisão.' : 'Nenhuma resenha conferida ainda.' }))
    ];
  }
  async function telaFila() { trocar(...await listaResenhas('pendente', 'Fila de revisão', 'Resenhas com decisões ainda não conferidas. Abra uma resenha, compare com o PDF oficial e confira, corrija ou rejeite.')); foco(); }
  async function telaConferidas() { trocar(...await listaResenhas('conferido', 'Já conferidas', 'Resenhas com decisões já conferidas, que entram nos indicadores públicos.')); foco(); }
  const foco = () => $('tituloAba')?.focus();

  async function telaAto(id) {
    const d = await pedir('/api/ato/' + id);
    const a = d.ato, pend = d.decisoes.filter(x => x.validacao === 'PENDENTE' && x.vigente !== 0);
    const voltar = h('a', { class: 'botao-texto', href: '#' + abaAtual, texto: '← Voltar à lista' });
    const pdf = h('button', { type: 'button', class: 'botao', onclick: () => abrirPdf(a.sha256, a.pagina) }, 'Abrir o PDF desta página');
    const conferirTodas = pend.length ? h('button', { type: 'button', class: 'botao botao-primario', onclick: () => revisarAto(a, pend.length) }, `Conferir as ${pend.length} pendentes`) : null;
    const rejeitarTodas = pend.length ? h('button', { type: 'button', class: 'botao', onclick: () => revisarAto(a, pend.length, 'REJEITAR') }, 'Rejeitar as pendentes') : null;
    trocar(
      voltar,
      h('div', { class: 'cabeca-aba' }, h('div', {},
        h('h1', { tabindex: '-1', id: 'tituloAba', texto: `${a.tipo === 'PORTARIA' ? 'Portaria' : 'Resenha'} ${a.numero}${a.sufixo ? ' ' + a.sufixo : ''}` }),
        h('p', { class: 'descricao', texto: `${EIXO[a.eixo] || '—'}${a.modalidade ? ' · ' + a.modalidade.toLowerCase() : ''}${a.grupo ? ' · grupo ' + a.grupo : ''}${a.subcategoria ? ' · ' + a.subcategoria : ''} · publicada em ${data(a.data_publicacao)}, página ${a.pagina}` })),
        h('div', { class: 'acoes' }, pdf, a.url_oficial ? h('a', { class: 'botao', href: a.url_oficial, target: '_blank', rel: 'noopener noreferrer', texto: 'Página oficial ↗' }) : null)),
      a.pendencias.length ? h('div', { class: 'estado estado-aviso' }, h('b', { texto: 'Pontos de atenção apontados pelo robô' }), h('ul', {}, a.pendencias.map(p => h('li', { texto: p })))) : null,
      d.conflitos.length ? h('div', { class: 'estado estado-erro' }, h('b', { texto: `${d.conflitos.length} conflito(s) aberto(s) nesta resenha. ` }), h('a', { href: '#conflitos', texto: 'Resolver na aba Conflitos' })) : null,
      h('section', { class: 'painel', 'aria-labelledby': 'tDec' },
        h('div', { class: 'cabeca-aba' }, h('h2', { id: 'tDec', texto: `Decisões (${d.decisoes.length})` }), h('div', { class: 'acoes' }, conferirTodas, rejeitarTodas)),
        h('div', { class: 'tabela-rolagem', role: 'region', tabindex: '0', 'aria-label': 'Decisões da resenha' },
          h('table', {}, h('thead', {}, h('tr', {}, ['Processo', 'Matrícula', 'Nome', 'Cargo', 'Evolução', 'Resultado', 'Situação', 'Ações'].map(t => h('th', { scope: 'col', texto: t })))),
            h('tbody', {}, d.decisoes.map(x => {
              let det = {}; try { det = typeof x.detalhe === 'string' ? JSON.parse(x.detalhe || '{}') : (x.detalhe || {}); } catch (e) { det = {}; }
              const evol = det.classe_anterior ? `${det.classe_anterior} → ${det.classe_posterior || '?'}` : det.nivel_anterior ? `${det.nivel_anterior} → ${det.nivel_atual || '?'}` : det.dias ? `${det.dias} dias` : '—';
              return h('tr', { class: x.vigente === 0 ? 'fora-contagem' : null },
                h('th', { scope: 'row', texto: x.processo || 'sem processo' }), h('td', { texto: x.matricula || '—' }), h('td', { texto: x.servidor || '—' }), h('td', { texto: x.cargo || '—' }),
                h('td', { texto: evol }), h('td', { texto: x.resultado }),
                h('td', {}, h('span', { class: 'etiqueta ' + (x.validacao === 'CONFERIDO' ? 'etiqueta-conferido' : x.validacao === 'REJEITADO' ? 'etiqueta-semDado' : 'etiqueta-provisorio'), texto: ESTADO_DECISAO[x.validacao] || x.validacao }),
                  x.revisor ? h('small', { class: 'revisor', texto: ' por ' + x.revisor }) : null),
                h('td', { class: 'acoes-linha' },
                  x.validacao !== 'CONFERIDO' ? h('button', { type: 'button', class: 'botao-texto', onclick: () => revisarDecisao(x, 'CONFERIR', a) }, 'Conferir') : null,
                  h('button', { type: 'button', class: 'botao-texto', onclick: () => corrigirDecisao(x, det, a) }, 'Corrigir'),
                  x.validacao === 'PENDENTE' ? h('button', { type: 'button', class: 'botao-texto', onclick: () => revisarDecisao(x, 'REJEITAR', a) }, 'Rejeitar') : h('button', { type: 'button', class: 'botao-texto', onclick: () => revisarDecisao(x, 'REABRIR', a) }, 'Reabrir')));
            }))))),
      d.trilha.length ? h('section', { class: 'painel', 'aria-labelledby': 'tTrilha' }, h('h2', { id: 'tTrilha', texto: 'O que já foi feito nesta resenha' }),
        h('ul', { class: 'trilha-acoes' }, d.trilha.slice(0, 30).map(t => h('li', {}, h('b', { texto: dataHora(t.momento) }), ` · ${t.autor} · ${t.acao}`, t.justificativa ? h('span', { texto: ' — ' + t.justificativa }) : null)))) : null);
    foco();
  }

  /* ---------- diálogos de revisão (sempre com justificativa e confirmação de consulta ao PDF) ---------- */
  function dialogo(titulo, corpo, rotulo, acao) {
    $('dialogoTitulo').textContent = titulo; $('dialogoCorpo').replaceChildren(...corpo); $('dialogoErro').textContent = '';
    $('dialogoConfirmar').textContent = rotulo; aoConfirmar = acao;
    $('dialogo').showModal();
  }
  const campoJust = () => h('label', { class: 'campo campo-largo' }, h('span', { texto: 'Justificativa (obrigatória)' }), h('textarea', { id: 'dlgJust', rows: '3', required: true }));
  const caixa = (id, texto) => h('label', { class: 'caixa' }, h('input', { type: 'checkbox', id }), h('span', { texto }));
  const comuns = () => ({ justificativa: $('dlgJust').value.trim(), confirma_fonte: $('dlgFonte')?.checked || false, confirma_vinculo: $('dlgVinculo')?.checked || false });
  function revisarAto(a, n, decisao = 'CONFERIR') {
    const corpo = [h('p', { texto: decisao === 'CONFERIR' ? `Conferir as ${n} decisões pendentes desta resenha. Elas passam a contar nos indicadores públicos.` : `Rejeitar as ${n} decisões pendentes desta resenha. Elas saem da fila e não contam nos indicadores.` }), campoJust()];
    if (decisao === 'CONFERIR') corpo.push(caixa('dlgFonte', 'Consultei o PDF oficial e os dados conferem.'));
    if (decisao === 'CONFERIR' && a.vinculo !== 'EXPRESSO') corpo.push(caixa('dlgVinculo', 'Confirmo que o ato é de competência da GEDIV (o texto cita só a DEREH).'));
    dialogo(decisao === 'CONFERIR' ? 'Conferir a resenha' : 'Rejeitar as pendentes', corpo, decisao === 'CONFERIR' ? 'Conferir' : 'Rejeitar',
      () => pedir('/api/revisao', { metodo: 'POST', corpo: { alvo: 'ato', id: a.id, decisao, ...comuns() } }));
  }
  function revisarDecisao(x, decisao, a) {
    const nomes = { CONFERIR: 'Conferir decisão', REJEITAR: 'Rejeitar decisão', REABRIR: 'Reabrir decisão' };
    const corpo = [h('p', { texto: `Processo ${x.processo || 'sem número'} · ${x.servidor || 'sem nome'}` }), campoJust()];
    if (decisao === 'CONFERIR') corpo.push(caixa('dlgFonte', 'Consultei o PDF oficial e os dados conferem.'));
    if (decisao === 'CONFERIR' && a.vinculo !== 'EXPRESSO') corpo.push(caixa('dlgVinculo', 'Confirmo que o ato é de competência da GEDIV.'));
    dialogo(nomes[decisao], corpo, nomes[decisao].split(' ')[0], () => pedir('/api/revisao', { metodo: 'POST', corpo: { alvo: 'decisao', id: x.id, decisao, ...comuns() } }));
  }
  function corrigirDecisao(x, det, a) {
    const campos = [['processo', 'Processo', x.processo], ['matricula', 'Matrícula', x.matricula], ['servidor', 'Nome', x.servidor], ['cargo', 'Cargo', x.cargo], ['lotacao', 'Lotação', x.lotacao],
      ['classe_anterior', 'Classe/nível anterior', det.classe_anterior || ''], ['classe_posterior', 'Classe/nível novo', det.classe_posterior || '']];
    const sel = h('select', { id: 'dlg_resultado' }, ['DEFERIDO', 'INDEFERIDO', 'NAO_INFORMADO'].map(v => h('option', { value: v, selected: x.resultado === v, texto: v === 'NAO_INFORMADO' ? 'Não informado' : v[0] + v.slice(1).toLowerCase() })));
    const corpo = [h('p', { texto: 'Altere só o que estiver diferente do PDF oficial. O valor anterior fica guardado no histórico.' }),
      h('div', { class: 'grade-campos' }, campos.map(([k, rot, v]) => h('label', { class: 'campo' }, h('span', { texto: rot }), h('input', { id: 'dlg_' + k, value: v || '' }))),
        h('label', { class: 'campo' }, h('span', { texto: 'Resultado' }), sel)),
      campoJust(), caixa('dlgFonte', 'Consultei o PDF oficial.'), a.vinculo !== 'EXPRESSO' ? caixa('dlgVinculo', 'Confirmo que o ato é de competência da GEDIV.') : null].filter(Boolean);
    dialogo('Corrigir decisão', corpo, 'Salvar correção', () => {
      const correcoes = {};
      campos.forEach(([k, , v]) => { const novo = $('dlg_' + k).value.trim(); if (novo !== (v || '')) correcoes[k] = novo || null; });
      if ($('dlg_resultado').value !== x.resultado) correcoes.resultado = $('dlg_resultado').value;
      if (det.nivel_anterior && 'classe_anterior' in correcoes) { correcoes.nivel_anterior = correcoes.classe_anterior; delete correcoes.classe_anterior; }
      if (det.nivel_anterior && 'classe_posterior' in correcoes) { correcoes.nivel_atual = correcoes.classe_posterior; delete correcoes.classe_posterior; }
      if (!Object.keys(correcoes).length) throw new Error('Nenhum campo foi alterado.');
      return pedir('/api/revisao', { metodo: 'POST', corpo: { alvo: 'decisao', id: x.id, decisao: 'CONFERIR', correcoes, ...comuns() } });
    });
  }
  async function confirmarDialogo(e) {
    e.preventDefault();
    if (!$('dlgJust').value.trim()) { $('dialogoErro').textContent = 'Escreva uma justificativa.'; $('dlgJust').focus(); return; }
    $('dialogoConfirmar').disabled = true;
    try {
      await aoConfirmar();
      $('dialogo').close();
      $('anuncio').textContent = 'Registrado.';
      aviso('info', 'Registrado no seu nome: ' + sessao.nome + '.');
      irAba(location.hash.slice(1) || abaAtual);
    } catch (erro) {
      if (erro.message !== 'sessao') $('dialogoErro').textContent = erro.message; else $('dialogo').close();
    } finally { $('dialogoConfirmar').disabled = false; }
  }

  /* ---------- conflitos e histórico ---------- */
  async function telaConflitos() {
    const d = await pedir('/api/conflitos');
    trocar(
      h('div', { class: 'cabeca-aba' }, h('div', {}, h('h1', { tabindex: '-1', id: 'tituloAba', texto: 'Conflitos' }),
        h('p', { class: 'descricao', texto: 'Quando o robô lê de novo um PDF e encontra um valor diferente do que a gerência já revisou, o valor revisado fica valendo e a diferença aparece aqui para decisão.' }))),
      d.conflitos.length ? h('div', { class: 'tabela-rolagem', role: 'region', tabindex: '0', 'aria-label': 'Conflitos abertos' },
        h('table', {}, h('thead', {}, h('tr', {}, ['Onde', 'Campo', 'Valor em vigor', 'Nova leitura propõe', 'Origem', 'Decisão'].map(t => h('th', { scope: 'col', texto: t })))),
          h('tbody', {}, d.conflitos.map(c => h('tr', {},
            h('th', { scope: 'row', texto: c.alvo_tipo }), h('td', { texto: c.campo }), h('td', { texto: valorLegivel(c.valor_vigente) }), h('td', { texto: valorLegivel(c.valor_proposto) }), h('td', { texto: c.origem }),
            h('td', { class: 'acoes-linha' },
              h('button', { type: 'button', class: 'botao-texto', onclick: () => resolver(c, 'MANTER') }, 'Manter o valor em vigor'),
              h('button', { type: 'button', class: 'botao-texto', onclick: () => resolver(c, 'ACEITAR') }, 'Aceitar a nova leitura'))))))) :
        h('div', { class: 'vazio' }, h('p', { texto: 'Nenhum conflito aberto.' })));
    foco();
  }
  function resolver(c, decisao) {
    dialogo(decisao === 'ACEITAR' ? 'Aceitar a nova leitura' : 'Manter o valor em vigor',
      [h('p', { texto: `Campo ${c.campo}: em vigor “${valorLegivel(c.valor_vigente)}”, nova leitura “${valorLegivel(c.valor_proposto)}”.` }), campoJust(), caixa('dlgFonte', 'Consultei o PDF oficial.')],
      'Confirmar', () => pedir('/api/revisao', { metodo: 'POST', corpo: { alvo: 'conflito', id: c.id, decisao, ...comuns() } }));
  }
  async function telaHistorico() {
    const d = await pedir('/api/auditoria');
    trocar(
      h('div', { class: 'cabeca-aba' }, h('div', {}, h('h1', { tabindex: '-1', id: 'tituloAba', texto: 'Histórico de ações' }),
        h('p', { class: 'descricao', texto: 'Tudo o que foi feito no painel do admin: quem, quando, o quê e por quê. Os registros não podem ser apagados pelo painel.' }))),
      d.trilha.length ? h('div', { class: 'tabela-rolagem', role: 'region', tabindex: '0', 'aria-label': 'Histórico de ações' },
        h('table', {}, h('thead', {}, h('tr', {}, ['Quando', 'Quem', 'Ação', 'Alvo', 'Justificativa'].map(t => h('th', { scope: 'col', texto: t })))),
          h('tbody', {}, d.trilha.map(t => h('tr', {}, h('th', { scope: 'row', texto: dataHora(t.momento) }), h('td', { texto: t.autor }), h('td', { texto: t.acao }), h('td', { texto: t.alvo_tipo }), h('td', { texto: t.justificativa || '—' })))))) :
        h('div', { class: 'vazio' }, h('p', { texto: 'Nenhuma ação registrada ainda.' })));
    foco();
  }

  /* ---------- arquivos (sempre com a credencial; nada fica em link aberto) ---------- */
  async function baixarPlanilha(escopo) {
    try {
      const r = await pedir('/api/exportar?formato=xlsx&escopo=' + escopo, { binario: true });
      const nome = (r.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'painel-gediv.xlsx';
      const url = URL.createObjectURL(await r.blob());
      const link = h('a', { href: url, download: nome }); document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (erro) { if (erro.message !== 'sessao') aviso('erro', erro.message); }
  }
  async function abrirPdf(sha, pagina) {
    try {
      const r = await pedir('/api/pdf/' + sha, { binario: true });
      const url = URL.createObjectURL(new Blob([await r.blob()], { type: 'application/pdf' }));
      window.open(url + '#page=' + pagina, '_blank', 'noopener');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (erro) { if (erro.message !== 'sessao') aviso('erro', erro.message); }
  }

  /* ---------- início ---------- */
  function apiValida(u) {
    try { const x = new URL(u); return x.protocol === 'https:' || ((x.hostname === '127.0.0.1' || x.hostname === 'localhost') && x.protocol === 'http:'); } catch (e) { return false; }
  }
  async function iniciar() {
    $('formLogin').addEventListener('submit', entrar);
    $('sair').addEventListener('click', sair);
    $('dialogoForm').addEventListener('submit', confirmarDialogo);
    $('fecharDialogo').addEventListener('click', () => $('dialogo').close());
    window.addEventListener('hashchange', () => { if (sessao) { aviso(); irAba(location.hash.slice(1)); } });
    try {
      const c = await (await fetch('./config.json', { cache: 'no-store' })).json();
      api = typeof c.api === 'string' ? c.api.replace(/\/+$/, '') : '';
    } catch (e) { api = ''; }
    if (!api || !apiValida(api)) {
      $('telaLogin').hidden = false;
      $('formLogin').querySelectorAll('input, button').forEach(x => { x.disabled = true; });
      aviso('aviso', 'O servidor gerencial ainda não foi configurado. O login só funciona depois que a equipe técnica ligar o servidor e informar o endereço em config.json. Esta página não contém nenhum dado.');
      return;
    }
    const guardada = lerGuardada();
    if (guardada && guardada.token) {
      sessao = guardada;
      try { const s = await pedir('/api/sessao'); guardar({ ...guardada, nome: s.nome, expira_em: s.expira_em }); abrirApp(); return; } catch (e) { if (e.message === 'sessao') return; /* senão cai no login */ }
    }
    mostrarLogin();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
