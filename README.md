# Painel de Publicações DOE-PB GEDIV

Observatório automatizado das publicações do Diário Oficial do Estado da Paraíba relacionadas à
Gerência Executiva de Concessão de Direitos e Vantagens (GEDIV/SEAD-PB).

Eixos do primeiro painel: **Progressão Funcional** e **Tempo de Serviço**.

Este é o repositório oficial. O sistema é escrito do zero; os projetos anteriores são apenas
referência (ver `docs/01`).

## Situação (10/11/2026)

| Etapa | Situação |
|---|---|
| 1. Coleta e integridade dos documentos | Código pronto e testado com dados sintéticos; **validação com as fontes reais pendente** |
| 2. Leitura dos PDFs | Não iniciada |
| 3 a 8 | Não iniciadas |

O acesso automático às fontes ainda não foi obtido. A causa está sendo medida, não presumida:
ver [resultados da Etapa 1](docs/03-etapa1-resultados.md).

## Como usar

Requisito: Python 3.10 ou mais recente. Nenhuma biblioteca adicional é necessária nesta etapa.
Todos os comandos são executados na pasta do projeto.

```
python -m unittest discover -s tests -t .          # testes (não usam internet)
python -m observatorio.sonda --saida sonda.json    # diagnóstico de acesso às fontes
python -m observatorio.coleta coletar --inicio 2026-01-01
python -m observatorio.coleta inventario --inicio 2026-01-01
python -m observatorio.coleta importar arquivo.pdf --data 2026-11-04
python -m observatorio.coleta conferir             # reconfere a integridade do acervo
```

A coleta grava o banco (`observatorio.sqlite3`) e os PDFs na pasta `dados/`, que **não** é
enviada ao GitHub.

## Regras deste repositório

- Não versionar PDFs, banco, backups, dados pessoais, senhas ou chaves.
- Uma branch por etapa; integração à `main` somente com os testes aprovados.
- Toda afirmação de "funciona" na documentação indica onde e como foi testada.

## Documentação

1. [Recuperação e diagnóstico dos projetos anteriores](docs/01-recuperacao-diagnostico.md)
2. [Plano de desenvolvimento](docs/02-plano-desenvolvimento.md)
3. [Etapa 1 — resultados de validação](docs/03-etapa1-resultados.md)
