# Prévia Pública Estática Gratuita no GitHub Pages

## Decisão de Hospedagem

A **demonstração pública gratuita do Painel Unificado do Observatório GEDIV** (**Delicadeza Visual**) utiliza **GitHub Pages** em repositório separado e dedicado, sem servidores institucionais, serviços pagos ou infraestrutura externa obrigatória:

- **Prévia pública estática (HTTPS gratuito):** https://gedivseadpb-boop.github.io/gediv-painel-unificado-previa/
- **Repositório da prévia estática:** https://github.com/gedivseadpb-boop/gediv-painel-unificado-previa
- **Repositório principal (código completo com backend Python/SQLite):** https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE
- **GitHub Pages legado:** preservado inalterado em `gh-pages` do repositório principal.

## Como o Pacote Estático Funciona

1. O gerador [scripts/preparar_previa_github_pages.py](../scripts/preparar_previa_github_pages.py) parte do painel real `observatorio/web/unificado/index.html` (preservando integralmente as 7 abas, cartões, gráficos, calendário, filtros, navegação e as 240 cores HEX).
2. A demonstração carrega `./dados-sinteticos-publicos.json` (dados **100% sintéticos e descartáveis** — processos `SAD-PSE-2099/*`, matrículas `950.xxx-x`, nomes `SERVIDOR FICTICIO ...`), sem depender de nenhuma rota `/api/*`.
3. Funções que exigem backend verdadeiro (**login gerencial**, **conferência documental**, **resolução de conflitos D2**, **trilha de auditoria D3** e **alterações de registros**) são claramente desabilitadas na interface estática, **sem simular segurança por senha em JavaScript**.
4. Antes de cada publicação pelo GitHub Actions (`publicar-pages.yml`), o validador fail-closed (`scripts/validar_artefato_publico.py`) garante a ausência de dados reais, credenciais, CPFs, caminhos locais e arquivos não autorizados.

## Como Reproduzir o Pacote Localmente

```bash
python scripts/preparar_previa_github_pages.py --saida dist-previa-pages
```

## Documentação Histórica de Infraestrutura Linux

Os guias e scripts em `deploy_autonomo/` (`GUIA_IMPLANTACAO_AUTONOMA.md`, `gediv-admin.service`, `homologar_ambiente_linux.sh`, etc.) permanecem preservados como **documentação histórica e opcional** para eventual uso futuro com backend completo, não constituindo requisito atual para a demonstração pública gratuita no GitHub Pages.
