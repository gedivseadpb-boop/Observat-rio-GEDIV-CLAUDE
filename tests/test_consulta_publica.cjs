'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const M=require('../painel-publico/modelo.js');
const data=require('../painel-publico/dados.json');
const selection=patch=>({...M.novoEstado(),...patch});

test('snapshot real mantém contrato, unidades e faixas sem reconstruir dados privados',()=>{
  assert.equal(M.validateProjection(data),data);
  const cells=M.filterCells(data.celulas,selection({}));
  assert.equal(cells.length,data.celulas.length);
  assert.equal(M.metricLabel(M.decisionMetric(data,selection({}),cells)),M.metricLabel(M.sumMetrics([data.resumo.conferidos,data.resumo.provisorios])));
  assert.notEqual(M.metricLabel(M.sumMetrics(cells.map(c=>c.decisoes))),M.metricLabel(M.decisionMetric(data,selection({}),cells)));
});

test('um dia nunca herda os agregados de seu mês e datas inválidas não passam',()=>{
  for(const s of [selection({inicio:'2026-11-14',fim:'2026-11-14'}),selection({inicio:'2026-11-01',fim:'2026-11-14'}),selection({inicio:'2026-02-30'}),selection({inicio:'2026-12-01',fim:'2026-11-30'})]){
    assert.ok(M.selectionIssue(s));
    assert.deepEqual(M.filterCells(data.celulas,s),[]);
    assert.equal(M.metricLabel(M.decisionMetric(data,s,[])),'—');
  }
  const month=selection({inicio:'2026-11-01',fim:'2026-11-30'});
  assert.equal(M.selectionIssue(month),'');
  assert.ok(M.filterCells(data.celulas,month).every(c=>c.periodo==='2026-11'));
});

test('filtros não disponíveis não são ignorados silenciosamente nem viram zero',()=>{
  for(const s of [selection({resultado:'DEFERIDO'}),selection({tipo:'RETIFICACAO'}),selection({coberturaFiltro:'quarentena'}),selection({situacao:'pendente'})]){
    assert.ok(M.selectionIssue(s));
    assert.deepEqual(M.filterCells(data.celulas,s),[]);
    assert.equal(M.numberBounds(M.decisionMetric(data,s,[])),null);
  }
});

test('células TS suprimidas não viram zero, resumo geral do eixo é preservado',()=>{
  const s=selection({eixo:'TEMPO_SERVICO'}),cells=M.filterCells(data.celulas,s);
  assert.deepEqual(cells,[]);
  assert.ok(M.numberBounds(M.decisionMetric(data,s,cells)));
  assert.equal(M.metricLabel(M.decisionMetric(data,{...s,subcategorias:['TS-01']},cells)),'—');
});

test('zero conhecido de conferidos permanece distinto de uma célula não divulgada',()=>{
  const s=selection({situacao:'conferido'});
  assert.equal(M.decisionMetric(data,s,M.filterCells(data.celulas,s)).valor,0);
  assert.equal(M.metricLabel(M.sumMetrics([])),'—');
  assert.equal(M.metricLabel(M.qualityMetric(data,s,[],'atos')),'—');
  assert.equal(M.metricLabel(M.qualityMetric(data,s,[],'publicacoes_pendentes')),'—');
});

test('período mensal fora da cobertura não transforma ausência de base em zero conferido',()=>{
  const s=selection({inicio:'2026-12-01',fim:'2026-12-31',situacao:'conferido'});
  const cells=M.filterCells(data.celulas,s);
  assert.match(M.coverageIssue(data,s),/fora da cobertura/);
  assert.equal(M.metricLabel(M.decisionMetric(data,s,cells)),'—');
  assert.equal(M.metricLabel(M.qualityMetric(data,s,cells,'conferidos')),'—');
});

test('grupos e múltiplos serviços selecionam somente suas dimensões oficiais',()=>{
  const cells=M.filterCells(data.celulas,selection({eixo:'PROGRESSAO',modalidade:'HORIZONTAL',grupo:'GAJ'}));
  assert.ok(cells.length);
  assert.ok(cells.every(c=>c.grupo==='GAJ'&&c.modalidade==='HORIZONTAL'));
  assert.deepEqual(M.filterCells(data.celulas,selection({eixo:'TEMPO_SERVICO',subcategorias:['TS-02','TS-07']})),[]);
});

test('percentual precisa de denominador verificável e mantém intervalos',()=>{
  assert.equal(M.shareInterval(M.vazio(),[]),null);
  const a={minimo:5,maximo:9,valor:null,rotulo:'5–9'},b={minimo:10,maximo:14,valor:null,rotulo:'10–14'};
  assert.deepEqual(M.shareInterval(a,[a,b]),{min:26,max:48});
  assert.equal(M.shareInterval(a,[a,M.vazio()]),null);
  assert.equal(M.shareLabel(null),'—');
});

test('ordenação, busca e paginação preservam todos os agregados sem mutar a fonte',()=>{
  const original=JSON.stringify(data.celulas),found=M.searchCells(data.celulas,'judiciario',data.catalogo);
  assert.ok(found.length&&found.every(c=>c.grupo==='GAJ'));
  assert.equal(M.pagination(data.celulas,1,5).items.length,1);
  assert.equal(M.pagination(data.celulas,999,5).page,1);
  assert.equal(M.pagination(data.celulas,0,10000).items.length,data.celulas.length);
  const sorted=M.sortCells(data.celulas,'decisoes',1);
  assert.ok(sorted[0].decisoes.minimo<=sorted.at(-1).decisoes.minimo);
  assert.equal(JSON.stringify(data.celulas),original);
});

test('exportação usa somente células selecionadas e protege contra fórmula CSV',()=>{
  const cells=M.filterCells(data.celulas,selection({grupo:'GAJ'})),rows=M.cellsToRows(cells,data.catalogo);
  assert.equal(rows.length,cells.length+1);
  assert.ok(M.cellsToCsv(cells,data.catalogo).includes('Apoio Judiciário'));
  assert.equal(M.csvValue('=1+1'),'"\'=1+1"');
  assert.ok(!M.cellsToCsv(cells,data.catalogo).includes('matricula'));
});

test('contrato recusa campos privados, duplicatas e dimensões cruzadas',()=>{
  const changes=[d=>d.celulas[0].servidor='MARCADOR FICTICIO',d=>d.celulas.push({...d.celulas[0]}),d=>d.celulas[0].subcategoria='TS-01',d=>d.celulas[0].decisoes.valor=42,d=>d.catalogo.grupos.pop()];
  for(const change of changes){const d=structuredClone(data);change(d);assert.throws(()=>M.validateProjection(d));}
});
