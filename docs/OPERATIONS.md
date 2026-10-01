# Operação e recuperação — NEXUS9 0.3.0

## Instalação e mudança de versão

Use o pacote completo e a raiz explícita do projeto. Execute `-PlanOnly` para
revisar destinos e donos; use instalação normal para aplicar. O runtime é
isolado e identificado pela versão/hash do manifesto. Uma versão nova não
sobrescreve outra em uso; uma versão íntegra pode ser reutilizada por mais de
um projeto com nomes MCP diferentes. Config e Skill são pré-validados antes do
runtime ser instalado. `-ReplaceExisting` autoriza somente conflitos conhecidos
da entrada NEXUS9 e dos arquivos de Skill/regra gerenciados.

A dependência inicial exige internet/PyPI e wheels compatíveis. O instalador
recusa builds locais de dependências. Operações do servidor não abrem rede.
O manifesto verifica integridade contra os arquivos do pacote, não fornece
assinatura independente do publicador. O installer não tem auto-update.

Após instalar, atualizar MCPs no IDE e verificar catálogo/health/Skill. Registrar
qual versão, projeto e política de dono foram adotados. Em mudança de dono,
inspecionar e pausar os hooks/regras concorrentes antes de ativar a capacidade
NEXUS9. O diagnóstico não prova o estado interno do host.

## Saúde e evidência

`nexus_query` com `operation=health` informa integridade SQLite e política local.
`metrics` informa volume/duração e usage declarado. Falhas de sintaxe em `verify`
são evidência local de gramática; validação funcional exige checks do projeto.
Não publicar um percentual de economia sem comparar tarefas pareadas, uso real
do provedor e resultados aceitos. O teste de smoke usa projeto temporário e não
valida o conteúdo do projeto do usuário.

## Recibos e rollback

Recibos ficam em `%LOCALAPPDATA%\NEXUS9\installations\<instalacao>\receipt.json`.
Arquivos `.backup` preservam bytes anteriores, incluindo secrets presentes no
config original; proteger essa pasta com permissões do usuário/proteção de disco.
O diagnóstico não exibe esses secrets e os recibos não são enviados a um serviço.
A cópia de config é necessária para reversão íntegra, não é sanitizada.

Executar `rollback.ps1 -Receipt ...`, depois atualizar o IDE. Quando o config
foi editado em outras partes, a reversão repõe apenas a entrada NEXUS9 e preserva
as demais mudanças. Se a entrada NEXUS9/Skill/regra gerenciada tiver sido editada,
a reversão recusa a operação antes de começar. Revisar as diferenças localmente
antes de decidir qual versão manter. Não restaurar o config inteiro por cima de
edições posteriores.

Os arquivos são substituídos atomicamente um a um e o recibo é gravado antes das
mudanças. Vários arquivos não são uma transação de filesystem. Se o processo
for interrompido, localizar recibo com status `applying`/`recovery_required` e
usar rollback. Em falha tratada, o installer tenta restaurar arquivos aplicados;
se detectar edição concorrente, preserva-a e registra `recovery_paths`. Não há
lock interprocesso para editores do IDE; fechar o editor do config durante a mudança.

Um runtime incompleto é preservado e a instalação recusa sobrescrevê-lo. Se
nenhum servidor o utiliza, revisar o caminho exato e removê-lo antes de repetir.
Rollback não apaga runtime, memórias ou caches; retenção desses dados é separada.
Recibos são arquivos locais confiáveis: não executar rollback de recibo recebido
de terceiros sem revisão.

## Hardware Kaby Lake 2C/4T

Começar com Light. Sem embeddings, pipeline ML, workers em background ou
varreduras automáticas periódicas. Cada chamada executa trabalho sob limites;
deadlines são cooperativos e não interrompem um parser nativo no meio da análise.
Arquivos selecionados são revalidados mesmo dentro do TTL de descoberta.

`index_cached` e `index_age_seconds` indicam descoberta potencialmente defasada.
`index_limited` indica cobertura parcial. Usar paths explícitos, ampliar somente
a evidência necessária e consultar índice em lotes quando novo inventário for
realmente necessário. Imports TypeScript por alias/bundler não são resolvidos.
Mantenha `.nexusignore` com dependências, logs e dados desnecessários; reinicie
servidor após alterar exclusões.

Para medir, use o Python do runtime e seu PYTHONPATH conforme config:
`python scripts/benchmark.py --files 80 --repeats 6`. O benchmark cria corpus
sintético temporário, mede CPU/tempo e verifica fonte/dependência. Não representa
o Kaby Lake até ser executado nele, nem mede uso do modelo. Compare também o
projeto real e a responsividade do IDE. Light é uma política de esforço reduzido,
não uma garantia de consumo quase nulo ou deadline rígido.

## Validação Windows reproduzível

A CI incluída cobre Windows/Linux e Python 3.12/3.13. Em Windows, executa parser
PowerShell e `scripts/windows_install_acceptance.ps1`: usa diretórios temporários
com espaços, config isolado, runtime isolado, Skill isolada, instalação, política
Auto, handshake MCP e rollback. Nunca usa o config pessoal do usuário.
Esse teste é fornecido e não foi executado neste runner Linux.
