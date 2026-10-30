# NEXUS9 sozinho no Antigravity

Este manual cobre o **NEXUS9 0.4.0** no Antigravity IDE para Windows. Ele funciona sem o QUANT9: oferece contexto de código, memória, investigações e evidências para projetos de software em geral. Para combinar os dois, siga [uso conjunto](USO-CONJUNTO.md).

O pacote contém duas partes que precisam estar disponíveis: o **servidor MCP**, executado em Python, e a **skill `nexus9`**, com as instruções de uso pelo agente. Copiar somente `SKILL.md`, clonar o repositório ou publicar uma versão no GitHub não inicia o servidor no IDE.

## 1. Prepare as três localizações

Requisitos: Antigravity IDE, Windows 64 bits e Python **3.12 ou 3.13** no PATH. O download inicial das dependências requer internet; não são necessárias chaves de exchange ou de modelo para instalar este servidor local.

| Localização | Exemplo | O que significa |
| --- | --- | --- |
| Pacote NEXUS9 | `C:\Ferramentas\nexus9` | Código, instalador e skill de origem. |
| Projeto analisado | `C:\Projetos\meu-projeto` | Raiz do código em que você quer trabalhar. |
| Configuração MCP | `<projeto>\.agents\mcp_config.json` ou o arquivo global ativo | Onde o Antigravity encontra o comando do servidor. |

Baixe e extraia o ZIP completo da versão 0.4.0 ou obtenha o repositório completo. Confirme que a pasta do pacote contém `install.ps1`, `integration.py`, `requirements.lock.txt` e `skills\nexus9\SKILL.md`. Abra a pasta **do projeto analisado** como workspace no Antigravity.

O argumento `-Workspace` do instalador vira `--root` no servidor. Ele deve apontar para o projeto analisado, não para a pasta do NEXUS9. Abrir outra pasta no editor não altera o `--root` de uma entrada MCP global já cadastrada.

## 2. Escolha um único escopo de instalação

Antes de instalar, abra **⋯ → MCP Servers → Manage MCP Servers → View raw config** no painel do agente. Confira também **Customizations** para ver as skills disponíveis.

Para uma **instalação nova**, este manual usa configuração e skill no workspace:

```text
meu-projeto/
  .agents/
    mcp_config.json
    skills/
      nexus9/
        SKILL.md
```

Se já existe uma entrada `nexus9` global, ou uma skill global com esse nome, escolha qual instalação manter antes de criar a local. A localização global documentada é `%USERPROFILE%\.gemini\config\mcp_config.json`; skills globais ficam em `%USERPROFILE%\.gemini\config\skills`. Versões antigas podem usar caminhos legados. Use o arquivo mostrado pelo seu IDE; não presuma que o primeiro arquivo encontrado é o ativo.

**Não mantenha duas cópias conflitantes do mesmo servidor/skill contando com uma precedência implícita.** Para continuar global, use o caminho real do config e da skill globais nas variáveis abaixo. Uma entrada global fica vinculada ao seu `--root`; atualize essa raiz deliberadamente ao trocar de projeto ou use uma configuração por workspace.

## 3. Defina o dono da memória e da compressão

| Situação | Configuração de dono |
| --- | --- |
| Somente NEXUS9 exerce essas funções | `MemoryOwner Nexus9` e `CompressionOwner Nexus9`. |
| Outro servidor deve continuar dono | `External` para a função correspondente. |
| Você quer diagnóstico conservador primeiro | `Auto`, seguido da conferência da política resultante. |

`Auto` pode encontrar HYDRA, agentMemory ou regras relacionadas e selecionar dono externo. O diagnóstico tem escopo limitado: confira também os servidores globais e hooks ativos no IDE, mesmo quando estiver instalando um config local.

