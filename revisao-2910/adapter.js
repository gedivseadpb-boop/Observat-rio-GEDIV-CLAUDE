/* Adaptador de agregados: nunca fabrica linhas individuais a partir de totais. */
(function(root){'use strict';
const M=root.GedivModelo;
const groupCodes={SAUDE:'SSA','GAJ-1700':'GAJ','FAP-1300':'FAP','TEC-ADM':'AST','ANS-900':'ANS',ESPECIAL:'ESP','DPS-1600':'DPS',FAZENDA:'SFT'};
function state(s){return {...M.novoEstado(),inicio:s.from,fim:s.to,eixo:s.axis==='tempo'?'TEMPO_SERVICO':s.axis==='progressao'?'PROGRESSAO':'',modalidade:(s.modality||'').toUpperCase(),grupo:groupCodes[s.group]||s.group,subcategorias:[...s.category],resultado:s.merit||(['deferidos','indeferidos'].includes(s.card)?s.card:''),tipo:['refeitos','semEfeito'].includes(s.card)?s.card:''};}
function query(data,s){
 const q=state(s);let issue=M.selectionIssue(q)||M.coverageIssue(data,q);
 if(s.view==='outras')issue='Outros benefícios não estão discriminados na projeção pública.';
 if(['processes','resenhas'].includes(s.card))issue='Esta contagem distinta não está disponível na projeção pública.';
 let cells=issue?[]:M.searchCells(M.filterCells(data.celulas,q),s.query,data.catalogo);
 // Busca também restringe indicadores; o resumo da base inteira não representa a busca.
 let decisions=issue?M.vazio():s.query?M.sumMetrics(cells.map(c=>c.decisoes)):M.decisionMetric(data,q,cells);
 return {state:q,issue,cells,decisions,atos:issue?M.vazio():s.query?M.vazio():M.qualityMetric(data,q,cells,'atos')};
}
root.GedivRevisao={state,query,groupCodes};
if(typeof module!=='undefined')module.exports=root.GedivRevisao;
})(typeof window!=='undefined'?window:globalThis);
