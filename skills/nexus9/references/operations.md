# Exemplos de protocolo

Descobrir o schema atual antes da primeira chamada de cada operação. Não supor
que uma operação bloqueada pelo runtime poderá ser executada.

Enviar a `nexus_manage`:

```json
{"operation":"session_open","parameters":{"name":"gps-20261001-01","profile":"economy","call_budget_bytes":4096,"total_budget_bytes":64000}}
```

Escolher nome novo por tarefa. Em seguida, enviar a `nexus_query`:

```json
{"operation":"context","session":"gps-20261001-01","parameters":{"task":"Corrigir startGPS preservando Expo 52","paths":["src/gps.ts"],"focus_symbols":{"src/gps.ts":"startGPS"},"constraints":["Manter Expo 52"],"budget_bytes":4096}}
```

O exemplo depende de esse arquivo/símbolo existir. Substituir por evidência do
workspace, não inventar paths.

Para salvar memória, obter revisão atual com `memory`, descobrir `memory_save`,
informar `expected_revision` exata e body com objetivo, decisões, restrições,
pendências, arquivos relativos e validações. Informar fonte `user`, `agent`,
`verified_file` ou `test_result` conforme a origem real. Essas etiquetas são
declarações do agente; preservar também evidência. Não usar `test_result` para
testes que não foram executados.

Fechar sessão em `nexus_manage`:

```json
{"operation":"session_close","parameters":{"name":"gps-20261001-01"}}
```

`session_open` repetido não zera gasto. `remember_read` usa revisão por
arquivo/sessão. `cache_save` exige arquivos fonte, valida hashes e tem TTL.
Manter três nomes MCP fixos e obter schemas detalhados sob demanda.
