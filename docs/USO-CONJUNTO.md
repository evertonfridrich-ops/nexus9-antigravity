# NEXUS9 + QUANT9 no Antigravity

Este manual é distribuído nos dois repositórios. Os projetos funcionam separadamente; use o conjunto quando precisar de contexto/investigações e de verificações específicas de um robô cripto. Para usar somente o projeto deste repositório, siga [o manual individual](ANTIGRAVITY.md).

| Componente | Responsabilidade | Identificador técnico |
| --- | --- | --- |
| Antigravity | Executar o agente e disponibilizar as skills/ferramentas | Host do modelo escolhido |
| NEXUS9 0.4 | Contexto por símbolos, memória, investigações e evidências | Skill/servidor `nexus9`; ferramentas `nexus_*` |
| QUANT9 3.0 | Especialidades e auditorias offline de robôs cripto | Skill/servidor `crypto-institutional`; pacote `crypto_institutional`; ferramentas `crypto_*` |

São nove módulos por projeto, não nove modelos iniciados automaticamente. O agente coordena o uso. O QUANT9 não exige NEXUS9 e não fornece uma segunda memória/compressão concorrente. O NEXUS9 não assume que outro MCP está conectado apenas porque uma receita cita seu nome.

## 1. Escolha a raiz e o escopo antes de instalar

Exemplos Windows/PowerShell, com Python **3.12 ou 3.13, 64 bits**, compatível com ambos. Substitua os três caminhos por pastas existentes; não copie os caminhos de outro usuário:

```powershell
$Projeto = (Resolve-Path -LiteralPath 'C:\Projetos\meu-robo').Path
$Nexus = (Resolve-Path -LiteralPath 'C:\Ferramentas\nexus9').Path
$Quant = (Resolve-Path -LiteralPath 'C:\Ferramentas\QUANT9').Path
$Config = Join-Path $Projeto '.agents\mcp_config.json'
$SkillNexus = Join-Path $Projeto '.agents\skills\nexus9'
```

`$Projeto` é o código do robô. `$Nexus` e `$Quant` são os pacotes extraídos/clonados, mantidos em pastas próprias. O nome da pasta QUANT9 é livre; os identificadores Python/MCP acima permanecem iguais. Não use a pasta de um pacote como raiz do outro nem como workspace do robô.

Para o NEXUS9, prefira o **ZIP completo da release**, cujo manifesto corresponde aos bytes distribuídos. Um checkout Git com conversão LF/CRLF ou arquivos editados pode falhar na verificação de integridade. Nesse caso obtenha o pacote íntegro ou siga o procedimento de geração de pacote; não desabilite a verificação.

Para **instalação nova**, este guia usa configuração e skills **por workspace**:

```text
meu-robo/
  .agents/
    mcp_config.json
    skills/
      nexus9/SKILL.md
      crypto-institutional/SKILL.md
```

O Antigravity também aceita configuração/skills globais em `~/.gemini/config/`. **Se já há instalações globais, faça primeiro a revisão da seção 7.** Não presuma qual cópia vencerá quando houver nomes duplicados em escopos diferentes. A precedência pode variar por superfície/versão. No IDE, o menu **⋯ > MCP Servers > Manage MCP Servers > View raw config** ajuda a localizar a configuração; confira o caminho aberto, pois este guia usa `$Config` no workspace, não necessariamente o global.

## 2. Defina um único dono de memória e compressão

Quando só NEXUS9 e QUANT9 atendem este projeto, a configuração recomendada é:

| Opção do NEXUS9 | Valor |
| --- | --- |
| `--root` | A pasta `$Projeto` |
| `--hardware` | `light` para começar; `standard` quando o volume exigir |
| `--memory-owner` | `nexus9` |
| `--compression-owner` | `nexus9` |
| `--enable-test-runner` | Ausente inicialmente |

Se houver HYDRA, agentMemory, hooks ou regras de memória/redução, revise o que realmente está ativo no IDE. Pause apenas a função concorrente antes de transferir a propriedade ao NEXUS9. Outros MCPs, como GitHub/Linear, podem continuar disponíveis. A instalação **não pausa nem apaga** esses componentes.

`Auto` é conservador: pode selecionar `external` quando detectar concorrentes. Na versão 0.4, memória externa também bloqueia as operações de investigação e recibos de testes. Se deseja manter outro dono, isso é uma configuração válida, com essa limitação; não force `Nexus9` só para esconder o diagnóstico. Alterar a flag não transfere o histórico do outro servidor. Configuração cadastrada e menção em regra não comprovam conexão/execução ativa.

## 3. Instale o NEXUS9 no workspace escolhido

