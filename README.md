# Painel de Publicações DOE-PB GEDIV

Observatório automatizado das publicações do Diário Oficial do Estado da Paraíba relacionadas à
Gerência Executiva de Concessão de Direitos e Vantagens (GEDIV/SEAD-PB).

Eixos do primeiro painel: **Progressão Funcional** e **Tempo de Serviço**.

Este é o repositório oficial. O sistema é escrito do zero; os projetos anteriores são apenas
referência (ver `docs/01`).

## Situação (10/11/2026)

Quatro níveis diferentes, que não se confundem:

| Parte | Código | Testes automatizados (simulação) | Validação com documentos oficiais | Operação efetiva |
|---|---|---|---|---|
| Coleta em lotes, por fonte | Pronto | Aprovados | **Não** | **Não** |
| Importação manual de PDFs | Pronto | Aprovados | **Não** (aguarda PDFs) | **Não** |
| Leitura por colunas, OCR, qualidade | Pronto | Aprovados | **Não** (aguarda PDFs) | **Não** |
| Classificação GEDIV, revisão, painel | Não iniciado | — | — | — |

O acesso automático às fontes ainda não foi comprovado ([medições](docs/03-etapa1-resultados.md)).
Isso não paralisa o projeto: PDFs fornecidos manualmente percorrem o mesmo fluxo de integridade e leitura.
Cada fonte é validada separadamente; a cobertura é sempre informada como parcial enquanto houver lacunas.

## Como usar

Requisito: Python 3.10 ou mais recente. Todos os comandos são executados na pasta do projeto.
A coleta e a sonda não precisam de nenhuma biblioteca adicional. A leitura de PDFs precisa de
`python -m pip install -r requirements.txt`; o OCR precisa também do programa Tesseract com o idioma
português (sem ele, páginas digitalizadas ficam marcadas como `OCR_INDISPONIVEL`, nunca como lidas).

```
python -m observatorio.sonda --saida sonda.json              # 1. diagnóstico de acesso às fontes
python -m observatorio.coleta descobrir --inicio 2026-01-01   # 2. lê as listagens mensais
python -m observatorio.coleta piloto --fonte auniao           # 3. piloto: até 5 edições de datas diferentes
python -m observatorio.coleta piloto --fonte cge
python -m observatorio.coleta lote --fonte auniao             # 4. lotes históricos de até 10 (após o piloto DESTA fonte)
python -m observatorio.coleta progresso                       # situação por mês e por fonte
python -m observatorio.coleta inventario --inicio 2026-01-01  # cobertura dia a dia
python -m observatorio.coleta importar arquivo.pdf --data 2026-11-04   # inclusão manual de um PDF
python -m observatorio.coleta importar pasta-com-pdfs         # vários PDFs; a data vem do nome (DD-MM-AAAA)
python -m observatorio.coleta conferir                        # reconfere a integridade do acervo
python -m observatorio.leitura processar                      # lê os PDFs do acervo ainda não lidos
python -m observatorio.leitura situacao
python -m observatorio.leitura validar --saida validacao.json # relatório sem texto das publicações
python -m observatorio.leitura pagina SHA256 3                # texto de uma página, para conferência humana
python -m unittest discover -s tests -t .                     # testes (não usam internet)
```

Todos os comandos podem ser interrompidos e repetidos: o que já foi feito não é refeito.
O banco (`observatorio.sqlite3`) e os PDFs ficam na pasta `dados/`, que **não** é enviada ao GitHub.

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
