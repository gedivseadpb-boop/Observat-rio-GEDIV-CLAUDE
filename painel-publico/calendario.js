/* Seletor de datas público GEDIV. Não consulta nem deriva dados individuais. */
(function (root) {
  'use strict';
  const DAYS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
  const MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
  const iso = d => d.toISOString().slice(0, 10);
  const parse = s => new Date(s + 'T12:00:00Z');
  const valid = s => /^20\d\d-\d\d-\d\d$/.test(s || '') && Number.isFinite(parse(s).getTime()) && iso(parse(s)) === s;
  const label = s => valid(s) ? s.split('-').reverse().join('/') : 'Não definida';
  const plusDays = (s, n) => { const d = parse(s); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
  const monthStart = s => s.slice(0, 7) + '-01';
  const plusMonths = (s, n) => {
    const d = parse(monthStart(s)); d.setUTCMonth(d.getUTCMonth() + n); return iso(d);
  };
  const endMonth = s => plusDays(plusMonths(s, 1), -1);
  function today() {
    const parts = new Intl.DateTimeFormat('en', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
    const get = type => parts.find(x => x.type === type).value;
    return get('year') + '-' + get('month') + '-' + get('day');
  }
  let active = null;

  function abrir(options = {}) {
    if (active?.open) { active.focus(); return; }
    if (active) { active.remove(); active = null; }
    const previous = document.activeElement;
    const initial = valid(options.inicio) ? options.inicio : '';
    const final = valid(options.fim) ? options.fim : '';
    const first = valid(options.primeiraData) ? options.primeiraData : '';
    const last = valid(options.ultimaData) ? options.ultimaData : '';
    let start = initial, end = final, selectingEnd = false;
    let view = monthStart(initial || last || today()), focused = initial || last || today();
    const dialog = document.createElement('dialog');
    dialog.className = 'gediv-calendar-dialog'; dialog.id = 'gedivCalendario';
    dialog.setAttribute('aria-labelledby', 'gedivCalendarioTitulo');
    dialog.setAttribute('aria-describedby', 'gedivCalendarioAjuda');
    dialog.innerHTML = '<div class="gediv-cal-heading"><div><h2 id="gedivCalendarioTitulo">Escolher período</h2><p id="gedivCalendarioAjuda">Escolha a data inicial e a final. As datas só serão usadas ao aplicar.</p></div><button type="button" class="gediv-cal-close" data-cal-close aria-label="Fechar calendário sem aplicar">✕</button></div>' +
      '<div class="gediv-cal-shortcuts" aria-label="Atalhos de período">' + [
        ['hoje', 'Hoje'], ['ontem', 'Ontem'], ['sete', 'Últimos 7 dias'], ['trinta', 'Últimos 30 dias'],
        ['mes', 'Este mês'], ['anterior', 'Mês anterior'], ['ano', 'Este ano'], ['tudo', 'Toda a base disponível']
      ].map(([key, name]) => '<button type="button" data-cal-shortcut="' + key + '" aria-pressed="false">' + name + '</button>').join('') + '</div>' +
      '<div class="gediv-cal-inputs"><label>Data inicial<input type="date" id="gedivCalInicio" aria-label="Data inicial do período" min="2000-01-01" max="2099-12-31"></label><span aria-hidden="true">→</span><label>Data final<input type="date" id="gedivCalFim" aria-label="Data final do período" min="2000-01-01" max="2099-12-31"></label></div>' +
      '<div class="gediv-cal-nav"><button type="button" data-cal-move="-12" aria-label="Ano anterior">«</button><button type="button" data-cal-move="-1" aria-label="Mês anterior">‹</button>' +
      '<label><span class="sr-only">Mês do calendário</span><select id="gedivCalMes" aria-label="Mês do calendário">' + MONTHS.map((m, i) => '<option value="' + (i + 1) + '">' + m + '</option>').join('') + '</select></label>' +
      '<label><span class="sr-only">Ano do calendário</span><input id="gedivCalAno" type="number" min="2000" max="2099" aria-label="Ano do calendário"></label>' +
      '<button type="button" data-cal-move="1" aria-label="Próximo mês">›</button><button type="button" data-cal-move="12" aria-label="Próximo ano">»</button></div>' +
      '<div class="gediv-cal-months" id="gedivCalMeses"></div><p class="gediv-cal-keyboard">Teclado: setas mudam o dia; Home/End mudam a semana; Page Up/Down mudam o mês; Enter seleciona.</p>' +
      '<div class="gediv-cal-message" id="gedivCalMensagem" role="status" aria-live="polite"></div>' +
      '<p class="gediv-cal-coverage">Cobertura documental informada: <b>' + (first && last ? label(first) + ' a ' + label(last) : 'não disponível') + '</b>. O intervalo não comprova cobertura de cada dia. Horário de Brasília.</p>' +
      '<div class="gediv-cal-actions"><button type="button" data-cal-clear>Limpar</button><span></span><button type="button" data-cal-close>Cancelar</button><button type="button" class="gediv-cal-apply" id="gedivCalAplicar">Aplicar período</button></div>';
    document.body.appendChild(dialog); active = dialog;
    const $ = id => dialog.querySelector('#' + id);

    function message() {
      const apply = $('gedivCalAplicar');
      const invalid = (start && !valid(start)) || (end && !valid(end));
      apply.disabled = !!invalid || (!!start && !!end && end < start) || (!!start !== !!end);
      let text;
      if (invalid) text = 'Confira as datas informadas.';
      else if (!!start !== !!end) text = 'Informe as duas datas para aplicar o período.';
      else if (start && end && end < start) text = 'A data final deve ser igual ou posterior à data inicial.';
      else if (!start && !end) text = 'Toda a base disponível será consultada. Nenhum filtro de período será aplicado.';
      else {
        const partial = !start.endsWith('-01') || end !== endMonth(end);
        text = (start === end ? 'Dia selecionado: ' + label(start) + '. ' : 'Intervalo: ' + label(start) + ' a ' + label(end) + '. ');
        if (start > today() || end > today()) text += 'Há datas futuras; isso não comprova publicações nem cobertura. ';
        if ((last && start > last) || (first && end < first)) text += 'Este período está fora da cobertura documental informada. ';
        else if ((first && start < first) || (last && end > last)) text += 'Parte do período está fora da cobertura documental informada. ';
        text += partial ? 'A projeção é mensal: este recorte não permite calcular indicadores diários. As datas serão preservadas; consulte o mês completo para ver agregados.' : 'Serão consultados os agregados mensais publicáveis; a cobertura pode ser parcial.';
      }
      if (selectingEnd) text = 'Agora escolha a data final, ou aplique para consultar somente o dia escolhido. ' + text;
      $('gedivCalMensagem').textContent = text;
    }
    function render(focusDate) {
      $('gedivCalInicio').value = start; $('gedivCalFim').value = end;
      $('gedivCalMes').value = String(parse(view).getUTCMonth() + 1);
      $('gedivCalAno').value = String(parse(view).getUTCFullYear());
      $('gedivCalMeses').innerHTML = [view, plusMonths(view, 1)].map((m, index) => {
        const date = parse(m), offset = date.getUTCDay(), count = parse(endMonth(m)).getUTCDate();
        let html = '<section class="gediv-cal-month' + (index ? ' gediv-cal-second' : '') + '" aria-label="' + MONTHS[date.getUTCMonth()] + ' de ' + date.getUTCFullYear() + '"><h3>' + MONTHS[date.getUTCMonth()] + ' ' + date.getUTCFullYear() + '</h3><div class="gediv-cal-weekdays" aria-hidden="true">' + DAYS.map(d => '<span>' + d + '</span>').join('') + '</div><div class="gediv-cal-days" role="group" aria-label="Dias de ' + MONTHS[date.getUTCMonth()] + '">';
        html += Array.from({ length: offset }, () => '<span aria-hidden="true"></span>').join('');
        html += Array.from({ length: count }, (_, i) => {
          const day = m.slice(0, 7) + '-' + String(i + 1).padStart(2, '0');
          const chosen = day === start || day === end, between = start && end && day > start && day < end;
          const current = day === today();
          return '<button type="button" data-cal-date="' + day + '" tabindex="' + (day === focused ? '0' : '-1') + '" class="' + (chosen ? 'selected ' : '') + (between ? 'in-range ' : '') + (current ? 'is-today' : '') + '" aria-label="' + label(day) + (day === start ? ', início selecionado' : '') + (day === end ? ', fim selecionado' : '') + '" aria-pressed="' + (chosen || !!between) + '"' + (current ? ' aria-current="date"' : '') + '>' + (i + 1) + '</button>';
        }).join('');
        return html + '</div></section>';
      }).join('');
      // Um dia acessível pelo Tab em cada mês, mesmo após navegação pelos seletores.
      dialog.querySelectorAll('.gediv-cal-month').forEach(month => {
        if (!month.querySelector('[tabindex="0"]')) month.querySelector('[data-cal-date]')?.setAttribute('tabindex', '0');
      });
      message();
      if (focusDate) dialog.querySelector('[data-cal-date="' + focusDate + '"]')?.focus();
    }
    function resetShortcuts(key = '') {
      dialog.querySelectorAll('[data-cal-shortcut]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.calShortcut === key)));
    }
    function choose(day) {
      resetShortcuts();
      if (!selectingEnd) { start = end = day; selectingEnd = true; }
      else { if (day < start) { end = start; start = day; } else end = day; selectingEnd = false; }
      focused = day; render(day);
    }
    dialog.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button) return;
      if (button.hasAttribute('data-cal-close')) { dialog.close(); return; }
      if (button.hasAttribute('data-cal-clear')) { start = end = ''; selectingEnd = false; resetShortcuts('tudo'); render(); return; }
      if (button.dataset.calDate) { choose(button.dataset.calDate); return; }
      if (button.dataset.calMove) {
        const next = plusMonths(view, Number(button.dataset.calMove));
        if (next >= '2000-01-01' && next <= '2099-11-01') { view = next; focused = view; render(); }
        return;
      }
      if (button.dataset.calShortcut) {
        const key = button.dataset.calShortcut, t = today(); selectingEnd = false;
        if (key === 'tudo') start = end = '';
        else if (key === 'hoje') start = end = t;
        else if (key === 'ontem') start = end = plusDays(t, -1);
        else if (key === 'sete') { start = plusDays(t, -6); end = t; }
        else if (key === 'trinta') { start = plusDays(t, -29); end = t; }
        else if (key === 'mes') { start = monthStart(t); end = endMonth(t); }
        else if (key === 'anterior') { start = plusMonths(t, -1); end = endMonth(start); }
        else if (key === 'ano') { start = t.slice(0, 4) + '-01-01'; end = t.slice(0, 4) + '-12-31'; }
        if (start) { view = monthStart(start); focused = start; }
        resetShortcuts(key); render(); return;
      }
      if (button.id === 'gedivCalAplicar' && !button.disabled) {
        const value = { inicio: start, fim: end };
        dialog.close(); if (typeof options.onApply === 'function') options.onApply(value);
      }
    });
    dialog.addEventListener('change', event => {
      if (['gedivCalInicio', 'gedivCalFim'].includes(event.target.id)) {
        start = $('gedivCalInicio').value; end = $('gedivCalFim').value; selectingEnd = false;
        resetShortcuts(); const target = event.target.value;
        if (valid(target)) { view = monthStart(target); focused = target; }
        render();
      }
      if (['gedivCalMes', 'gedivCalAno'].includes(event.target.id)) {
        const year = Number($('gedivCalAno').value), month = Number($('gedivCalMes').value);
        if (Number.isInteger(year) && year >= 2000 && year <= 2099 && month >= 1 && month <= 12) {
          view = year + '-' + String(month).padStart(2, '0') + '-01'; focused = view; render();
        }
      }
    });
    dialog.addEventListener('keydown', event => {
      const day = event.target.dataset.calDate;
      if (!day) return;
      let next = day;
      if (event.key === 'ArrowRight') next = plusDays(day, 1);
      else if (event.key === 'ArrowLeft') next = plusDays(day, -1);
      else if (event.key === 'ArrowDown') next = plusDays(day, 7);
      else if (event.key === 'ArrowUp') next = plusDays(day, -7);
      else if (event.key === 'Home') next = plusDays(day, -parse(day).getUTCDay());
      else if (event.key === 'End') next = plusDays(day, 6 - parse(day).getUTCDay());
      else if (event.key === 'PageUp' || event.key === 'PageDown') {
        const step = (event.key === 'PageUp' ? -1 : 1) * (event.shiftKey ? 12 : 1);
        const m = plusMonths(day, step);
        next = m.slice(0, 7) + '-' + String(Math.min(parse(day).getUTCDate(), parse(endMonth(m)).getUTCDate())).padStart(2, '0');
      } else return;
      event.preventDefault();
      if (next < '2000-01-01' || next > '2099-12-31') return;
      focused = next;
      const mobile = root.matchMedia('(max-width: 680px)').matches;
      const shownThrough = mobile ? view.slice(0, 7) : plusMonths(view, 1).slice(0, 7);
      if (next.slice(0, 7) < view.slice(0, 7) || next.slice(0, 7) > shownThrough) view = monthStart(next);
      render(next);
    });
    dialog.addEventListener('close', () => {
      if (active !== dialog) { dialog.remove(); return; }
      active = null; dialog.remove();
      if (previous && previous.isConnected) previous.focus({ preventScroll: true });
    }, { once: true });
    render(); dialog.showModal(); $('gedivCalInicio').focus();
  }
  root.GedivCalendario = { abrir };
})(window);
