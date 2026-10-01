# NEXUS9 0.3.0 — instalação no seu Antigravity

Baixe **NEXUS9-Antigravity-0.3.0-Windows.zip**. Este documento sozinho não contém
nem instala o servidor. O ZIP inclui código, instaladores, Skill nativa, testes
e relatórios. Nove módulos, 24 operações e três ferramentas MCP.

## 1. Colocar os arquivos em F:\SKILLS

Salve o ZIP em `F:\SKILLS`. Extraia-o nessa mesma pasta; ele já contém a pasta
`nexus9`. Se houver uma pasta antiga com esse nome, preserve-a com outro nome
antes de extrair. No PowerShell:

```powershell
Expand-Archive -LiteralPath 'F:\SKILLS\NEXUS9-Antigravity-0.3.0-Windows.zip' -DestinationPath 'F:\SKILLS'
Set-Location -LiteralPath 'F:\SKILLS\nexus9'
```

Confirme `install.ps1`, `install-for-your-pc.ps1`, `server.py`, `README.md` e
`skills\nexus9\SKILL.md`. O código real do servidor está em `src\nexus9`;
`server.py` também permite iniciar a partir da pasta extraída.

## 2. Instalar

Requer Python **3.12 ou 3.13, Windows 64 bits**, com PATH habilitado.
O caminho de Workspace abaixo precisa ser substituído pela **raiz do seu
projeto de código**. `F:\SKILLS\nexus9` é a pasta do pacote, não a raiz do projeto.

```powershell
.\install-for-your-pc.ps1 -Workspace 'CAMINHO_REAL_DO_PROJETO'
```

O atalho já usa os caminhos que você informou:

| Componente | Destino |
| --- | --- |
| MCP config ativo | `C:\Users\QG DUS GURI\.gemini\antigravity\mcp_config.json` |
| Skill nativa | `C:\Users\QG DUS GURI\.gemini\config\skills\nexus9\SKILL.md` |
| Hardware | Light, sem embeddings ou workers em background |
| Dono de memória/compressão | Auto, após diagnóstico |

Para revisar o plano sem instalar: acrescentar `-PlanOnly`. Se uma entrada
NEXUS9 ou uma Skill diferente já existir, o instalador preserva essa versão e
recusa a troca; use `-ReplaceExisting` para atualizar com backup. Não precisa de
administrador. O download inicial das dependências requer internet.

O instalador verifica hashes do pacote, testa dependências e realiza handshake
MCP em um projeto temporário antes de registrar a integração. Anota o caminho
do recibo de instalação para reversão. Em falhas parciais, tenta restaurar as
mudanças e preserva recibos para recuperação.

## 3. HYDRA e agentMemory

O instalador **não pausa nem apaga** outros MCPs, hooks ou regras. Com HYDRA/
agentMemory detectados, mantém as funções sobrepostas com dono externo e o
NEXUS9 bloqueia suas operações correspondentes. As demais funções continuam
ativas. Confira o diagnóstico:

```powershell
.\doctor.ps1 -Workspace 'CAMINHO_REAL_DO_PROJETO'
```

Para transferir memória e compressão ao NEXUS9, revise as regras/hooks que o
diagnóstico listar, pause somente os concorrentes no IDE e então execute:

```powershell
.\install-for-your-pc.ps1 -Workspace 'CAMINHO_REAL_DO_PROJETO' -MemoryOwner Nexus9 -CompressionOwner Nexus9 -ReplaceExisting
```

Menções em arquivos são candidatas, não prova de hooks ativos. Inspecione também
Customizations e locais personalizados. Não use dois compressores/memórias na
mesma tarefa.

## 4. Verificar no Antigravity

Atualize os servidores MCP. Confirme `nexus_catalog`, `nexus_query` e
`nexus_manage`; confirme a Skill `nexus9` em **Customizations**. Peça:

> Use a Skill NEXUS9 neste projeto. Confira a política de dono de cada função,
> monte contexto mínimo preservando minhas restrições, informe omissões e valide
> a alteração com os testes reais do projeto. Preserve as decisões no dono de
> memória indicado pela política. Consulte health para confirmar a integração.

No Antigravity 2.0, a Skill também pode ser invocada com `/nexus9`. A Skill
orquestra as três ferramentas; ela não substitui o processo Python/MCP.

## 5. Reverter ou medir

Com o caminho de recibo exibido pelo instalador:

```powershell
.\rollback.ps1 -Receipt 'CAMINHO_DO_RECIBO_JSON'
```

A reversão preserva alterações posteriores de outros servidores e recusa
sobrescrever uma Skill/entrada NEXUS9 editada pelo usuário. Runtime e memória
não são apagados.

O perfil Light limita cada refresh a 120 arquivos, 24 novas análises, 8 MiB e
2 segundos cooperativos, com lotes rotativos. Fontes de parser ficam limitadas
a 512 KiB. Descoberta é reutilizada por até 30 segundos; os arquivos selecionados
para contexto são relidos e têm hash verificado. Não há promessa de CPU zero.

Consulte `docs/VALIDATION.md`, `docs/performance.json`, `docs/OPERATIONS.md` e
`docs/SECURITY.md`. Os testes locais não substituem validação no seu Windows,
na sua versão do Antigravity e no tamanho real do projeto. A economia efetiva
precisa ser medida com usage do provedor e qualidade das tarefas.