Na versão 0.4, memória externa também bloqueia as operações de investigação, casos de regressão e recibos de testes do NEXUS9. Contexto e demais capacidades não sobrepostas podem continuar disponíveis. Se decidir transferir a propriedade ao NEXUS9, pause somente as funções concorrentes reais antes de usar essa configuração. O instalador não desativa outros servidores/hooks e a troca de dono não migra o histórico de outra ferramenta.

## 4. Revise o plano e instale

No PowerShell, ajuste os caminhos para **pastas existentes**. O exemplo abaixo pressupõe que não há outro dono ativo de memória/compressão nessa tarefa:

Se o PowerShell bloquear a execução dos scripts e você já tiver revisado a origem do pacote, a opção abaixo vale somente para a sessão atual:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Ela não exige mudar a política global ou abrir o terminal como administrador. Fechar o PowerShell encerra essa configuração de processo. Uma política corporativa pode prevalecer; nesse caso, siga a política do ambiente em vez de alterar configurações globais para contorná-la.

```powershell
$Projeto = 'C:\Projetos\meu-projeto'
$Nexus = 'C:\Ferramentas\nexus9'
$Config = Join-Path $Projeto '.agents\mcp_config.json'
$Skill = Join-Path $Projeto '.agents\skills\nexus9'

$Parametros = @{
    Workspace = $Projeto
    ConfigPath = $Config
    SkillPath = $Skill
    HardwareProfile = 'Light'
    MemoryOwner = 'Nexus9'
    CompressionOwner = 'Nexus9'
}

& (Join-Path $Nexus 'install.ps1') @Parametros -PlanOnly
```

Confira a raiz, o arquivo de configuração, o destino da skill e os donos exibidos. `-PlanOnly` não instala runtime nem altera config/skill. Se o plano estiver correto:

```powershell
& (Join-Path $Nexus 'install.ps1') @Parametros
```

O instalador valida o manifesto do pacote, cria um runtime isolado identificado por versão/hash, verifica dependências e executa um handshake MCP em projeto temporário. Só depois registra a entrada e instala a skill. Preserve o caminho do recibo exibido para reversão. O pacote de origem deve permanecer íntegro; depois de editar seus arquivos, gere o pacote conforme o procedimento do projeto antes de usá-lo como distribuição.

`Light` limita o trabalho local por consulta e é uma opção inicial para máquinas com poucos recursos. Não limita diretamente o contexto do modelo nem garante economia de tokens. `Standard` amplia os limites locais quando o projeto exigir.

## 5. Confirme dentro do IDE

Recarregue os servidores MCP e abra um chat novo no workspace escolhido. Confirme a skill `nexus9` em **Customizations** e as três ferramentas:

```text
nexus_catalog
nexus_query
nexus_manage
```

Peça ao agente:

> Use a skill nexus9. Consulte nexus_catalog e descubra os schemas de runtime_status e health. Execute essas consultas e informe a versão, a instância que respondeu e os donos de memória/compressão. Depois recupere um trecho pequeno de um arquivo que eu indicar deste workspace, para verificar a raiz configurada. Não execute o projeto.

Resultado esperado para esta versão:

- `runtime_status` responde **0.4.0**. `restart_required=true` pede recarregamento; não significa que bytes novos já foram carregados.
- `health` informa integridade local e a política de dono escolhida.
- Um arquivo exclusivo do projeto correto pode ser recuperado; erro de caminho pode indicar raiz incorreta.
- A skill e o servidor estão disponíveis na mesma sessão. Uma chamada bem-sucedida comprova a resposta do endpoint, não compreensão ou obediência do modelo.

Para uma investigação com vários passos:

> Investigue este problema com NEXUS9. Registre objetivo, hipóteses, fontes e critérios. Vincule as evidências às conclusões e informe o que ficou pendente. Antes de concluir, consulte novamente a investigação para revalidar as fontes.

As nove cabeças são módulos de software; o host determina se há agentes independentes. O runner opcional de testes fica **desabilitado por padrão**. O uso normal de contexto/investigações não exige ativá-lo. Veja [investigações e testes observados](INVESTIGATIONS.md) antes de habilitar perfis de testes confiáveis; esse runner não é um sandbox.

