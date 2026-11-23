# Prévia Pública Estática Gratuita no GitHub Pages e Homologação Local

## 1. Decisão de Hospedagem

A **demonstração pública gratuita do Painel Unificado do Observatório GEDIV** (**Delicadeza Visual**) utiliza **GitHub Pages** em repositório separado e dedicado, sem servidores institucionais, serviços pagos ou infraestrutura externa obrigatória:

- **Prévia pública estática (HTTPS gratuito):** https://gedivseadpb-boop.github.io/gediv-painel-unificado-previa/
- **Repositório da prévia estática:** https://github.com/gedivseadpb-boop/gediv-painel-unificado-previa
- **Repositório principal (código completo com backend Python/SQLite):** https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE
- **GitHub Pages legado:** preservado inalterado em `gh-pages` do repositório principal.

---

## 2. Prévia Pública Estática vs. Aplicação com Backend Python/SQLite

| Aspecto | Prévia Pública Estática (GitHub Pages) | Aplicação com Backend (`python -m observatorio.web`) |
| :--- | :--- | :--- |
| **Fonte de dados** | `./dados-sinteticos-publicos.json` (100% sintético e descartável) | Banco SQLite (`observatorio.sqlite3`) + `snapshot_publico.json` congelado para consulta pública |
| **Rotas `/api/*`** | Nenhuma (`0` chamadas de API) | `/api/saude`, `/api/data`, `/api/painel`, `/api/login`, `/api/revisao`, `/api/auditoria`, `/api/exportar` |
| **Consulta pública** | Navegação interativa completa sobre dados fictícios (`SAD-PSE-2099/*`, `950.xxx-x`) | Somente agregados protegidos (`>= 5` decisões e `>= 5` matrículas, faixas de 5, granularidade mensal, `rows: []`) |
| **Login, revisão e auditoria** | Claramente desabilitados (sem senha simulada em JavaScript) | Autenticação nominal (`scrypt` + cookie `HttpOnly`), RBAC (`Público`, `Gerência`, `Administração`), revisão auditada |
| **Uso de dados reais** | **Estritamente proibido** | Permitido apenas em ambiente interno controlado, nunca exposto sem autenticação nem no `snapshot_publico.json` |

---

## 3. Fonte Única Canônica de Dados Sintéticos

Para evitar divergências entre a prévia publicada no GitHub Pages e a homologação local com backend, ambos reutilizam o módulo único [observatorio/operacao/previa_sintetica.py](../observatorio/operacao/previa_sintetica.py):

- **6 edições sintéticas** (Jun–Nov/2026) com processos `SAD-PSE-2099/*`, matrículas `950.xxx-x` e nomes `SERVIDOR FICTICIO ...`.
- **Reconciliação de referência nas decisões conferidas (96 decisões):**
  - **42 Progressões Verticais:** `29` A–F efetivadas + `7` indeferidas (sem nível) + `2` deferidas sem nível + `2` inconsistências A–F (`D → B`, `C → C`) + `2` estrutura A–F não se aplica (`II → III`, `III → IV`).
  - **29 Progressões Horizontais** e **25 decisões de Tempo de Serviço** (`TS-01` a `TS-07` + subcategoria pendente).
- **Guarda de segurança:** `criar_base_local_sintetica()` recusa (`ValueError`) sobrescrever qualquer `observatorio.sqlite3` existente que contenha publicações reais (não sintéticas).

---

## 4. Comando Oficial `publicar-snapshot-publico`

```bash
python -m observatorio.operacao publicar-snapshot-publico --dados PASTA [--saida ARQUIVO.json]
```

### Finalidade e argumentos
- **Finalidade:** gera, valida e grava atomicamente o arquivo `snapshot_publico.json` a partir de um banco SQLite GEDIV, sem exigir o servidor web ativo nem autenticação HTTP.
- **`--dados PASTA`** (padrão: `dados`): diretório contendo `observatorio.sqlite3`.
- **`--saida ARQUIVO.json`** (opcional): caminho alternativo de gravação. Quando omitido, grava em `<PASTA>/snapshot_publico.json`.

### Condições de uso, validação e códigos de saída
- **Banco inexistente (`codigo_de_saida: 4` / `BANCO_AUSENTE`):** se `<PASTA>/observatorio.sqlite3` não existir, a CLI falha de forma fechada e retorna JSON estruturado **sem criar um banco SQLite vazio**.
- **Validação fail-closed (`codigo_de_saida: 1` / `SNAPSHOT_INVALIDO`):** antes de substituir o arquivo de destino (via arquivo temporário `.tmp`, `fsync` e `os.replace`), o conteúdo passa por `indicadores.validar_snapshot_publico()`. Se houver qualquer violação de contrato ou privacidade, o comando retorna `1` e preserva eventual snapshot anterior intacto.
- **Sucesso (`codigo_de_saida: 0` / `OK`):** grava `snapshot_publico.json` e imprime no `stdout` um resumo JSON contendo apenas metadados e agregados públicos protegidos.

### Medidas de proteção de informações pessoais
- K-anonymity com limiar mínimo de **5 decisões e 5 matrículas distintas**, arredondamento em faixas de largura 5 e granularidade temporal exclusivamente mensal (`YYYY-MM`).
- **Supressão complementar e secundária** em todas as dimensões agregadas (incluindo `por_situacao_nivel_vertical`, `resumo_nivel_vertical` e `por_subcategoria` + `tempo_sem_subcategoria`), impedindo reconstrução de células `< 5` por subtração.
- Remoção total de `rows`, `events`, `resenhas`, `transicoes`, URLs com `#page=`, hashes de PDF, CPFs e números individuais de processo — tanto no arquivo gravado quanto na saída padrão da CLI.

---

## 5. Como Reproduzir, Atualizar e Validar os Ambientes

### 5.1. Pacote estático para o GitHub Pages
```bash
python scripts/preparar_previa_github_pages.py --saida dist-previa-pages
```
Antes de cada publicação pelo GitHub Actions (`publicar-pages.yml`), o validador fail-closed (`scripts/validar_artefato_publico.py`) confirma a ausência de dados reais, credenciais, CPFs, caminhos locais e arquivos fora da lista autorizada (`.nojekyll`, `index.html`, `dados-sinteticos-publicos.json`).

### 5.2. Atualização e validação do ambiente local sintético com backend
```bash
# 1. Gerar/sincronizar base SQLite sintética canônica + snapshot público inicial
python scripts/preparar_previa_github_pages.py --banco-local dados-previa-sintetica

# 2. (Opcional / manutenção) Regerar e validar apenas snapshot_publico.json via CLI oficial
python -m observatorio.operacao publicar-snapshot-publico --dados dados-previa-sintetica

# 3. Subir o servidor local
python -m observatorio.web --dados dados-previa-sintetica --endereco 127.0.0.1 --porta 8000

# 4. Validar testes automatizados (Python, JS/ARIA e navegador real)
python -m unittest tests/test_operacao_snapshot_cli.py tests/test_sincronizacao_sintetico_canonico.py tests/test_niveis_verticais_af.py -v
npm test
node tests/test_acessibilidade_navegador.cjs --url http://127.0.0.1:8000/painel/
```

---

## 6. Documentação Histórica de Infraestrutura Linux

Os guias e scripts em `deploy_autonomo/` (`GUIA_IMPLANTACAO_AUTONOMA.md`, `gediv-admin.service`, `homologar_ambiente_linux.sh`, etc.) permanecem preservados como **documentação histórica e opcional** para eventual uso futuro com backend completo em servidor Linux, não constituindo requisito atual para a demonstração pública gratuita no GitHub Pages.
