# NEXUS9 — Motor de Eficiência de Contexto para Antigravity

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL_3.0-blue.svg)](LICENSE)
[![Author: Everton Fridrich](https://img.shields.io/badge/Author-Everton%20Fridrich-orange.svg)](https://github.com/evertonfridrich-ops)
[![MCP Ready](https://img.shields.io/badge/MCP-Protocol-green.svg)](https://modelcontextprotocol.io)

> **Criado e mantido por [Everton Fridrich](https://github.com/evertonfridrich-ops).**

**Projeto novo com nove módulos executáveis, 24 operações e Skill nativa.**
Executa análise, seleção, deduplicação, memória e auditoria localmente; a Skill
orquestra três ferramentas MCP com descoberta progressiva.

Versão 0.3.0: implementação local testada, com arquitetura e controles voltados
a uso profissional. Instalação Windows/Antigravity real, revisão independente e
medição com o provedor ainda precisam ser concluídas antes de declarar produção
institucional. Não há certificação ou percentual garantido de economia.

## As nove cabeças e o que realmente fazem

| Cabeça | Função implementada | Benefício concreto |
|---|---|---|
| 1. Orchestrator | Classifica a tarefa por política, sugere operações e validação | Evita começar com leituras e ferramentas indiscriminadas |
| 2. Tool Router | Catálogo progressivo e seleção por tags de ferramentas informadas | Só três schemas MCP fixos; parâmetros das 24 operações sob demanda |
| 3. Context Compiler | Índice por SHA-256, ranking lexical, parser TS/TSX/JS/Python, símbolos, referências e imports | Monta pacote com código alvo, declarações relacionadas e dependências locais |
| 4. Project Memory | Restrições, decisões, pendências e evidências com origem e revisão | Preserva decisões do projeto e identifica fontes alteradas na retomada |
| 5. Delta & Cache | Snapshots explícitos, unified diff, cache de respostas com fontes e TTL | Reutiliza somente fontes válidas e mostra alterações desde a leitura conhecida |
| 6. Budget Governor | Orçamentos atômicos, política de dono e health check | Limita volume e bloqueia funções atribuídas a outros servidores |
| 7. Local Reducer | Logs agrupados, deduplicação exata e seleção por prioridade | Processa volume localmente, preserva blocos obrigatórios e expõe omissões |
| 8. Usage & Evaluation | Telemetria, registro idempotente de usage e comparação pareada de tarefas | Separa redução de texto de tokens reportados e sinaliza regressão de qualidade |
| 9. Scoped Handoff | Brief de papel/tarefa com contexto, restrições e validação | Prepara uma passagem de tarefa pequena e verificável, sem iniciar agentes |

Por exemplo: numa correção do GPS do MotoRoute, pode selecionar a função de
tracking, incluir as opções globais que ela referencia e recuperar o corpo de
uma função local importada. Mantém “não atualizar Expo/RN” na memória. Se um
trecho necessário não couber, informa a omissão; não corta silenciosamente
essas restrições para aparentar economia.

## Instalar no Windows

Leia `COMECE-AQUI.md`. Extraia **o ZIP completo** em `F:\SKILLS`; ele já contém
uma pasta `nexus9`. Confirme `F:\SKILLS\nexus9\install.ps1`, `server.py`,
`README.md` e `skills\nexus9\SKILL.md`. Baixar apenas um `.md` não instala o projeto.
Instale Python 3.12 ou 3.13 com PATH, abra PowerShell nessa pasta e execute:

```powershell
.\install-for-your-pc.ps1 -Workspace "CAMINHO_REAL_DO_PROJETO"
```

Esse atalho usa os caminhos que você informou:

- MCP config: `C:\Users\QG DUS GURI\.gemini\antigravity\mcp_config.json`.
- Skill: `C:\Users\QG DUS GURI\.gemini\config\skills\nexus9\SKILL.md`.
- Hardware: `Light`; memória/compressão: `Auto`.

`-Workspace` é a raiz do projeto de código que o NEXUS9 poderá ler; não é a pasta
onde o pacote foi extraído. Para outro computador, use `install.ps1` com
`-ConfigPath` e `-SkillPath` explícitos. Se não houver escolha explícita e duas
configs forem detectadas, o instalador exige o caminho mostrado em View raw config.
Atualize os servidores MCP e verifique a Skill em Customizations após instalar.

O runtime usa um ambiente Python isolado em
`%LOCALAPPDATA%\NEXUS9\runtime-0.3.0-<hash>`. Não precisa de administrador, chave API
ou serviço HTTP. Dependências são fixadas e verificadas por hashes. O download
inicial requer internet; as operações usam arquivos e estado locais. O modelo
continua podendo receber os trechos retornados através do IDE.

O instalador verifica o manifesto, pré-valida conflitos e executa handshake MCP
real em um projeto temporário antes de registrar o servidor. Instala a Skill
nativa automaticamente. `-InstallRule` acrescenta a regra de projeto opcional;
a Skill já orienta o fluxo e normalmente dispensa a regra adicional.

Para outro projeto, use `-ServerName nexus9-outro` em `install.ps1`. O mesmo runtime
íntegro é reutilizado; releases diferentes usam outra pasta e não sobrescrevem
um runtime em uso. `-ReplaceExisting` autoriza substituir apenas a entrada/Skill/
regra de mesmo nome, sempre com backup e recibo de reversão. A instalação registra
as mudanças e tenta revertê-las em falhas; vários arquivos não formam uma transação
atômica de filesystem. Veja `docs/OPERATIONS.md` para recuperação após interrupção.

## Coexistência com HYDRA e agentMemory

`doctor.ps1 -Workspace "CAMINHO_REAL_DO_PROJETO"` inspeciona o config e locais
conhecidos de regras/hooks, sem exibir comandos, variáveis de ambiente ou seus
conteúdos. Nomes habilitados no config não provam conexão ativa; menções em regras
são candidatas para revisão. O inventário é limitado e não garante descobrir hooks
em todos os plugins/locais personalizados.

Em `Auto`, HYDRA ou regras HYDRA detectadas atribuem memória e compressão ao dono
externo; agentMemory detectado atribui memória ao dono externo. NEXUS9 então
**recusa** suas operações sobrepostas, inclusive referências de memória em
context/handoff. A política aparece no catálogo e em `health`; as demais funções
continuam disponíveis. O instalador preserva os outros servidores, regras e hooks.

Para transferir essas funções ao NEXUS9, pause os hooks/regras concorrentes
identificados no seu IDE e execute novamente com `-MemoryOwner Nexus9
-CompressionOwner Nexus9 -ReplaceExisting`. Isso reconfigura NEXUS9; não pausa
HYDRA automaticamente. Preserve funções complementares e os dados do agentMemory.
Não execute dois compressores/memórias para a mesma tarefa.

## Interface MCP compacta

- `nexus_catalog(operation="")`: mostra as nove cabeças. Informe uma operação
  para obter seu schema detalhado.
- `nexus_query(operation, parameters, session?)`: consulta e análise local.
- `nexus_manage(operation, parameters, session?)`: alterações explícitas do estado
  local, como memória, cache, usage e orçamento. Não edita o código do projeto.

As operações MCP não são slash commands. A Skill pode ser solicitada pelo nome
NEXUS9; no Antigravity 2.0 há invocação manual `/nexus9`. Verifique a superfície
e versão em uso. O agente deve descobrir o schema antes de chamar a operação.

## Operações disponíveis

| Tipo | Operações |
|---|---|
| Planejamento/roteamento | `plan`, `route` |
| Código/contexto | `index`, `context`, `outline`, `snippet`, `impact`, `verify` |
| Memória/retomada | `memory_save`, `memory`, `resume` |
| Alterações/reutilização | `remember_read`, `delta`, `cache_save`, `cache` |
| Orçamento/política | `session_open`, `session_close`, `health` |
| Redução | `logs`, `compress` |
| Auditoria/avaliação | `usage_record`, `metrics`, `evaluate` |
| Passagem de tarefa | `handoff` |

## Exemplo: contexto com função e dependências

Argumentos de `nexus_query`:

```json
{
  "operation": "context",
  "parameters": {
    "task": "Corrigir startWatching no GPS",
    "paths": ["src/hooks/useGPSTracking.ts"],
    "focus_symbols": {"src/hooks/useGPSTracking.ts": "startWatching"},
    "constraints": ["Manter Expo 52.0.49 e React Native 0.76.9"],
    "profile": "balanced",
    "budget_bytes": 12000
  }
}
```

Se houver dois símbolos com o mesmo nome, descubra o nome qualificado via
`outline`, por exemplo `useGPSTracking.startWatching`. `coverage` e `omitted`
informam o que precisa ser expandido. O pacote não prova que todo o contexto
necessário da tarefa foi encontrado.

`known_hashes` permite omitir um arquivo **somente quando o chamador declara que
o conteúdo daquele digest está no contexto ativo**. O servidor verifica o SHA-256
atual, mas não consegue verificar se o IDE manteve o conteúdo na conversa.

## Exemplo: memória do projeto

Argumentos de `nexus_manage`:

```json
{
  "operation": "memory_save",
  "parameters": {
    "name": "gps",
    "expected_revision": 0,
    "body": {
      "goal": "Resolver localização parada",
      "constraints": [{"text": "Não atualizar Expo/RN", "source": "user"}],
      "decisions": [{"text": "Investigar callback do watch", "source": "agent"}],
      "pending": ["Testar deslocamento no Android físico"],
      "files": ["src/hooks/useGPSTracking.ts"],
      "validation": []
    }
  }
}
```

Na próxima sessão, use `resume` com `name: "gps"`; ele revalida arquivos.
Para atualizar, forneça a revisão retornada por `memory`.
Origens `test_result` e `verified_file` são rótulos informados pelo chamador,
nunca uma certificação automática da afirmação. Digests são observados localmente.

## Exemplo: diff e orçamento

1. Abra uma sessão com `session_open` em `nexus_manage`:

```json
{"name":"gps","call_budget_bytes":12000,"total_budget_bytes":250000,"profile":"balanced"}
```

2. Somente após observar o arquivo completo no contexto ativo, confirme a base
   com `remember_read`, incluindo `session: "gps"`. Um snippet parcial não serve
   como baseline completo para interpretar o diff sozinho.
3. Após uma alteração, use `delta` com a mesma sessão e caminho. A resposta
   mostra somente o diff ou informa que a fonte está igual. Não avança a base.
4. Confirme a nova base com `remember_read` e a revisão esperada quando fizer sentido.

Snapshots são limitados a 128 KiB. Arquivos maiores devem usar pacotes de símbolos.
Abrir a mesma sessão não zera o consumo. Encerrar uma sessão impede novas consultas.
Para recomeçar conscientemente, use um nome novo.

## Controles e limites

- Raiz absoluta obrigatória; recusa caminhos externos/travessia/ADS,
  symlinks/reparse points detectáveis, hardlinks e arquivos especiais.
- Bloqueia nomes comuns de segredos e diretórios de dependências/build.
- Redação de credenciais conhecidas antes de expor texto; não é DLP completo.
- Schemas estritos por operação, com recusa de campos desconhecidos e coerções.
- Dados, logs e memória marcados como conteúdo não confiável.
- SQLite com transações para orçamento, revisões e snapshots; telemetria sem
  conteúdo dos argumentos, código ou credenciais.
- Nenhum handler apaga arquivos do projeto ou executa o código recuperado.

| Recurso | Limite |
|---|---:|
| Fonte para parser/índice | Light: 512 KiB; Standard: 2 MiB por arquivo |
| Refresh Light | Até 120 arquivos/24 novas análises, 8 MiB e 2 s cooperativos por rodada; lotes rotativos |
| Refresh Standard | 250 arquivos padrão; até 1.000 solicitado, 64 MiB e 8 s cooperativos |
| Inventário de diretório | Light: 1.200 entradas/1 s; Standard: 5.000 entradas/3 s |
| Índice persistente | 5.000 arquivos; histogramas até 1.000 termos por arquivo |
| Inventário para ranking/grafo | Light: 512 registros recentes mais paths explícitos/dependências; cobertura parcial informada |
| Resposta de consulta | Até 24 KiB de JSON textual; orçamento menor por sessão |
| Perfil economy/balanced/rigorous | 4/12/24 KiB e 1/3/5 fontes principais antes das fontes explícitas |
| Log | Streaming até 64 MiB ou 3 s cooperativos |
| Snapshots | 100 snapshots no total; até 128 KiB cada |
| Memórias/sessões/cache de respostas | 100 de cada por projeto |
| Usage/telemetria | 10.000 entradas de cada |

O resultado MCP tem uma única representação JSON textual, evitando duplicação
texto/structuredContent. Os limites medem essa representação, não o envelope,
schemas, conversa ou tokens internos do modelo. Operações administrativas e
catálogo ficam fora do orçamento acumulado de consultas, para permitir gestão.

O índice usa ranking lexical semelhante a BM25, não embeddings nem um LLM extra.
Não usa PyTorch/SentenceTransformers e não inicia workers em background. Em Light,
context/impact reutilizam descoberta por até 30 s, mas contexto relê as fontes
selecionadas e verifica hashes; arquivos explícitos e imports diretos novos são
atualizados. O grafo/descoberta pode estar defasado; `index_cached`/`index_age_seconds`
informam isso. `index` solicita refresh explícito respeitando os mesmos limites.
Limites são cooperativos, não CPU quotas. AST, hashing e SQLite têm custo real;
não há promessa de impacto quase nulo no Kaby Lake. Meça com `scripts/benchmark.py`
no seu computador antes de ampliar escopo.
O grafo resolve imports locais convencionais; aliases TypeScript, resolução por
bundler, imports dinâmicos, chamadas indiretas e bibliotecas externas não são
resolvidos completamente. Referências locais são heurísticas sintáticas, não
análise de tipos ou call graph. `verify` verifica gramática; rode `tsc`, build e
testes reais para validar comportamento.

`compress` deduplica blocos exatos e seleciona por prioridade. Não inventa um
resumo semântico, não garante preservação de significado entre blocos diferentes
e não apaga a conversa do IDE. Conteúdo obrigatório que excede o orçamento causa
recusa. Texto omitido é identificado, e deve ser recuperado se necessário.

## Dados locais e segurança

Estado em `%LOCALAPPDATA%\Nexus9\<identificador-do-projeto>\state.sqlite3`
no Windows, ou `~/.local/state/Nexus9/` no Linux. Armazena índice/metadados,
memória, cache redigido, snapshots redigidos e contadores. Não há criptografia
própria em repouso ou ACL empresarial imposta. Use proteção de disco/permissões
do usuário. TTL limita reutilização de cache; não garante exclusão física.

Copie `.nexusignore.example` para `.nexusignore` no projeto para excluir dados
adicionais. Usa globs relativos simples, não toda a sintaxe de `.gitignore`.
Reinicie o servidor após alterar exclusões.

Leia `docs/SECURITY.md` para o escopo de confiança e os critérios operacionais.

## Testes e demonstração

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts\demo.py
```

O cenário offline verifica função alvo, configuração global referenciada, corpo
de uma dependência local, restrição de stack, orçamento, delta e 4.000 logs
agrupados. Não mede qualidade de um modelo nem faturamento.

CI Windows/Linux e Python 3.12/3.13 incluído, com actions fixadas por SHA. Ainda
precisa ser executado no repositório de destino. Nenhum repositório foi publicado.

## Desinstalar/reverter

Execute `rollback.ps1 -Receipt "CAMINHO_DO_RECIBO_JSON"` com o recibo mostrado
pelo instalador, em `%LOCALAPPDATA%\NEXUS9\installations`. A reversão verifica
hashes, restaura os arquivos anteriores e preserva servidores/configs adicionados
depois da instalação. Recusa sobrescrever arquivos da Skill ou a entrada NEXUS9
editados posteriormente. O runtime e a memória do projeto são preservados.
Após reverter, atualize MCPs e Skills no IDE. Remova runtime/estado manualmente
apenas quando não forem mais necessários; remoção do estado elimina checkpoints.

## Referências

- [HYDRA do seu amigo](https://github.com/Mailor-Jorge/hydra-tokens-antigravity)
- [Antigravity MCP](https://antigravity.google/docs/mcp)
- [Antigravity Rules](https://antigravity.google/docs/rules)
- [Antigravity Skills](https://antigravity.google/docs/skills)
- [SDK oficial MCP](https://github.com/modelcontextprotocol/python-sdk)
- [Tree-sitter Python bindings](https://github.com/tree-sitter/py-tree-sitter)

## Licença, Direitos Autorais e Dual Licensing

* **Licença Open Source:** O código-fonte do NEXUS9 é licenciado sob a [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).
* **Marca Registrada:** O nome **NEXUS9™** e elementos visuais associados são marcas de **Everton Fridrich** e não são transferidos pela licença AGPL. Consulte [TRADEMARKS.md](TRADEMARKS.md).
* **Licença Comercial / Enterprise:** Para incorporação em software proprietário fechado, distribuição OEM ou infraestrutura corporativa que não possa seguir as obrigações da AGPLv3, licenças comerciais personalizadas estão disponíveis via `evertonfridrich@gmail.com`.
* **Contribuições:** Todas as contribuições de terceiros são regidas pelo [Contributor License Agreement (CLA)](CLA.md).
