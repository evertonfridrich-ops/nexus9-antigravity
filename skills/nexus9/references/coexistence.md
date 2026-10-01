# Dono de cada função

Consultar `runtime_policy` no catálogo. As demais funções continuam disponíveis.

| Política | Efeito obrigatório |
| --- | --- |
| memory_owner=external | Não usar memory_save, memory, resume nem memory=... em context/handoff. |
| compression_owner=external | Não usar compress nem logs do NEXUS9. |
| dono nexus9 | Usar NEXUS9 como único executor dessa função para a tarefa. |

Em Auto, o instalador escolhe dono externo quando detecta HYDRA/agentMemory ou
candidatos de regras HYDRA. O diagnóstico lê nomes/configuração e arquivos
conhecidos sob limites; não garante descobrir todos os hooks ativos do IDE.
`configured_enabled` não prova conexão ativa.

Para transferir funções ao NEXUS9, orientar a revisar arquivos reportados por
`doctor.ps1`, pausar somente hooks/regras de memória ou compressão concorrentes
e reinstalar com dono Nexus9 explícito. Preservar funções complementares e dados
do agentMemory. Não editar configurações globais nem pausar servidores por
iniciativa da Skill.

Se regra global exigir duplicação, informar conflito e aplicar preferência
explícita do usuário. Sem preferência, usar funções não conflitantes até resolver.
Não driblar o bloqueio de política.