Use o pacote completo e intacto. O instalador verifica o manifesto antes de registrar. Na primeira instalação:

```powershell
$OpcoesNexus = @{
    Workspace = $Projeto
    ConfigPath = $Config
    SkillPath = $SkillNexus
    HardwareProfile = 'Light'
    MemoryOwner = 'Nexus9'
    CompressionOwner = 'Nexus9'
}
& (Join-Path $Nexus 'install.ps1') @OpcoesNexus -PlanOnly
```

Confira a raiz, o config, a skill e os donos. `PlanOnly` não instala runtime/config/skill. Para aplicar o mesmo plano:

```powershell
& (Join-Path $Nexus 'install.ps1') @OpcoesNexus
```

Se o PowerShell bloquear o script por política, em uma sessão dedicada você pode permitir a execução somente naquele processo e repetir a chamada com os mesmos parâmetros:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Essa opção termina quando a sessão é fechada; não exige administrador nem altera permanentemente a política da máquina. Uma política organizacional pode prevalecer; nesse caso use o procedimento aprovado pelo administrador. Se existir uma entrada diferente de mesmo nome, pare para comparar; atualização deliberada usa `-ReplaceExisting`, com backup/recibo, conforme seção 8.

O instalador cria o runtime isolado, a entrada `nexus9` no mapa `mcpServers` e a skill no destino informado. Não é necessário copiar manualmente o Python/hash do runtime. A instalação não modifica o código do robô.

## 4. Instale a skill e o runtime do QUANT9

Preview e instalação da skill, sem instalar para outras plataformas:

```powershell
python (Join-Path $Quant 'scripts\install.py') --project $Projeto --platform antigravity --dry-run
python (Join-Path $Quant 'scripts\install.py') --project $Projeto --platform antigravity
```

O destino é `$Projeto\.agents\skills\crypto-institutional`. O instalador é por projeto; ele não atualiza uma cópia global existente. `--replace` é usado somente para substituir deliberadamente uma cópia diferente, após revisão e com backup fora da descoberta.

Para uma primeira instalação do runtime, na pasta do QUANT9:

```powershell
Set-Location -LiteralPath $Quant
python -m venv .venv
$PythonQuant = Join-Path $Quant '.venv\Scripts\python.exe'
& $PythonQuant -m pip install '.[mcp]'
& $PythonQuant -m crypto_institutional mcp-config --platform antigravity
```

O último comando **só imprime JSON**. Ele não escreve config nem conecta o IDE. O NEXUS9 e QUANT9 usam ambientes Python separados; não instale um dentro do venv do outro. O download inicial das dependências requer internet; as auditorias usam dados locais sanitizados.

O host pode enviar os trechos/resultados recebidos ao provedor do modelo. Operação local do MCP não significa que toda a conversa permaneça offline.

### Registrar sem substituir a configuração inteira

Você pode copiar **somente a entrada `crypto-institutional`** do JSON gerado para dentro do mapa `mcpServers` já existente em `$Config`. Preserve a entrada `nexus9` e outros servidores. Não cole outro objeto raiz, não crie duas chaves `mcpServers` e não renomeie o módulo Python para `quant9`.

Como alternativa, no uso conjunto, o helper `configure.py` já incluído no NEXUS9 faz essa mesclagem, recusa JSON com chaves duplicadas e cria backup quando muda um arquivo existente:

