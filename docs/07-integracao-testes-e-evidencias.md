# Integração, testes e evidências — entrega de 10/11/2026

> **Atualização (10/11/2026, fechamento):** depois deste documento o fluxo foi executado sobre quatro PDFs
> oficiais. As seções 3 e 5 abaixo descrevem a situação **anterior** a esse teste; o estado atual, os
> defeitos reais corrigidos e o fechamento de RISCO-013 e LIMITE-014 estão em
> [`08-validacao-com-pdf-oficial.md`](08-validacao-com-pdf-oficial.md). A suíte passou a ter 155 testes.

Versão 0.3.0. Este documento separa o que foi **executado e comprovado** do que continua **pendente**.

## 1. Fluxo implementado

```
DOE/PB ──► PDF ──► acervo (SHA-256) ──► leitura por colunas / OCR ──► classificação GEDIV ──► banco privado (SQLite)
 coleta em lotes        nucleo                 leitura                   gerencias/gediv            nucleo/banco
 ou importação manual                                                           │
                                                                                ▼
        dashboard web ◄── API (perfis público e gerência) ◄── indicadores ◄── revisão humana + auditoria
            web/estatico        web/servidor                    painel            revisao
```

| Etapa | Comando | Situação |
|---|---|---|
| Obter PDFs nas fontes | `python -m observatorio.coleta …` | Código e testes prontos; **acesso real às fontes não comprovado** (seção 5) |
| Importar PDFs fornecidos | `python -m observatorio.operacao executar PASTA` | Funcionando (teste ponta a ponta) |
| Ler texto por colunas / OCR | `python -m observatorio.leitura processar [--refazer]` | Funcionando com PDFs sintéticos |
| Classificar | `python -m observatorio.gerencias.gediv classificar` | Funcionando; medido também sobre texto real |
| Revisar | painel web ou `python -m observatorio.revisao …` | Funcionando, com trilha de auditoria |
| API e dashboard | `python -m observatorio.web --dados PASTA` | Funcionando; conferido em navegador |

## 2. O que veio de cada origem

**Do projeto Claude (base, mantida):** coleta em lotes com trava por fonte, acervo por SHA-256,
banco SQLite com migração de esquema, leitura por colunas, OCR, qualidade por página, sonda de
acesso, testes sem internet e a regra de documentar cada afirmação com onde foi testada.

**Do GEMINI-2 (aproveitado como regra, reescrito nesta arquitetura):**
- catálogo `src/classificacao/catalogo.py`: códigos TS-01…TS-07, expressões dos grupos, condição Plena/Condicional;
- `src/robo.py`: padrões de processo, resenha e cabeçalho da GEDIV; ordem "caso específico antes do genérico"
  nas subcategorias; resultado contraditório = não informado; isolamento de blocos por unidade;
- `shared/dashboard-model.mjs`: semântica dos cartões (escopo conferido/pendente, Refeitos por evento
  vinculado, clique no cartão restringe o universo) — agora calculada **no servidor**, numa única projeção;
- `dashboard/`: layout aprovado (filtros recolhíveis à esquerda, cartões e gráficos ao centro, tabela e
  detalhe à direita), alternância "por resenha / por processo", logotipo, proteção contra fórmulas na exportação;
- `docs/`: Especificação V3 e checklist, que são a fonte dos cenários de aceitação dos testes.

**Não aproveitado do GEMINI-2, e por quê:** estado em arquivo JSON único (substituído por banco);
dependência de PyMuPDF (AGPL) e `requests`/`bs4`; cliente/gateway para um backend externo que nunca
respondeu (HTTP 403 registrado); dados embutidos no HTML; duplicação `dashboard/` × `painel-interativo/`.

**Do Drive:** regras (documento 06), o formato real das resenhas e os defeitos apontados na
auditoria v2.1, corrigidos nesta entrega:

