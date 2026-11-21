# Painel Diário Oficial | GEDIV — prévia pública

Esta entrega aproveita o leitor, o catálogo e o dashboard incorporados na linha PR10.1. A `main` e as branches anteriores não são alteradas. O painel privado existente continua separado, com autenticação e revisão; a prévia pública não oferece acesso a registros individuais.

Endereço da prévia: [endereço privado removido]

Branch de entrega: `entrega/painel-publico-gediv`.

## Dados e uso

O painel público lê apenas `dados.json`, uma projeção gerada de bancos reais abertos em modo somente leitura. Ela diferencia conferidos, provisórios e cobertura documental, sem transformar leitura por OCR ou resultado de teste em homologação humana.

A divulgação usa agregados mensais e faixas de contagem, além de resumos gerais dos dois eixos. Células precisam de pelo menos cinco decisões e cinco matrículas distintas reconhecidas; recortes menores são omitidos antes da publicação; nomes, matrículas, processos, IDs de decisões, trechos e documentos de origem não fazem parte do pacote. Os gráficos e os filtros abrangem somente os agregados publicáveis. Por isso não devem ser comparados como se fossem os totais exatos da base privada.

Os dois eixos são Progressão Funcional (horizontal/vertical e catálogo PCCR existente) e Tempo de Serviço (TS-01 a TS-07). Licença-saúde e vacância não compõem os indicadores. Uma publicação de assunto não explícito continua pendente na documentação de cobertura e não bloqueia os demais agregados.

## Atualização a partir do processamento disponível

A geração é explícita, sem coleta, agendamento ou mudança de revisão:

```bash
python scripts/preparar_painel_publico.py \
  --banco /caminho-privado/fonte.sqlite3 \
  --banco /caminho-privado/fonte-mais-recente.sqlite3 \
  --cobertura /caminho-privado/matriz-cobertura.csv \
  --saida /caminho-de-distribuicao
```

Nenhum caminho privado deve ser gravado na projeção ou em arquivos versionados. É possível executar esse comando após o fluxo de processamento já existente. A geração não atualiza SQLite nem confere decisões. O responsável técnico deve verificar a projeção antes de substituir o snapshot público.

Para validar ou empacotar somente o snapshot público versionado, sem bancos em CI:

```bash
python scripts/preparar_painel_publico.py \
  --projecao painel-publico/dados.json --saida dist
```

A distribuição é uma lista fechada de arquivos: HTML, JavaScript, CSS, logomarca e JSON agregado. Nenhum serviço Python, PaddleOCR, banco ou chave é necessário no navegador ou na hospedagem. PaddleOCR permanece opcional e experimental na leitura privada.

## Exportação e apresentação

Filtros por mês, eixo, modalidade, grupo, assunto e situação operam sobre o mesmo JSON dos gráficos e tabelas. CSV exporta apenas a visão agregada protegida. PDF usa a impressão do navegador, com apresentação própria. XLSX é gerado localmente no navegador, com os mesmos agregados protegidos, sem biblioteca remota ou acesso ao banco.

Há modo claro/escuro, layout responsivo, estados de erro e ausência de dados, data da geração do snapshot e indicação de cobertura incompleta desde 01/01/2026. Nenhum mês sem cobertura é apresentado como mês sem atos. A prévia não declara resultado administrativo oficial.

## Hospedagem e continuidade

GitHub Pages não estava habilitado no repositório. A prévia usa Sites, separada de `centralgestaopublica.com.br`, sem mudança de DNS, contratação de serviço ou ativação de cobrança. O repositório principal preserva código e snapshot na branch de entrega; a hospedagem recebe somente uma cópia estática protegida.

A publicação inicial é executada e verificada nesta entrega. A rotina diária e a cobertura histórica completa permanecem etapas futuras: precisam de execução privada do leitor, acesso contínuo às fontes, conferência humana e publicação do snapshot atualizado. Nenhum segredo ou banco privado é levado ao CI. Não foi ativado agendamento diário automaticamente.
