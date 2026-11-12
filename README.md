# Painel Diário Oficial | GEDIV

Observatório automatizado das publicações do Diário Oficial do Estado da Paraíba relacionadas à
Gerência Executiva de Concessão de Direitos e Vantagens (GEDIV/SEAD-PB).

Dois eixos: **Progressão Funcional** (modalidades Horizontal e Vertical, por grupo do PCCR) e **Tempo de Serviço/Contribuição** (sete subcategorias).

Este é o repositório oficial. Dos projetos anteriores (GEMINI-2, V2) foram aproveitadas regras,
formatos e o layout aprovado do painel; ver `docs/07`.

## Situação (10/11/2026, versão 0.4.0)

O fluxo completo está implementado e foi executado de ponta a ponta com documentos sintéticos e,
em 10/11/2026, com **quatro PDFs oficiais** (edições de 01, 02, 03 e 06/10/2026 — ver [docs/08](docs/08-validacao-com-pdf-oficial.md)):

```
DOE/PB → PDF → leitura por colunas/OCR → classificação GEDIV → banco privado → API → dashboard
```

| Parte | Código | Testes automatizados (sintéticos) | Validação com documento oficial | Operação efetiva |
|---|---|---|---|---|
| Coleta em lotes, por fonte | Pronto | Aprovados | **Não** (fontes sem resposta) | **Não** |
| Importação manual de PDFs | Pronto | Aprovados | **Executada** em 4 edições (hash da de 02/10 igual à referência) | **Não** |
| Leitura por colunas, OCR, qualidade | Pronto | Aprovados | **Executada**: 172 páginas, 7 defeitos reais corrigidos | **Não** |
| Classificação GEDIV (2 eixos, 16 grupos, 7 subcategorias) | Pronto | Aprovados | **Executada**: 7 resenhas, 49 decisões; amostra conferida pelo desenvolvedor | **Não** |
| Revisão humana com trilha de auditoria | Pronto | Aprovados | **Não** (nenhum registro real conferido pela GEDIV) | **Não** |
| API e dashboard (7 indicadores, filtros, gráficos, exportações) | Pronto | Aprovados; conferido em navegador | **Executados** sobre a base real | **Não** |

Os PDFs oficiais vieram da pasta do projeto no Drive: o **download automático nas fontes continua não
comprovado**. A amostra real é pequena (4 edições) e a conferência pela GEDIV ainda não ocorreu; por
isso o sistema **não** está declarado como validado para produção. Todo registro produzido pela
classificação é **candidato**: só entra nos indicadores depois de conferido por uma pessoa.
Detalhes, evidências e pendências: [docs/07](docs/07-integracao-testes-e-evidencias.md).
Regras consolidadas (eixos, grupos, indicadores): [docs/06](docs/06-regras-consolidadas.md).

## Como usar

Requisito: Python 3.10 ou mais recente; `python -m pip install -r requirements.txt` para ler PDFs.
O OCR precisa também do Tesseract com o idioma português (sem ele, páginas digitalizadas ficam
marcadas como `OCR_INDISPONIVEL`, nunca como lidas). A API e o dashboard usam só a biblioteca padrão.

### Ver o painel funcionando (demonstração, dados fictícios)

```
python -m pip install -r requirements-dev.txt
python -m observatorio.operacao demonstracao --dados dados-demo
python -m observatorio.web --dados dados-demo
```

Abra `http://127.0.0.1:8000`. O terminal mostra a credencial da gerência; use o botão
"Acesso da gerência". Sem credencial, o painel mostra só agregados de registros conferidos.

### Com PDFs do Diário Oficial

```
python -m observatorio.operacao executar PASTA_COM_PDFS      # importa, lê e classifica (data no nome: DD-MM-AAAA)
python -m observatorio.operacao executar ARQUIVO.pdf --data 2026-11-04 --url URL_OFICIAL
python -m observatorio.operacao validar-real ARQUIVO.pdf --data 2026-10-02 --url URL --saida relatorio.json --amostra amostra.txt
                                                              # relatório SEM dados pessoais + amostra PRIVADA para conferência
python -m observatorio.web                                    # painel; a revisão é feita na própria tela
```

### Comandos por etapa

```
python -m observatorio.sonda --saida sonda.json              # diagnóstico de acesso às fontes
python -m observatorio.coleta descobrir --inicio 2026-01-01   # lê as listagens mensais
python -m observatorio.coleta piloto --fonte auniao           # piloto: até 5 edições de datas diferentes
python -m observatorio.coleta lote --fonte auniao             # lotes de até 10 (após o piloto DESTA fonte)
python -m observatorio.coleta progresso | inventario | conferir
python -m observatorio.leitura processar [--refazer]          # lê os PDFs do acervo (refaz erros e pendências)
python -m observatorio.leitura validar --saida validacao.json # relatório sem texto das publicações
python -m observatorio.gerencias.gediv classificar [--refazer] | situacao | catalogo
python -m observatorio.revisao fila | ato ID … | decisao ID … | evento ID … | trilha
python -m unittest discover -s tests -t .                     # testes (não usam internet)
```

Todos os comandos podem ser interrompidos e repetidos: o que já foi feito não é refeito, e o que
já passou por revisão humana nunca é sobrescrito por uma nova classificação.
O banco (`observatorio.sqlite3`) e os PDFs ficam na pasta `dados/`, que **não** é enviada ao GitHub.

### Acesso e privacidade

- Sem credencial: apenas indicadores agregados de registros conferidos.
- Com a credencial da gerência (`GEDIV_TOKEN_GERENCIA`, 16+ caracteres): nomes, matrículas, processos,
  fila de pendências, revisão, PDFs do acervo e exportações (Excel/CSV).
- O servidor escuta só em `127.0.0.1`. Não o exponha à internet sem HTTPS e autenticação institucional.

## Regras deste repositório

- Não versionar PDFs, banco, backups, dados pessoais, senhas ou chaves.
- Uma branch por etapa; integração à `main` somente com os testes aprovados.
- Toda afirmação de "funciona" na documentação indica onde e como foi testada.

## Documentação

1. [Recuperação e diagnóstico dos projetos anteriores](docs/01-recuperacao-diagnostico.md)
2. [Plano de desenvolvimento](docs/02-plano-desenvolvimento.md)
3. [Etapa 1 — resultados de validação](docs/03-etapa1-resultados.md)
4. [Coleta em lotes e início da leitura de PDFs](docs/04-coleta-em-lotes-e-leitura.md)
5. [Leitura, validação e fontes independentes](docs/05-leitura-validacao-e-fontes-independentes.md)
6. [Regras consolidadas: eixos, grupos, subcategorias e indicadores](docs/06-regras-consolidadas.md)
7. [Integração, testes e evidências](docs/07-integracao-testes-e-evidencias.md)
8. [Validação com PDFs oficiais (10/11/2026)](docs/08-validacao-com-pdf-oficial.md)
