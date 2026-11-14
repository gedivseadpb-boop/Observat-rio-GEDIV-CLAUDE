# Etapa 05.1 — Integração das Etapas 04 e 05

Data: 14/11/2026. Branch local: `etapa05-1/integracao-pdfs-coleta`. Sem push, merge, deploy ou alteração da
`main`.

## Situação: integração COMPLETA

| Linha | Origem | SHA | Situação |
|---|---|---|---|
| Etapas 01–03 | GitHub `etapa03/pr02-leitura-ouro` | `b225289` | Base comum |
| Etapa 04 | Branch local `etapa04/pdfs-dificeis` + bundle verificado | `7ee3933` | Integrada sem alteração |
| Etapa 05 | `etapa05.bundle` fornecido em 14/11/2026 (`git bundle verify` OK, histórico completo), branch `etapa05/coleta-oficial` | `8d9c640` (código), `3c99895` (relatório) | Integrada por merge sem squash |

Ordem: Etapa 04 → migrações estruturais (`36bf6f6`) → merge da Etapa 05 (`8494510`). As duas linhas partem de
`b225289`; a 04 veio primeiro porque a correção das migrações foi escrita sobre ela.

## Conflitos e resolução

| Arquivo | Tipo | Resolução |
|---|---|---|
| `observatorio/nucleo/banco.py` | Textual e de banco: as duas linhas chamaram sua migração de "v6" | v6 = coluna `evento.publicacoes_citadas` (Etapa 04); **v7** = tabelas `download` e `verificacao_arquivo` (Etapa 05); `VERSAO_ESQUEMA = 7`. Mantidos o motor estrutural e todos os métodos e constantes da Etapa 05. |
| `observatorio/operacao/__main__.py` | Textual | União: `corpus` (04) + `sonda`, `coletar-dia`, `coletar-intervalo`, `cobertura` (05) e todos os argumentos |
| `tests/test_regras_definitivas.py` | Textual (mesma mudança nas duas linhas) | Versão sem o comentário que deixaria de valer |
| `observatorio/coleta/coletor.py` | **Comportamento** (achado real, ver abaixo) | Mês lido registrado por inteiro; o período restringe os downloads |
| `tests/apoio.py`, `nucleo/pdf.py`, `nucleo/rede.py`, demais | Sem conflito | Entraram como na Etapa 05 |

## Migração final (v7)

A decisão é tomada pela **estrutura presente**, não só pelo número. Cada instrução (`CREATE TABLE`, `CREATE INDEX`,
`ALTER … ADD COLUMN`) só roda se a estrutura ainda não existir. As pendentes e a nova versão são gravadas numa
única transação, com ROLLBACK em falha, e é feita uma cópia do arquivo antes de alterar um banco existente.

| Banco existente | Resultado |
|---|---|
| v1, v4, v5 | v7 com as duas estruturas; dados preservados |
| v6 da Etapa 04 | ganha `download` e `verificacao_arquivo` |
| "v6" da Etapa 05 | ganha só `evento.publicacoes_citadas`; downloads e verificações preservados. **Testado também com um banco real criado pelo código original da Etapa 05.** |
| Migração interrompida no meio | completada sem erro |
| Tabela homônima incompatível | migração falha inteira, nada é alterado |
| Versão mais nova | recusado |

## Achado real corrigido: cobertura declarava "sem publicação" por engano

Com o código da Etapa 05 sem alteração, `coletar-dia --data 2026-11-07` seguido de `cobertura` de 04 a 08/11
marcava 04, 05 e 06/11 como `SEM_PUBLICACAO_LISTADA`, embora a listagem de novembro lida na mesma execução
trouxesse essas edições.

- **Causa:** a leitura do mês era gravada como completa, mas só as edições do período eram registradas.
- **Correção:** o mês lido é registrado por inteiro; só os downloads seguem o período.
- **Teste:** o teste da Etapa 1 que fixava "o período restringe o registro" passou a verificar o contrato
  correto. A mudança de expectativa tem esta justificativa.
- **Verificação com dados reais:** 04–06/11 `PENDENTE`, 07/11 `COMPLETO`, 08/11 `SEM_PUBLICACAO_LISTADA`, um
  único download.

## Validação

| Verificação | Resultado |
|---|---|
| Suíte completa, sem dados reais | 262 testes: 260 OK, 2 pulados |
| Suíte completa com PDFs oficiais e esperado privado | 262 testes: **262 OK, 0 pulados, 0 falhos** |
| Conjunto-ouro (01, 02, 03, 06/10 e 04/11) | 5/5 |
| Corpus por campo | 100% (63 linhas de desenvolvimento, 36 de validação cega) |
| Edições de novembro (05 a 12/11) | Idênticas à Etapa 04, ato por ato |
| Cadeia real: `sonda` → `coletar-dia` 07/11 → leitura 0.6 → classificação | 579 (20) e 580 (22) e demais atos idênticos à Etapa 04 |

O ruído `BrokenPipeError` na saída dos testes vem do servidor local de `tests/apoio.py` quando o cliente encerra a
conexão de propósito (testes de truncamento). Já existia na Etapa 05 e não é falha.

## Aquisição real em nuvem (14/11/2026, contêiner desta sessão; não é GitHub Actions)

| Comando | Resultado |
|---|---|
| `sonda` | `DOWNLOAD_INTEGRO`, edição de 14/11: HTTP 200, Content-Length = bytes (1.577.446), 40 páginas, estrutura verificada |
| `coletar-dia --data 2026-11-07` | `NOVO`: Content-Length = bytes (2.449.072), SHA-256 `8bac8dad…` (igual à referência), 44 páginas, manifesto e verificação gravados, banco v7 |
| `--dry-run`, `cobertura` | Funcionando |

`AQUISICAO_REAL_NUVEM`: comprovada em executor de desenvolvimento. Não homologada: a sessão é efêmera, e o
GitHub Actions ainda não foi medido com o coletor da Etapa 05.
