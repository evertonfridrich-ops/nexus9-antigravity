# O que foi preservado e o que foi evoluído

HYDRA foi a referência conceitual: orquestração, seleção de ferramentas,
compactação, auditoria, formato conciso, controle de contexto, repetição,
tracking e prompts mínimos. Essas são camadas úteis e diferentes; as nove
cabeças não equivalem necessariamente a nove ferramentas MCP.

NEXUS9 é uma implementação independente, com primitives de segurança aproveitadas
do ContextGuard criado anteriormente. Não copia os skills/código do HYDRA e
não é só uma mudança de nome ou um instalador mais seguro.

| Ideia do HYDRA | Evolução funcional implementada |
|---|---|
| Orquestrar o uso das cabeças | `plan` fornece rota verificável com sinais de risco e validação |
| Selecionar MCPs relevantes | Facade com três ferramentas, schemas sob demanda e `route` por catálogo fornecido |
| Contexto mínimo | `context` produz pacote multi-arquivo com ranking, AST, imports, restrições e cobertura |
| Recortar uma função | `snippet` usa Tree-sitter para JS/TS/TSX/Python, inclusive arrows e strings com chaves |
| Saber quem depende | `impact` resolve imports locais e importadores em até três níveis, com pendências explícitas |
| Compactar/guardar contexto | Memória revisionada com proveniência e hashes, mais deduplicação exata de blocos |
| Evitar repetição | Diffs contra base explícita, hash ativo declarado pelo chamador e cache com fontes/TTL |
| Reduzir logs | Streaming, agrupamento de erros repetidos e preservação de códigos de status pequenos |
| Controlar saturação | Orçamentos de resposta/sessão realmente aplicados ao retorno local, em transação |
| Auditar tokens/custo | Contadores locais separados de usage reportado, com dedup por request_id |
| Prompt mínimo para agentes | `handoff` compila brief com evidência, restrições e validação; não inicia agentes |
| Demonstrar eficiência | Avaliação pareada por tarefa que sinaliza regressões de qualidade mesmo com menos tokens |

As operações que dependem do IDE/modelo continuam sendo orientação ou informação
de entrada. NEXUS9 não controla a lista de outros servidores do host, não substitui
a história da conversa e não mede automaticamente o faturamento do Antigravity.

A superioridade comprovada nesta entrega é de capacidades e controles específicos
testados. Economia geral e qualidade em projetos reais precisam de comparação
pareada executada no ambiente de uso. Por isso não há uma porcentagem comercial
de economia anunciada como fato.
