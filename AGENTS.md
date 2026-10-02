# Diretrizes para Agentes de IA (Claude, Gemini, Copilot, Cursor)

Este repositório possui regras estritas de economia de contexto para agentes de IA:

## 1. Princípios Operacionais Fundamentais
1. **Descoberta Progressiva:** Não tente adivinhar schemas de operações. Chame `nexus_catalog` para obter a definição precisa antes de executar consultas.
2. **Priorize Símbolos a Arquivos Inteiros:** Ao analisar o código, recupere apenas as funções e classes necessárias usando a operação `context` ou `snippet`.
3. **Diff-Only:** Ao editar o código-fonte, use substituição cirúrgica em blocos contíguos (`replace_file_content`). Nunca reescreva arquivos íntegros para alterar poucas linhas.
4. **Verificação de Impacto:** Sempre execute a operação `impact` antes de alterar interfaces públicas ou funções amplamente importadas.

## 2. Comandos de Validação Local
- Para rodar testes de integridade: `python -m unittest discover -s tests -v`
- Para validar a suite de smoke: `python integration.py verify`
- Para checar conformidade estática: `python -m pip check`
