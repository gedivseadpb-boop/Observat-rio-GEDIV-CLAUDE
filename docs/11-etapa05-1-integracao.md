# Etapa 05.1 — Integração das Etapas 04 e 05 (situação em 14/11/2026)

Branch de integração local: `etapa05-1/integracao-pdfs-coleta`. Sem push, sem merge, sem deploy.

## Situação: integração INCOMPLETA — código da Etapa 05 indisponível

| Linha | Origem verificada | Situação |
|---|---|---|
| Etapas 01–03 | GitHub: `etapa03/pr01-regras-definitivas` (`1fc2469`), `etapa03/pr02-leitura-ouro` (`b225289`) | Recuperadas |
| Etapa 04 | Branch local `etapa04/pdfs-dificeis` (`7ee3933`) e bundle verificado com `git bundle verify` | **Recuperada integralmente** e base da branch de integração |
| Etapa 05 | Não está no GitHub (não há branch `etapa05*` no remoto em 14/11/2026), nem neste ambiente, nem anexada (`etapa05.bundle`, patches, `RELATORIO_ETAPA05.md`, JSONs da sandbox) | **Não recuperada. Não reconstruída a partir de relatos.** |

## O que foi feito nesta etapa

1. **Migrações pela estrutura presente** (`observatorio/nucleo/banco.py`, commit `36bf6f6`):
   - cada instrução só roda se a tabela, o índice ou a coluna ainda não existir;
   - todas as pendentes e a nova versão numa única transação explícita, com ROLLBACK em falha. O
     `executescript` anterior fazia COMMIT antes e podia deixar uma migração pela metade;
   - cópia íntegra do arquivo antes de alterar um banco existente (`<banco>.antes-v<N>.bak`);
   - banco de versão mais nova continua recusado;
   - um banco marcado `user_version = 6` com esquema de outra linha (tabelas extras, sem a coluna
     `evento.publicacoes_citadas`) é completado sem perda.
2. **Testes de migração** (`tests/test_migracoes.py`, 9 testes): banco novo; v1/v4/v5 com dados; reabertura
   idempotente; migração interrompida; variante v6 de outra linha; falha com rollback; restauração da cópia;
   versão mais nova recusada; cobertura estrutural de todas as 31 instruções.
3. **Revalidação da Etapa 04** sobre a branch de integração, com os PDFs oficiais:
   - conjunto-ouro 5/5;
   - corpus por campo 100% (63 linhas de desenvolvimento e 36 de validação cega);
   - 7 edições de novembro iguais, ato por ato, à Etapa 04;
   - evento "sem efeito" de 10/11 com a publicação original (1999-07-28).
4. **Aquisição real em nuvem** com o coletor do projeto (§4).

## Como a Etapa 05 deverá entrar, quando o bundle estiver disponível

1. `git bundle verify etapa05.bundle` e `git fetch etapa05.bundle etapa05/coleta-oficial:etapa05/coleta-oficial`.
   Conferir que a base é `b225289`.
2. Na branch `etapa05-1/integracao-pdfs-coleta`, fazer o merge (sem squash) de `etapa05/coleta-oficial`,
   preservando os commits originais. Ordem: Etapa 04 (já na base), depois Etapa 05, porque a 05 parte de uma
   base mais antiga.
3. **Migração:** a migração da Etapa 05 (tabelas `download` e `verificacao_arquivo`) entra como **v7**:
   - acrescentar `(7, _ESQUEMA_V7)` a `_MIGRACOES`;
   - `VERSAO_ESQUEMA = 7`;
   - usar só `CREATE TABLE`, `CREATE INDEX` e `ALTER TABLE … ADD COLUMN`; qualquer outra instrução exige
     ampliar `_ja_existe`, e o teste de cobertura estrutural falha até isso ser feito.

   Bancos existentes:

   | Banco existente | O que acontece |
   |---|---|
   | v6 da Etapa 04 | ganha as tabelas da 05 |
   | "v6" da Etapa 05 | ganha só a coluna de eventos; as tabelas de download são preservadas |
   | v4 / v5 | ganham as duas |

   Acrescentar a `tests/test_migracoes.py` os casos com as colunas REAIS da Etapa 05, substituindo a
   simulação.
4. Conflitos a examinar com o código real: `tests/apoio.py`, `observatorio/nucleo/banco.py`,
   `observatorio/operacao/__main__.py`, `observatorio/nucleo/pdf.py`, `requirements*.txt`, documentação.
5. Garantir que o fluxo de aquisição só entrega arquivo à leitura depois da verificação de integridade
   (quarentena antes do acervo).
6. Rodar a suíte inteira, o conjunto-ouro, o corpus de novembro e o corpus por campo.

## Aquisição real em nuvem (14/11/2026)

| Executor | Resultado |
|---|---|
| Contêiner de nuvem da sessão de desenvolvimento (Anthropic, proxy de saída) | **Comprovado**: listagem de novembro com 9 edições; download de 04/11 pelo coletor do projeto, 2.202.466 bytes, SHA-256 `02cbb8ae…` igual à referência, estrutura válida. Não é infraestrutura operacional (sessão efêmera, sem agendamento). |
| Sandbox da Etapa 05 | `PROXY_RECUSOU` (relatado; bloqueio daquele ambiente) |
| GitHub Actions | Conexão expira (medições de 10–11/11). O workflow `sonda.yml` (manual) já existe; nova execução exige autorização. |

`AQUISICAO_REAL_NUVEM`: comprovada neste executor de desenvolvimento; **não homologada** para operação.
