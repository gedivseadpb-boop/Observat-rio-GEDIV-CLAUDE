# Identificação documental visível — PR09.4 experimental

As listas de atos mostram um rótulo composto com emitente/unidade, tipo e número,
edição/data lidas e página. O detalhe mantém o sufixo existente. Os IDs internos,
classificação, filtros, indicadores e esquema SQLite 8 não mudam.

O namespace do painel (`gerencia_painel=GEDIV`) não comprova o órgão emitente.
A identificação usa somente cabeçalhos lidos explicitamente reconhecidos de
SEAD ou PBPREV; menções no corpo, sufixo isolado, ausência ou contradição não
comprovam emitente. Nesses casos aparece `EMITENTE_NAO_CONFIRMADO`. A unidade
também depende do cabeçalho. Isto é apresentação do texto armazenado, não revisão
documental humana. Não há novo OCR nem leitura de PDF nesse caminho.

CSV de decisões e abas Decisoes/Atos do XLSX preservam as 27/15 colunas históricas,
seus valores e tipos, e acrescentam nove colunas no final:

1. Painel/gerência;
2. Órgão emitente (cabeçalho lido);
3. Unidade emissora (cabeçalho lido);
4. Tipo de publicação;
5. Sufixo institucional lido;
6. Edição DOE lida;
7. Data da edição lida;
8. SHA-256 do PDF;
9. Identificação documental (conferir na fonte).

Edição, data e SHA ausentes/inválidos ficam vazios; a data de publicação não é
usada para inventar data da edição. O sufixo não é preenchido no banco. Nenhum
texto livre do ato ou dado pessoal é acrescentado aos metadados públicos.

Consumidores devem preservar ID do ato, página e documento; o número de resenha
isolado não é identificador institucional. Riscos das chaves físicas/lógicas e
de sugestões de retificação por número continuam reservados a tarefa distinta.

O pacote privado de conferência V2 é externo ao Git. Conserva todas as leituras
e campos humanos da versão anterior; os novos campos apenas qualificam a fonte.
Máscaras parciais não autorizam circulação pública. A revisão humana, o
licenciamento PyMuPDF e a implantação continuam pendentes.

Uma edição sem atos GEDIV pode ser legítima. Zero registros não confirma ausência
de ato/edição, nem significa falha técnica. A cobertura existente permanece
parcial; esta mudança não acrescenta estados de coleta ou agendamento diário.
