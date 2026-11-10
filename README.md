# Painel de Publicações DOE-PB GEDIV

Observatório automatizado das publicações do Diário Oficial do Estado da Paraíba relacionadas à
Gerência Executiva de Concessão de Direitos e Vantagens (GEDIV/SEAD-PB).

Eixos do primeiro painel: **Progressão Funcional** e **Tempo de Serviço**.

Este é o repositório oficial. O sistema é escrito do zero; os projetos anteriores são apenas
referência (ver `docs/01`).

## Situação (10/11/2026)

| Parte | Situação |
|---|---|
| Coleta em lotes, acervo e registro | Código pronto e testado por simulação; **nenhum download real ainda** |
| Leitura dos PDFs por colunas | Iniciada e testada com PDF sintético; **nenhum DOE real lido ainda**; OCR pendente |
| Classificação GEDIV, revisão, painel | Não iniciados |

O acesso automático às fontes ainda não foi comprovado. A causa é medida, não presumida:
ver [resultados da Etapa 1](docs/03-etapa1-resultados.md). A carga histórica fica travada
pelo próprio sistema até haver um lote piloto aprovado em cada fonte.

## Como usar

Requisito: Python 3.10 ou mais recente. Todos os comandos são executados na pasta do projeto.
A coleta e a sonda não precisam de nenhuma biblioteca adicional; a leitura de PDFs precisa de
uma (`python -m pip install -r requirements.txt`).

```
python -m observatorio.sonda --saida sonda.json              # 1. diagnóstico de acesso às fontes
python -m observatorio.coleta descobrir --inicio 2026-01-01   # 2. lê as listagens mensais
python -m observatorio.coleta piloto --fonte auniao           # 3. piloto: até 5 edições de datas diferentes
python -m observatorio.coleta piloto --fonte cge
python -m observatorio.coleta lote --fonte auniao             # 4. lotes históricos de até 10 (após os pilotos)
python -m observatorio.coleta progresso                       # situação por mês e por fonte
python -m observatorio.coleta inventario --inicio 2026-01-01  # cobertura dia a dia
python -m observatorio.coleta importar arquivo.pdf --data 2026-11-04   # inclusão manual de um PDF
python -m observatorio.coleta conferir                        # reconfere a integridade do acervo
python -m observatorio.leitura processar                      # lê os PDFs do acervo ainda não lidos
python -m observatorio.leitura situacao
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
