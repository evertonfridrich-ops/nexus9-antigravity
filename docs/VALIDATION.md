# Validação do NEXUS9 0.3.0

**87 testes aprovados, zero falhas e zero skips**, em Linux/Python 3.12.14.
Log completo: `test-results.txt`. Dependências instaladas em ambiente isolado
pelo lock com hashes; `pip check` passou. SDK MCP 1.30.0; Tree-sitter 0.25.2;
gramáticas JS 0.25.0, TS/TSX 0.23.2 e Python 0.25.0.

## Verificado por execução

- Nove módulos e 24 operações com schemas estritos e três ferramentas MCP.
- Parsers TS/TSX/JS/Python, arrows, strings com chaves, decoradores, imports
  multilinha, declarações referenciadas e corpos de dependências locais.
- Índice incremental por conteúdo, lotes rotativos e remoção somente em scan
  completo; restrições não são descartadas para aparentar economia.
- Omissões, imports não resolvidos e cobertura limitada são informados.
- Budgets acumulados atômicos, snapshots explícitos, diffs, revisão de memória,
  cache com hashes/TTL, logs agrupados, handoff limitado e usage idempotente.
- Raiz/caminhos/links/segredos/UTF-8/binários/limites e config com backup.
- Política de dono externo recusa operações válidas de memória/redução e
  referências de memória em context/handoff, antes de acessar esses dados.
- Light limita novas análises, arquivos grandes e inventário para ranking/grafo;
  paths explícitos continuam disponíveis fora do inventário limitado.
- Contexto dentro do TTL ainda recupera código alterado e um import novo.
- Instalação preserva outros MCPs; reinstalação igual é idempotente; conflito da
  Skill é detectado antes da alteração de config.
- Falha simulada após config reverte os arquivos já aplicados e cria recibo.
- Rollback restaura bytes originais, preserva servidores/configs externos
  adicionados depois e recusa sobrescrever Skill editada ou backup adulterado.
- Diagnóstico não exibe argumentos, env ou conteúdo de regras/credenciais.

Cliente/servidor oficiais MCP via stdio: handshake, três ferramentas, catálogo,
schema, sessão, contexto, snapshot, diff após edição, recusa de caminho externo,
operação desconhecida e ping. Uma representação textual JSON por resultado.

Também executado `scripts/smoke.py`, incluído no instalador: handshake real,
health/integridade SQLite, contexto Light e recusa de gravação de memória com
dono externo, usando parâmetros válidos. Esse smoke usa projeto temporário.
A Skill passou validação de frontmatter e um cenário funcional independente de
orquestração com memória externa; isso não é auditoria de segurança externa nem
prova de qualidade de um modelo nas tarefas do usuário.

## Distribuição Windows e integração IDE

Wheels Windows x64/Python 3.12 foram baixadas/verificadas por SHA-256 na etapa
anterior, incluindo Tree-sitter e pywin32 311. O lock explicita dependências
Windows; teste verifica sua presença. Nenhuma dependência foi alterada na 0.3.0.
Download cruzado não executa binários Windows.

CI fornecida para Windows/Linux, Python 3.12/3.13, com actions por commit. Em
Windows inclui parser PowerShell e aceitação isolada de instalação/rollback com
paths contendo espaços. **Essa CI e o instalador PowerShell não foram executados
neste runner Linux.** A instalação/Skill/conexão na versão Antigravity do usuário
precisam ser confirmadas no computador dele. Os caminhos foram configurados
conforme o usuário informou, não observados diretamente no disco Windows.

## Demonstração offline

`scripts/demo.py` e `demo-result.json`: fixture sintético de seleção, sem modelo.

| Medida local | Valor observado |
| --- | ---: |
| Arquivo TS de entrada | 93.151 bytes |
| Pacote com função/configuração/dependência/restrição | 5.073 bytes |
| Schemas das três ferramentas MCP | 942 bytes |
| Schemas completos das 24 operações | 11.067 bytes |
| Log de entrada, 4.000 repetições | 184.000 bytes |
| Relatório agrupado | 389 bytes |

Sete verificações funcionais passaram. Volumes locais não equivalem a tokens,
faturamento, quota ou resultado de modelo. O fixture tem ruído criado para
exercitar seleção; fontes curtas/tarefas amplas podem não ter esse benefício.

## Desempenho Light

`scripts/benchmark.py` e `performance.json`: 82 arquivos, 3.842.388 bytes,
seis consultas de contexto com fonte/dependência verificadas, em runner Linux.
Tempos exatos e contagem de CPUs do runner estão no JSON. A primeira consulta
faz indexação parcial; seguintes reutilizam descoberta e conferem as fontes.
`coverage_incomplete=true` é preservado porque o inventário inicial foi limitado.

Esses números **não representam o Kaby Lake do usuário**, o custo do IDE ou do
modelo. O benchmark não usa embeddings/workers de background e não promete
impacto quase nulo. Deve ser executado no hardware real, com medições adicionais
no tamanho efetivo do projeto.

## Critérios de adoção institucional

Validar Windows/IDE/hardware reais, executar CI, revisar segurança/dependências,
definir proteção/retenção e comparar tarefas com/sem ferramenta usando dados do
provedor e resultados aceitos. Este release fornece funções, controles e
procedimentos; não afirma certificação empresarial ou economia garantida.