| Achado da auditoria | Correção | Teste |
|---|---|---|
| BUG-009 — 429 era repetido e havia tentativa em endereço alternativo após recusa | 429 deixou de ser transitório; 403/429 encerram na primeira ocorrência, sem alternativa | `test_bug009_*` (conta as requisições) |
| BUG-010 — piloto de tamanho 1 dividia por zero | tratado | `test_bug010_*` |
| BUG-011 — listagem além do limite de páginas era dada como varrida | varredura registrada como `LISTAGEM_PARCIAL` e relida | `test_bug011_*` |
| BUG-012 — robots.txt negado (403/429) era tratado como ausente | situação `RECUSADO`; o lote não roda | `test_bug012_*` |
| BUG-015 — releitura com erro apagava o texto já lido | leitura anterior preservada; falha registrada | `test_bug015_*` |
| BUG-016 — leitura com erro/pendência não voltava à fila | `processar --refazer` | `test_bug016_*` |
| BUG-017 — dia "COMPLETO" sem todas as fontes varridas | `BAIXADO_SEM_VARREDURA_COMPLETA` | `test_bug017_*` |
| RISCO-013 (página mista texto+imagem) e LIMITE-014 (PDF corrompido com marcadores) | **não tratados** — pendentes | — |

## 3. Testes executados em 10/11/2026

Comando: `python -m unittest discover -s tests -t .` — **142 testes, 141 aprovados, 1 pulado**
(OCR: o Tesseract não está instalado no ambiente de desenvolvimento; roda no GitHub Actions/Linux).
Registro completo: `docs/evidencias/testes-2026-11-10.txt`.

| Arquivo | Testes | Assunto |
|---|---|---|
| `test_nucleo.py`, `test_coleta.py`, `test_lotes.py`, `test_leitura.py` | 71 | já existentes: PDF, acervo, banco, rede, coleta, lotes, leitura, OCR |
| `test_gediv.py` | 33 | dicionário (2 eixos, 16 grupos, 7 subcategorias), duas camadas, eventos, formatos vistos em texto real |
| `test_painel.py` | 26 | candidato ≠ conferido, regras de revisão, trilha, os sete indicadores, filtros, exportação, API e perfis |
| `test_ponta_a_ponta.py` | 12 | PDF → acervo → leitura → classificação → revisão → API; regressões da auditoria |

Todos usam **dados sintéticos** (pessoas, matrículas e processos fictícios). Comprovam a lógica,
não o comportamento com o Diário real.

### Cenários de aceitação da Especificação V3 cobertos

Resenha com 3 linhas e 2 processos → 1 resenha, 3 decisões, 2 processos · ato original de uma data
alterado em outra → conta em Refeitos na data do evento · ato só tornado sem efeito → Refeitos 0,
Sem efeito 1 · evento sem ato original identificável → pendente, não eleva indicador · palavra-chave
sem vínculo institucional → fora dos totais · filtro Progressão > Horizontal > MAG · subcategoria sem
registro → "cobertura pendente" · usuário sem credencial → só agregados, API bloqueia linhas e exportação ·
mesmo processo em original e republicação → 1 processo.

## 4. Evidências

| Evidência | Arquivo | O que comprova |
|---|---|---|
| Testes automatizados | `evidencias/testes-2026-11-10.txt` | 141 aprovados, 1 pulado |
| Fluxo completo com PDFs sintéticos | `evidencias/fluxo-demonstracao-2026-11-10.json` | 3 PDFs → 5 páginas lidas (2 em duas colunas) → 14 atos, 56 decisões, 2 eventos, 3 atos de outra gerência descartados |
| Dashboard em navegador | `evidencias/painel/01…06-*.png` | consulta pública só com agregados; visão da gerência com tabela, detalhe e trilha; cartão clicável; dados preliminares rotulados; outras publicações; sete subcategorias sempre visíveis |
| Classificador sobre **texto real** | `evidencias/validacao-texto-real-2026-11-10.json` | ver abaixo |

