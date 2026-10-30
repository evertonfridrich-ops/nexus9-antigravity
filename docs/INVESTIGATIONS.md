# Investigações com evidências — NEXUS9 0.4

O NEXUS9 mantém nove cabeças e as três ferramentas MCP. A versão 0.4 acrescenta investigações persistentes, vínculos entre hipóteses/fontes/testes/conclusões, casos de regressão e identidade do processo. Isso não inicia agentes, não troca o modelo nem fornece atualização automática.

## Descoberta e fluxo

Descubra o schema de cada operação com `nexus_catalog(operation=...)`. As consultas usam `nexus_query` e alterações explícitas usam `nexus_manage`.

| Operação | Ferramenta | Finalidade |
| --- | --- | --- |
| `investigation_save` | manage | Criar/estender a investigação com revisão esperada. |
| `investigation` | query | Consultar estado, fontes, hipóteses concorrentes e próximas verificações; `conclusion_id` foca a explicação. |
| `regression_cases` | query | Recuperar casos ligados a notas e hipóteses, com filtros de tags e paginação. |
| `domain_pack` | query | Consultar receitas de domínio sem carregar código de plugins. |
| `check_profiles` | query | Listar perfis de testes disponíveis quando o runner foi explicitamente ativado. |
| `check_run` | manage | Executar um perfil permitido e registrar o resultado observado. |
| `check_result` | query | Consultar recibo e validade atual das fontes capturadas. |
| `runtime_status` | query | Identificar a instância que respondeu, versão importada e alterações em disco desde sua criação. |

`plan`, `route`, `context` e `handoff` aceitam `investigation` opcional. O pacote inclui um resumo atualizado e próximas verificações, preservando o orçamento. Consultas gerais continuam disponíveis sem criar investigação. A persistência dessas operações respeita `memory_owner`: se a memória pertencer ao servidor externo, as operações de investigação/testes e referências embutidas são recusadas.

## Exemplo mínimo

Parâmetros de `investigation_save`, em um workspace que contenha `src/engine.py`:

```json
{
  "name": "retry",
  "expected_revision": 0,
  "body": {
    "objective": "Investigar duplicação após resposta perdida",
    "domain": "crypto-institutional",
    "hypotheses": [{"id": "h1", "statement": "O retry pode criar uma segunda ordem"}],
    "notes": [{"id": "n1", "text": "O incidente ocorreu depois de um timeout"}],
    "evidence": [{
      "id": "e1", "summary": "Observação do tratamento de timeout",
      "hypothesis_ids": ["h1"], "result": "supports", "files": ["src/engine.py"]
    }],
    "conclusions": [{
      "id": "c1", "statement": "A observação sustenta investigar o retry",
      "evidence_ids": ["e1"], "hypothesis_ids": ["h1"]
    }],
    "criteria": [{
      "id": "a1", "requirement": "Reproduzir o comportamento em teste",
      "conclusion_ids": ["c1"], "requires_observed_test": true
    }],
    "regressions": [{
      "id": "r1", "note_id": "n1", "hypothesis_id": "h1",
      "description": "Cenário de resposta perdida", "tags": ["retry", "timeout"]
    }]
  }
}
```

A fonte recebe um hash observado localmente. O critério acima permanece aberto, pois não há execução de teste observada. Uma afirmação do chamador de que o teste passou não substitui essa execução. Para obter a explicação, consulte `investigation` com `name: retry, conclusion_id: c1`.

`result: supports|refutes|inconclusive` é uma **avaliação do chamador**, não compreensão semântica automática do arquivo. Evidências sem fonte ou recibo ficam como relato. Evidência oposta atual para uma hipótese permanece relevante mesmo quando a conclusão seleciona apenas os itens favoráveis. Um resultado sustentado aparece como `supported_by_current_evidence`; isso não prova correção geral ou adequação do teste.

## Alterações, retomada e revalidação

Na próxima consulta, o NEXUS9 compara as fontes declaradas com seus hashes originais. Fontes alteradas, removidas ou recusadas pela política tornam as provas dependentes pendentes de revalidação. Fontes não relacionadas não invalidam a investigação. Não existe watcher em background; dependências omitidas pelo exportador não podem ser descobertas por esse mecanismo.

O objetivo, domínio e identidades/conteúdos das evidências são preservados. Atualizações usam `expected_revision`; dois escritores com a mesma revisão não podem sobrescrever um ao outro. Campos/coleções omitidos em uma extensão preservam o conteúdo existente. Para adicionar uma nota, envie o mesmo objetivo e a nova nota com ID único; não precisa reenviar o grafo inteiro.