## 6. Atualize sem confundir fonte, runtime e skill

Uma atualização possui três etapas: atualizar o pacote de origem, reinstalar o runtime/skill e recarregar o servidor/chat. Editar o repositório não atualiza uma cópia instalada automaticamente.

Para substituir uma entrada/skill existente, mantendo o mesmo escopo e após revisar personalizações:

```powershell
& (Join-Path $Nexus 'install.ps1') @Parametros -ReplaceExisting -PlanOnly
& (Join-Path $Nexus 'install.ps1') @Parametros -ReplaceExisting
```

A substituição conserva backup/recibo. Não use `-ReplaceExisting` para resolver um conflito sem conferir os destinos. Se existirem duas skills de mesmo nome em escopos diferentes, atualizar apenas uma não sincroniza a outra. Preserve personalizações antes de escolher uma única origem de descoberta.

Após recarregar, repita `runtime_status`, `health` e a leitura do arquivo exclusivo do projeto. Ao trocar Gemini por Claude **dentro do Antigravity**, os servidores pertencem ao mesmo host, mas confirme novamente a seleção da skill e as chamadas necessárias; não há garantia de aplicação automática idêntica entre modelos.

## 7. Diagnostique e reverta

Use os caminhos escolhidos na instalação:

```powershell
& (Join-Path $Nexus 'doctor.ps1') -Workspace $Projeto -ConfigPath $Config -SkillPath $Skill
```

O diagnóstico informa candidatos/configuração; cadastro não prova conexão ativa. O IDE e uma chamada real confirmam o endpoint acessível na sessão.

| Sintoma | Conferência |
| --- | --- |
| Ferramentas não aparecem | Config ativo, comando Python existente, recarregamento e logs MCP do IDE. |
| Só a skill aparece | O processo MCP também precisa estar instalado e conectado. |
| Acessa outro projeto | `--root` da entrada e o workspace aberto. |
| Investigação recusada por política | `health`/`runtime_policy`; memória externa bloqueia essas operações. |
| Versão antiga após editar | Runtime instalado e processo ainda aberto; reinstale/recarregue. |
| Duplicidade de skills | Cópias globais e locais; escolha uma origem e preserve a personalização. |
| Test runner desabilitado | Comportamento inicial esperado; não o ative para fazer uma auditoria parecer aprovada. |

### O instalador informa pacote incompleto ou alterado

Prefira o **ZIP de distribuição da release**, gerado com seu manifesto, e extraia o pacote completo em uma pasta nova. O ZIP automático de código-fonte do GitHub não deve ser presumido idêntico ao artefato de distribuição verificado. Um checkout Git pode converter finais de linha LF/CRLF e alterar os bytes usados nos hashes, mesmo quando o texto parece igual.

Confira a versão e a origem do pacote antes de repetir a instalação. Quem desenvolve o projeto deve gerar uma nova distribuição pelo procedimento de release, com `scripts/package_release.py`, e validar seu manifesto. Não desative a checagem nem substitua hashes arbitrariamente para aceitar um pacote divergente.

Para reverter uma instalação gerenciada, use o recibo exibido pelo instalador:

```powershell
& (Join-Path $Nexus 'rollback.ps1') -Receipt 'C:\CAMINHO\DO\RECIBO\receipt.json'
```

A reversão recusa sobrescrever entradas/skills gerenciadas que foram editadas depois. Consulte [operação e recuperação](OPERATIONS.md) para falhas parciais. Para integrar QUANT9, continue pelo [manual conjunto](USO-CONJUNTO.md).

Documentação oficial consultada em **30/10/2026**: [MCP no Antigravity](https://antigravity.google/docs/mcp) e [skills no Antigravity](https://antigravity.google/docs/skills). Interfaces e caminhos podem variar por versão; o menu/config mostrado pelo host é a referência para a instalação em uso.