As telas foram geradas sobre a base de **demonstração** (`python -m observatorio.operacao demonstracao`),
com documentos sintéticos. Os números nelas não são publicações reais.

### Medição sobre texto real (não é validação com PDF)

A planilha do Drive traz o trecho literal de 330 linhas de resenhas de 13 edições (02/09 a 10/10/2026).
O classificador foi executado sobre esses trechos e comparado com o que a planilha registrava:

| Campo | Coincidência |
|---|---|
| Resenha reconhecida como ato | 329 de 329 |
| Eixo | 329 de 329 |
| Modalidade (Horizontal/Vertical) | 295 de 295 |
| Subcategoria de Tempo de Serviço | 34 de 34 |
| Número da resenha, processo, matrícula, resultado | 329 de 329 cada |
| Nome do servidor | 308 de 329 |
| Portaria "tornar sem efeito" reconhecida como evento | 1 de 1 |

Os 21 nomes diferentes estão em linhas de tabela quebradas em duas; esses registros saem com o aviso
`linha_quebrada` para o revisor. A medição revelou cinco defeitos, corrigidos e cobertos por teste
(caractere invisível no meio de palavras, célula quebrada, nota "Publicado no D.O.E.", separador de
milhar, variante "STF").

**Limites desta medição:** o texto já estava extraído na planilha — ela **não** testa a leitura de PDF,
a separação de colunas, o OCR nem a coleta. A planilha tem dados pessoais e ficou fora do repositório.

## 5. O que NÃO foi comprovado

| Item | Situação | Motivo |
|---|---|---|
| Teste com **PDF oficial real** | **Não executado** | Nenhum PDF oficial esteve disponível: as fontes não responderam e a pasta do Drive não contém PDFs |
| Acesso automático a `auniao.pb.gov.br` e `cge.pb.gov.br` | **Não comprovado** | Em 10/11/2026, com os servidores liberados na rede deste ambiente, a conexão foi encerrada sem resposta após ~10 s — mesmo sintoma das três medições anteriores a partir de datacenters fora do Brasil |
| OCR em documento real | Não executado | sem documento |
| Revisão por pessoas da GEDIV | Não iniciada | nenhum registro real foi conferido |
| Carga histórica, rotina diária, hospedagem | Não iniciadas | dependem do acesso às fontes e de decisão institucional |

## 6. Segurança e privacidade

- O repositório não contém PDFs, banco, credenciais nem dados pessoais; as fixtures são fictícias.
- A API entrega dados individualizados, trechos, PDFs e exportações **somente** com a credencial da
  gerência; sem ela, apenas agregados de registros conferidos. Testado (401/403).
- A credencial vem de `GEDIV_TOKEN_GERENCIA` ou é gerada a cada inicialização; o servidor escuta em
  `127.0.0.1` por padrão. Exportações ficam na trilha de auditoria.
- **Limite conhecido:** há uma credencial única para a gerência, não usuários individuais; o nome do
  responsável é declarado em cada revisão. Publicar na internet exige HTTPS e autenticação
  institucional à frente do servidor — não foi feito nem deve ser feito sem autorização.

## 7. Pendências reais

1. **Um PDF oficial** (por exemplo, as edições de 02/10 e 04/11/2026) para a primeira validação real:
   `python -m observatorio.operacao executar PASTA` e conferência humana das páginas da SEAD.
2. **Executor com acesso às fontes** (rede brasileira/SEAD) para rodar sonda, piloto e lotes.
3. **Decisões de regra** listadas no documento 06, seção 7.
4. RISCO-013 e LIMITE-014 da auditoria; nomes em linhas quebradas (hoje sinalizados, não resolvidos).
5. Usuários individuais, HTTPS e hospedagem; backup cifrado; rotina diária.
6. A pasta do Drive permite leitura por qualquer pessoa com o link e contém planilha com dados
   pessoais: recomenda-se restringir o acesso (item P-01 do backlog da auditoria).
