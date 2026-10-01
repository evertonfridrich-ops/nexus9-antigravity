# Escopo de segurança e critérios de operação

NEXUS9 é um processo local stdio, do usuário do IDE, destinado a projetos
confiáveis com entradas de ferramentas não confiáveis. Não é um serviço
multiusuário ou uma sandbox de sistema operacional.

O servidor valida raiz/caminhos/links, limita dados, redige padrões conhecidos,
usa SQL parametrizado e trata resultados como dados. Não executa código de
projeto, não acessa credenciais do Google e não oferece exclusão de arquivos.

Persistência inclui snapshots e respostas redigidas, que ainda podem conter
dados sensíveis não reconhecidos por regex. Use ACLs do usuário e criptografia
de disco. Não há RBAC, SSO, criptografia própria, DLP completo ou retenção física
garantida. Informações de origem da memória/usage são declarações do chamador.

Não protege contra administrador, processo malicioso com o mesmo usuário,
troca concorrente de componentes de caminho (TOCTOU), manipulação prévia do
diretório de estado ou todas as formas de prompt injection. `O_NOFOLLOW` protege
o componente final no POSIX; Windows não usa handles ancorados em diretório.
Um projeto adversarial deve ser aberto em VM/container/sandbox apropriada.

Os limites de tempo são cooperativos. Parsers nativos são dependências fixadas,
não executáveis do projeto, mas falhas nativas podem encerrar o processo. Nos
testes desta implementação, Tree-sitter 0.26.0 falhou num corpus sintético amplo;
0.25.2 passou no mesmo caso e foi fixado no release. O teste de regressão permanece.
Não há afirmação de que essa falha ocorre em todas as instalações de 0.26.0.

Dependências e artefatos têm hashes; actions CI têm commits fixados. Isso verifica
integridade contra as versões escolhidas, não ausência de CVEs. Análise contínua
de vulnerabilidades, assinatura de releases, SBOM padronizado e revisão externa
devem fazer parte do processo empresarial de adoção.

Antes de produção institucional:

1. Executar instalação, rollback e matriz CI no Windows real.
2. Testar conexão/permissões/regra na versão do Antigravity em uso.
3. Fazer revisão de segurança independente e processo de atualização de dependências.
4. Definir retenção, ACLs, proteção de disco, incidentes e responsabilidade operacional.
5. Medir tarefas reais com/sem ferramenta, com consumo do provedor e testes de qualidade.
6. Validar desempenho/tamanho do projeto; índice limitado exige recuperação adicional.

Esses itens são critérios de adoção, não certificações já obtidas por este release.

## Integração e coexistência na versão 0.3.0

A Skill nativa orienta o modelo; o servidor MCP executa as operações. A política
de dono bloqueia memória/redução NEXUS9 quando atribuídas a outro servidor,
incluindo referências de memória em contexto/handoff. Isso não controla hooks
internos do IDE ou ações de outro MCP. O diagnóstico é limitado e classifica
menções em regras como candidatas, sem afirmar que estão ativas.

O instalador pré-valida conflitos, verifica o manifesto, faz smoke MCP e cria
backups/recibo antes da integração. A reversão verifica hashes e preserva configs
externas editadas depois; não garante transação atômica entre arquivos nem impede
um editor concorrente. Backups incluem o config original, inclusive credentials
nele existentes. Protegê-los como o próprio config; não compartilhá-los em logs.

Light limita esforço por rodada e inventário em memória, sem embeddings nem
workers periódicos. Limitação/TTL são expostos. Não fornece cgroup, hard deadline,
isolamento por tenant ou garantia de impacto quase nulo na máquina do usuário.
