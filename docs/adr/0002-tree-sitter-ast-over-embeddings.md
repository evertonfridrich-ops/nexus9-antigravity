# 0002. Adoção de Tree-sitter AST e BM25 em Substituição a Embeddings Neurais

* **Status:** Aceito
* **Data:** 2026-10-01
* **Decisores:** Everton Fridrich
* **Componente Afetado:** Cabeça 3 (Context Compiler) e `src/nexus9/index.py`

## Contexto e Declaração do Problema
O objetivo do NEXUS9 é fornecer máxima economia de tokens com zero consumo de recursos externos. Ambientes de desenvolvedor comuns utilizam hardware modesto (ex: Intel Kaby Lake 2 núcleos / 4 threads, 16 GB RAM, GPU integrada sem suporte a CUDA).

A abordagem tradicional de RAG baseada em modelos neurais de embedding (ex: SentenceTransformers, BGE, OpenAI Embeddings) impõe:
1. Consumo contínuo de 2 GB a 4 GB de RAM em workers de background.
2. Degradação perceptível da responsividade da interface (IDE latency).
3. Dependência de rede externa ou compilação de binários Torch/CUDA locais.

## Opções Consideradas
1. **Embeddings Locais com ONNX / MiniLM:** Leve, mas exige inferência vetorial contínua e não garante precisão sintática de limites de funções.
2. **Parsing Léxico por Regex:** Extremamente rápido, porém propenso a erros em declarações TypeScript aninhadas e imports multilinhas.
3. **Gramáticas Tree-sitter com Parser Incremental e Ranking Léxico:** Compilação de código nativa C via bindings Python, zero daemon em background e recuperação exata da árvore sintática.

## Decisão Tomada
Adotar gramáticas nativas **Tree-sitter** (`tree-sitter==0.25.2`) para Python, JavaScript e TypeScript em conjunto com um classificador léxico determinístico baseado em BM25.

### Consequências Positivas
* **Zero Overhead de GPU:** A indexação é executada cooperativamente em chunks curtos (< 2.0s por rodada).
* **Precisão Sintática Exata:** A recuperação de código retorna corpos completos de funções e interfaces declaradas, sem truncamentos arbitrários por número de caracteres.
* **Compatibilidade Total:** Executa de forma fluida em sistemas 2C/4T com footprint inferior a 80 MB de memória em runtime.

### Trade-offs Aceitos
* Resolução de aliases complexos de TypeScript (`tsconfig paths`) e chamadas indiretas dinâmicas exigem declaração explícita de caminhos adicionais pelo usuário ou pela Skill.