Após corrigir o código, adicione **uma nova evidência**, com novo ID e novas fontes/recibo. Pode atualizar `evidence_ids` de uma conclusão ou `conclusion_ids` de um critério existente; seus textos e requisitos permanecem fixos. As revisões anteriores e snapshots são mantidos. Reenviar a evidência antiga não atualiza silenciosamente seus hashes.

Uma nota pode originar um caso de regressão ligado à hipótese e ao nome de um perfil de testes. Esse registro organiza o cenário e sua origem; não gera código de teste, não executa o caso automaticamente e não treina o modelo. O agente implementa o cenário no projeto dentro do pedido e registra a verificação realmente feita.

Limites: até 100 investigações, 100 nós/32 KiB por investigação e 500 revisões totais. Limites atingidos são recusados, sem apagar provas antigas. Consultas têm `offset`/`limit`, contagens, omissões explícitas e cursor; uma visão truncada não equivale ao grafo completo.

## Testes observados: opt-in

O runner vem **desabilitado**. O uso normal de contexto, memória e investigações não executa código do projeto. Para habilitá-lo em um projeto de testes confiável, adicione `--enable-test-runner` aos argumentos de início do servidor e crie `nexus9-checks.json` na raiz do workspace:

```json
{
  "profiles": {
    "regression": {
      "kind": "python_unittest",
      "start_dir": "tests",
      "pattern": "test_*.py",
      "timeout_seconds": 20
    }
  }
}
```

O diretório de testes precisa ser importável pela discovery, normalmente com `tests/__init__.py`. O perfil usa o Python do servidor; esse ambiente precisa das dependências dos testes. Use projetos sintéticos ou checks previamente inspecionados. Testes são código confiável do projeto e executam com as permissões do usuário, inclusive acesso a arquivos/rede: **o runner não é um sandbox**. O servidor não inicia serviços/exchanges por conta própria, mas não restringe esses efeitos no código dos testes. Não habilite o runner para launchers ou suites desconhecidas.

O MCP recebe somente `profile` e `sources`, sem executable/argv/shell/env arbitrários. `check_run` com `profile: regression, sources: ["src/engine.py"]` registra o código de saída, contagem, timeout, saída limitada/redigida e um recibo. O manifesto captura configuração, árvore Python dos testes e fontes explicitamente informadas; não representa todas as dependências possíveis do runtime. Uma nova fonte de teste, alteração de perfil, mudança/remoção de fonte capturada ou mudança durante a execução invalida o resultado. Zero testes, todos ignorados, apenas falhas esperadas, timeout ou falha do processo não contam como aprovação.

Vincule `run_id` a uma **nova evidência**. Fontes dessa evidência precisam estar cobertas pelo recibo. Critérios com `requires_observed_test` exigem uma execução aprovada e ainda atual no caminho de prova. A saída MCP mostra um resumo limitado do manifesto; o manifesto integral é mantido localmente. Até 100 recibos são preservados, sem descarte automático de evidências referenciadas. Recibos registram observações do processo local, não são assinaturas independentes ou prova de que um teste é suficiente para a conclusão.

## Pacotes de especialidade

`domain_pack` oferece `generic` e `crypto-institutional`. A receita cripto indica invariantes e ferramentas complementares como `crypto_audit`; isso não conecta outro MCP automaticamente nem afirma que ele está instalado. O agente precisa descobrir a ferramenta no host. O NEXUS9 continua útil sem o projeto cripto.

Outros projetos podem acrescentar um `nexus9-domains.json` de metadados:

```json
{
  "schema_version": "1.0",
  "packs": [{
    "id": "mobile", "title": "Aplicativo mobile", "scope": "Permissões e localização",
    "invariants": ["Preservar a política de permissões"],
    "evidence": ["Teste no dispositivo"], "external_tools": []
  }]
}
```

Não há carregamento de Python, execução de plugins ou ferramentas arbitrárias. A receita não certifica critérios e não invalida automaticamente provas por mudar seu texto; para torná-la uma dependência de evidência, registre seu arquivo em `files`. Metadados são conteúdo não confiável, com limite de 16 KiB e 10 receitas customizadas, sem substituir os IDs embutidos.

## Versão que está respondendo

`runtime_status` retorna versão importada, ID da instância, horário de criação e hashes dos arquivos observados no início e agora. Se os arquivos mudarem, `restart_required` sinaliza a necessidade de reiniciar; não afirma que bytes editados já foram carregados. O último recibo de `context`/`handoff` indica qual payload esse endpoint retornou.

Uma chamada real no IDE confirma a resposta daquele servidor. O status não verifica se a skill foi carregada pelo host nem se o modelo seguiu as instruções. Esta versão não implementa auto-update, hot reload, instalação coordenada entre IDEs ou substituição do contexto antigo de um chat. Para adotar 0.4, reinstale o pacote, atualize o MCP e confira `runtime_status` e a skill no host.
