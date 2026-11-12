# Regras consolidadas da GEDIV — eixos, grupos, subcategorias e indicadores

Data: 10/11/2026. Versão do dicionário: `gediv-2026.11.10-1` (`observatorio/gerencias/gediv/catalogo.py`).

> **Atualização (12/11/2026, dicionário `gediv-2026.11.12-1`)** — regras definitivas da Etapa 02, que prevalecem
> sobre a tabela da seção 2.1:
> - códigos dos 16 grupos: MAG, SSA, GAJ, FAP, AST, ANS, ESP, DPS, SFT, OSPB, GPC, SEI, SAT, ACI, PPGG e INT
>   (`SAUDE` passou a `SSA`, `ESPECIAL` a `ESP`; `INT` incluído como provisório, com expressões a confirmar);
> - "TEC. ADM" e "STF" não têm grupo homologado: o ato fica sem grupo, com a expressão guardada e pendência para
>   a GEDIV (nenhuma equivalência com AST ou SFT é presumida);
> - licença-saúde, vacância e atos de outra gerência ficam FORA DO ESCOPO: registrados na tabela privada
>   `fora_escopo`, nunca em "Outras publicações" nem nos indicadores. A sigla DEREH nunca exclui ato dos dois eixos.

## 1. Fontes e precedência

| # | Fonte | Como foi lida | Uso |
|---|---|---|---|
| 1 | **"Eixos e grupos da GEDIV"** — documento da pasta do projeto no Google Drive | Lido integralmente em 10/11/2026 | Eixos, modalidades, lista de grupos, sete subcategorias, página de outras publicações |
| 2 | **Especificação Funcional V3** (29/10/2026), cópia em `GEMINI-2/docs` | Lida integralmente | Três dimensões de classificação, contrato dos sete indicadores, cenários de aceitação, segurança |
| 3 | **Checklist de 29/10/2026** e **Handoff/auditoria v2.1** (Drive, 10/11/2026) | Lidos: registro de decisões, divergências, histórico de erros, backlog, plano de testes, mapa de preservação | Decisões vigentes, conflitos e defeitos a corrigir |
| 4 | Planilha `Observatorio-GEDIV-Visão-Geral.xlsx` (Drive) — trechos literais de resenhas | Usada só localmente, para conhecer o formato real e medir o classificador | Formato das resenhas; expressões reais dos grupos |
| 5 | Imagens do painel aprovado (Drive) | Vistas | Layout do dashboard |

Quando duas fontes divergem, vale a de número menor; o que é mais recente e mais específico
prevalece sobre o mais antigo. O que nenhuma fonte resolve fica **pendente**, nunca presumido.

## 2. Estrutura fixa

- **Exatamente dois eixos:** Progressão Funcional e Tempo de Serviço/Contribuição.
- **Progressão** tem duas modalidades: **Horizontal** e **Vertical**. Grupo não é eixo; condição
  (Plena, Condicional, Não informada) é dimensão auxiliar.
- Para a Progressão, o documento oficial pede os **grupos do PCCR e a classe**: o sistema extrai
  classe anterior/posterior (Vertical) e nível anterior/atual (Horizontal) quando publicados.
- **Tempo de Serviço** tem exatamente **sete subcategorias**; grupo nunca é atribuído a esse eixo.

### 2.1 Grupos (16, na ordem do documento oficial)

| Código | Nome | Estado | Observação |
|---|---|---|---|
| MAG | Magistério | Confirmada | vista como "Grupo MAG" |
| SAUDE | Saúde | Confirmada | o documento não informa código |
| GAJ | Apoio Judiciário | Confirmada | vista como "GAJ-1700" |
| FAP | Fiscalização Agropecuária | Confirmada | vista como "FAP-1300" |
| AST | Técnicos Administrativos | Confirmada | vista como "Grupo TECNICO ADMINISTRATIVO - AST -" |
| TEC-ADM | Técnicos Administrativos (Tec. Adm) | Confirmada | vista como "Grupo TEC. ADM." |
| ANS | Nível Superior | Provisória | |
| ESPECIAL | Grupo Especial | Provisória | |
| DPS | Divulgação e Promoção | Provisória | |
| SFT | Fazenda · Auditor Fiscal | Confirmada | vista como "profissionais da Fazenda" e "Grupo STF - AUDITOR FISCAL TRIBUTARIO" |
| OSPB | Orquestra Sinfônica | Provisória | |
| GPC | Polícia Civil | Provisória | |
| SEI | Informática | Provisória | |
| SAT | Área Tecnológica | Provisória | |
| ACI | Auditoria e Controle Interno | Provisória | |
| PPGG | (o documento lista só a sigla) | Provisória | |

*Confirmada* = consta do documento oficial **e** a expressão foi vista em resenha real do histórico.
*Provisória* = consta do documento oficial; ainda sem resenha examinada neste projeto.
Nenhum grupo foi acrescentado além dos 16 do documento. Expressão não reconhecida vira
"grupo não informado", com pendência — o sistema não inventa grupo.

### 2.2 Subcategorias de Tempo de Serviço

| Código | Subcategoria |
|---|---|
| TS-01 | Anotação de Tempo de Serviço/Contribuição |
| TS-02 | Desaverbação de Tempo de Serviço |
| TS-03 | Licença para Tratar de Interesses Particulares |
| TS-04 | Desistência de Licença de Interesse Particular |
| TS-05 | Licença Especial |
| TS-06 | Conversão de Licença Especial em Tempo de Serviço |
| TS-07 | Conversão de Férias |

