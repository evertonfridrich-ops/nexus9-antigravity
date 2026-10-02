# Instruções para GitHub Copilot

Você está trabalhando no motor do **NEXUS9**. Siga estas convenções de engenharia:

- **Estilo de Código:** Python 3.12+ idiomático, tipagem explícita com `typing` / built-in generics, docstrings curtas em português quando públicas.
- **Isolamento de Segurança:** Toda manipulação de caminhos no filesystem DEVE passar pelas validações de `src/nexus9/guard.py` (`resolve_safe_path`). Jamais confie em caminhos passados diretamente por clientes.
- **Zero Dependências Pesadas:** Não introduza dependências de PyTorch, TensorFlow, HuggingFace ou bibliotecas que exijam GPU/CUDA.
- **Sem Background Workers:** O NEXUS9 não deve criar threads persistentes em background ou daemons que consumam CPU ociosa.
- **Tratamento de Exceções:** Trate erros de forma descritiva e com fallback seguro, sem interromper o loop principal do servidor stdio.