```powershell
$GeradoQuant = & $PythonQuant -m crypto_institutional mcp-config --platform antigravity
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar a entrada MCP do QUANT9.' }
$DocumentoQuant = ($GeradoQuant -join "`n") | ConvertFrom-Json
$RegistroQuant = @{
    name = 'crypto-institutional'
    entry = $DocumentoQuant.mcpServers.'crypto-institutional'
    replace = $false
}
$ArquivoRegistro = Join-Path ([IO.Path]::GetTempPath()) ('quant9-registration-' + [Guid]::NewGuid().ToString() + '.json')
try {
    [IO.File]::WriteAllText($ArquivoRegistro, ($RegistroQuant | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    python (Join-Path $Nexus 'configure.py') --config $Config --registration $ArquivoRegistro
    if ($LASTEXITCODE -ne 0) { throw 'Mesclagem recusada; revise conflitos sem sobrescrever o config inteiro.' }
} finally {
    Remove-Item -LiteralPath $ArquivoRegistro -ErrorAction SilentlyContinue
}
```

Use apenas **uma** alternativa. Se houver conflito de mesmo nome, compare a entrada antes de permitir substituição; `replace = $true` é uma decisão de atualização, não o padrão de instalação nova. Backups de config podem conter credenciais de outros MCPs: mantenha-os privados e fora do Git/chat.

## 5. Recarregue e confirme uma conexão real

Abra `$Projeto` como workspace. Recarregue os MCPs no Antigravity e inicie um chat novo. Em **Customizations**, confirme as skills `nexus9` e `crypto-institutional`. As oito ferramentas esperadas são:

| NEXUS9 | QUANT9 |
| --- | --- |
| `nexus_catalog` | `crypto_catalog` |
| `nexus_query` | `crypto_plan` |
| `nexus_manage` | `crypto_context` |
| — | `crypto_schema` |
| — | `crypto_audit` |

Peça ao agente:

> Use as skills nexus9 e crypto-institutional. Descubra os schemas necessários. Consulte runtime_status e health pelo NEXUS9; confirme versão 0.4.0 e donos nexus9. Verifique que ele consegue acessar um arquivo conhecido deste workspace. Consulte crypto_catalog para confirmar versão 3.0.0 e nove cabeças, depois crypto_context com topic heads. Informe os resultados reais e qualquer falha; não presuma conexão por uma entrada cadastrada.

`health` informa integridade/política e vínculo ao projeto, mas não imprime o caminho literal da raiz. Confirme `--root` no config e faça uma consulta de um arquivo exclusivo do projeto. `runtime_status` identifica a instância que respondeu; isso não prova que o host carregou a skill ou que o modelo seguiu todas as instruções.

No QUANT9, valide o exemplo sintético local:

```powershell
Set-Location -LiteralPath $Quant
& $PythonQuant -m crypto_institutional audit .\examples\nine-heads-healthy.json
# Esperado: exit 0; nove cabeças checks_passed nos checks declarados.
& $PythonQuant -m crypto_institutional audit .\examples\nine-heads-broken.json
# Esperado: exit 1; achados detectados. Esse retorno é intencional.
```

Para testar o caminho MCP, peça `crypto_schema` e envie o conteúdo do exemplo saudável como string a `crypto_audit`; a ferramenta recebe JSON, não um caminho de arquivo. Para dados do robô, adapte/exporte observações reais conforme o contrato: não existe um adaptador automático para toda arquitetura. Um exemplo sintético aprovado não valida a estratégia ou prontidão de live.

## 6. Trabalhe com os dois em conjunto

Prompt de trabalho:

> Investigue [problema] preservando o modo atual. Use NEXUS9 para contexto por símbolos, impacto, memória e uma investigação com hipóteses, fontes e critérios quando o trabalho exigir. Use QUANT9 para selecionar as cabeças de trading pertinentes e auditar evidências exportadas. Implemente as correções comprovadas no escopo e teste. Relacione cada conclusão às fontes e verificações, mantendo explícitas as lacunas.

O agente investiga o código. O QUANT9 avalia somente as seções fornecidas; cabeças ausentes permanecem `not_evaluated`. O NEXUS9 revalida dependências declaradas **na consulta**, sem watcher. Receitas e `crypto_plan` são sugestões, não execução autônoma. Critérios que exigem testes observados dependem do runner opcional; ele fica desligado inicialmente e só deve executar perfis inspecionados em um ambiente confiável.

Gemini e Claude dentro do **mesmo Antigravity** usam a configuração desse host. `--platform claude` no instalador da skill se refere ao aplicativo **Claude Code**, não ao modelo Claude selecionado no Antigravity. Após trocar de modelo, solicite as skills e confirme chamadas pertinentes; não há um modo que garanta obediência automática.

## 7. Se você já instalou globalmente

Faça inventário no IDE antes de aplicar os comandos de instalação nova:

| Item | Global | Workspace |
| --- | --- | --- |
| MCP | `~/.gemini/config/mcp_config.json` (ou caminho legado mostrado pelo IDE) | `$Projeto/.agents/mcp_config.json` |
| Skills | `~/.gemini/config/skills/` (ou legado detectado) | `$Projeto/.agents/skills/` |

Escolha uma origem de cada servidor/skill de mesmo nome. Não há deduplicação universal garantida. Há dois caminhos:

- **Manter global:** use o config efetivamente aberto pelo IDE em `$Config`, mantenha `-SkillPath` do NEXUS9 apontando à cópia global e atualize apenas essas entradas. A raiz `--root` global é fixa: revise-a ao trocar de projeto. A skill QUANT9 global deve ser atualizada manualmente a partir de `skills/crypto-institutional`, com backup fora da descoberta; o seu instalador continua sendo por projeto. Não crie uma segunda cópia local sem decidir qual manter.
- **Migrar para workspace:** preserve backups privados das entradas/pastas gerenciadas; prepare as duas entradas locais e skills deste guia. Antes de recarregar, remova da configuração global somente as entradas que serão substituídas e arquive as skills globais correspondentes fora de qualquer pasta `skills`. Preserve outros servidores e o histórico. Depois recarregue e valide as chamadas da seção 5. Se outros projetos dependem da instalação global, prepare suas configurações antes de removê-la.

Renomear uma pasta antiga **dentro** de `skills` não é um backup seguro para descoberta: seu `SKILL.md` ainda pode ser encontrado. Use uma pasta de backups fora da árvore de skills. Não apague diretórios de estado/memória nem substitua o config inteiro. Uma migração de escopo/dono não transfere automaticamente memórias entre servidores ou namespaces de projetos.

## 8. Atualizações e reversão

Para NEXUS9, obtenha o pacote completo, confira o plano com os mesmos destinos e use `-ReplaceExisting` somente depois de comparar conflitos. Guarde o recibo; `rollback.ps1 -Receipt <caminho>` restaura os arquivos gerenciados quando compatíveis e preserva mudanças não relacionadas. Os arquivos são substituídos individualmente; não é uma transação única de filesystem.

Para QUANT9, atualize o código, reinstale o runtime com o Python do **mesmo venv** (`-m pip install '.[mcp]'` executado na pasta do QUANT9), atualize a skill por projeto com `--replace` ou a cópia global escolhida com backup e recarregue o MCP. O instalador guarda backups fora da descoberta; não há um comando universal de rollback de todo o runtime QUANT9.

Publicar no GitHub, editar a origem ou copiar somente um SKILL.md não atualiza runtime instalado nem o contexto antigo do chat. Confirme novamente versões, donos, raiz e chamadas. Em outra máquina, gere novamente os caminhos locais; não publique executáveis absolutos ou config com credenciais no repositório do robô.

## 9. Diagnóstico rápido

| Sintoma | Verifique / corrija |
| --- | --- |
| Ferramentas não aparecem | Config do host correto, Python existente, dependências no venv correspondente, entrada habilitada e reload. |
| Skill aparece, MCP não | Skill é instrução; instalar runtime e registrar a entrada MCP são etapas separadas. |
| MCP aparece, comportamento antigo | Cópia instalada da skill desatualizada, processo antigo ou chat antigo; atualize as cópias e confirme chamadas. |
| `operation disabled by runtime policy` | `health`/catálogo: dono externo pode bloquear investigação e memória. Revise concorrentes antes de transferir a função. |
| NEXUS9 lê outro projeto | Confira `--root`, não apenas a pasta aberta no editor. Não troque pela pasta do pacote. |
| Nomes duplicados / versões divergentes | Inventário global, workspace e plugins; mantenha uma origem escolhida, sem presumir precedência. |
| JSON de configuração recusado | Um único objeto raiz e um mapa `mcpServers`, sem chaves duplicadas; preserve entradas existentes. |
| `No module named crypto_institutional` | Entrada aponta para Python sem o pacote instalado ou caminho de venv movido; reinstale e gere a entrada com esse Python. |
| NEXUS9 informa `Release is incomplete or changed` | Use o ZIP completo íntegro; confira edições e conversão de fim de linha no checkout. Não remova a validação do manifesto. |
| Auditor rejeita entrada | Use `crypto_schema`; decimal é string, timestamps têm fuso e campos extras são recusados. Não envie logs brutos como bundle. |
| Exemplo defeituoso retorna 1 | Resultado esperado de detecção. `incomplete` retorna 3; entrada inválida, 2. |
| `check_run` recusado | Runner NEXUS9 desligado por padrão; não habilite para fazer um check passar sem inspecionar os testes. |
| Estado mudou, conclusão antiga ainda é citada | Consulte `investigation` novamente e registre nova evidência; salvar uma nota não revalida provas antigas. |

Não envie o conteúdo completo do config ao chat: ele pode conter tokens de outros serviços. Informe apenas nome do servidor, erro sanitizado, versão e caminhos não sensíveis necessários ao diagnóstico.

## Fontes e alcance

Instruções conferidas nos instaladores/CLI destes projetos e na documentação oficial em **30/10/2026**: [MCP no Antigravity](https://antigravity.google/docs/mcp) e [Agent Skills](https://antigravity.google/docs/skills). Nomes de menus e políticas podem variar por versão/superfície. Testes locais/protocolo não comprovam uma configuração de IDE ainda não observada. A confirmação é feita pelas chamadas reais e critérios da seção 5; não existe promessa de conexão ou obediência perfeita em todo ambiente.