Os códigos TS-01…TS-07 vêm da Especificação V3; os nomes coincidem com o documento oficial.
As sete aparecem sempre no painel. Subcategoria sem registro mostra **"cobertura pendente"**
(e não zero confirmado) enquanto a cobertura do período não estiver validada.

## 3. Identificação em duas camadas

1. **Institucional.** Cada ato (resenha ou portaria) é delimitado e só então se verifica o vínculo:
   - `EXPRESSO`: o ato traz "Gerência Executiva de Concessão (Conc.) de Direitos e Vantagens" ou "GEDIV";
   - `NAO_EXPRESSO`: o ato é da DEREH/SEAD, trata de tema dos dois eixos, mas não menciona a GEDIV.
     Fica sinalizado e **só pode ser conferido com confirmação explícita do vínculo** pelo revisor;
   - ato de **outra gerência** (por exemplo `…/GOCESP/DEREH`) ou de outra secretaria é descartado.
2. **Temática.** Eixo, modalidade ou subcategoria, condição, grupo e resultado são lidos do preâmbulo
   do ato — nunca das linhas dos servidores (o cargo "Técnico Administrativo" não define o grupo).

Palavra-chave é gatilho, não prova: **tudo o que a classificação produz é candidato**.

## 4. Três dimensões independentes

- **Resultado:** Deferido, Indeferido, Não informado (verbos contraditórios no mesmo trecho → não informado).
- **Alteração da publicação:** Original, Retificação, Correção, Republicação (subtipo "por incorreção"),
  Tornado sem efeito. O ato modificador vira **evento**; não vira decisão nova.
- **Refeitos:** ato com ao menos um evento **validado e vinculado** de retificação, correção ou
  republicação. "Tornado sem efeito" é indicador separado e não torna o ato "refeito" por si só.

O sistema **sugere** o ato original quando o evento cita um número de resenha que corresponde a um
único ato da base; a sugestão não conta em nenhum indicador até ser validada por uma pessoa.
Sem correspondência única, o evento fica `PENDENTE_VINCULACAO`.

## 5. Os sete indicadores gerenciais

| Cartão | Unidade | Data usada |
|---|---|---|
| Total de processos | processos distintos das decisões originais | publicação original |
| Total de resenhas | resenhas originais distintas | publicação original |
| Total de decisões individuais | decisões originais | publicação original |
| Deferidos | decisões originais deferidas | publicação original |
| Indeferidos | decisões originais indeferidas | publicação original |
| Refeitos | atos originais com evento validado de retificação/correção/republicação | **publicação do evento** |
| Tornados sem efeito | atos originais com evento validado de "sem efeito" | **publicação do evento** |

- **Só registros conferidos por revisão humana entram nos indicadores.** A visão "Em conferência"
  existe apenas para a gerência, é sempre rotulada como preliminar e não calcula Refeitos nem
  Tornados sem efeito.
- Os cartões não se somam. Clicar em um cartão restringe tabela e gráficos ao universo dele.
- Indicadores de apoio: eventos de alteração validados, eventos sem vínculo, decisões aguardando
  revisão, pendentes sem GEDIV expressa, conferidas e rejeitadas.

## 6. Divergências resolvidas

| Divergência | Decisão adotada | Fundamento |
|---|---|---|
| Dois ou três eixos (painéis antigos tratavam Horizontal e Vertical como eixos) | **Dois eixos**; Horizontal/Vertical são modalidades | Documento oficial; V3; DEC-003 |
| Sete categorias ou oitava ("Abono de Permanência", presente no código V2) | **Sete.** Abono é reconhecido só como *conceito candidato* e aparece em "Outras publicações", fora dos indicadores | Documento oficial lista sete; DEC-013 em aberto |
| Catálogo de grupos (V3: 4 confirmados + 3 sujeitos a evidência; Gemini: 15 códigos; documento: 16) | **Os 16 do documento oficial**, com estado Confirmada/Provisória | Documento oficial é mais recente e específico |
| AST × Tec. Adm | Mantidos **separados**, como no documento | Sem autorização para fundir |
| STF × SFT | A expressão "STF - Auditor Fiscal Tributário" é associada a SFT; a expressão literal fica guardada | Precisa de confirmação da GEDIV (pendência) |
| Resenha só com DEREH conta como GEDIV? | Não automaticamente: vínculo `NAO_EXPRESSO`, confirmação humana obrigatória | V3 seção 3; DEC-004 |
| Cartões do painel (imagem aprovada mostra 6; V3 define 7) | **Os 7 da V3** | V3 é o contrato dos indicadores |
| Nome por extenso da GEDIV (a imagem do painel traz "Desenvolvimento do Servidor") | "Gerência Executiva de Concessão de Direitos e Vantagens" | É a expressão das próprias resenhas |
| Página extra pedida no documento oficial | Aba **"Outras publicações"**: Republicado por incorreção, Portaria, Ato Normativo, Alterações na Lei | Documento oficial |
| Reaproveitar ou reescrever | Base Claude mantida; do Gemini e do V2 aproveitaram-se regras e formatos, não o código | Instrução desta entrega; DEC-010 |

## 7. Pendências de regra (dependem da GEDIV)

1. Confirmar em publicação os nove grupos *provisórios* e a denominação de PPGG.
2. Confirmar a equivalência STF/SFT e a relação AST/Tec. Adm.
3. Decidir o tratamento de "Abono de Permanência" (DEC-013).
4. Período histórico da carga: 2025 ou 2026 (DEC-011). O sistema não fixa período.
5. Confirmar que as resenhas de Progressão Vertical sem menção à GEDIV pertencem à gerência
   (203 dos 329 trechos reais examinados estão nessa situação).
