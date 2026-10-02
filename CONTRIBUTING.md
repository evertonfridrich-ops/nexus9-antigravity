# Guia de Contribuição — NEXUS9

Obrigado pelo interesse em contribuir com o **NEXUS9**. Este projeto segue diretrizes de engenharia de software institucional.

## 1. Termo de Contribuição (CLA)
Todas as contribuições de código, testes ou documentação submetidas ao projeto exigem a concordância integral com o nosso [Contributor License Agreement (CLA)](CLA.md). Ao abrir um Pull Request, você confirma estar de acordo com os termos estabelecidos.

## 2. Configuração do Ambiente de Desenvolvimento
1. Clone o repositório:
   ```bash
   git clone https://github.com/evertonfridrich-ops/nexus9-antigravity.git
   cd nexus9-antigravity
   ```
2. Crie e ative um ambiente virtual com Python 3.12+:
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # Linux:
   source .venv/bin/activate
   ```
3. Instale as dependências validadas por hash:
   ```bash
   python -m pip install --require-hashes -r requirements.lock.txt
   ```

## 3. Padrão de Commits
Utilizamos o padrão **Conventional Commits**:
* `feat(escopo): nova funcionalidade`
* `fix(escopo): correção de bug`
* `docs(escopo): melhorias em documentação`
* `test(escopo): adição ou ajuste de testes`
* `perf(escopo): otimizações de performance`

## 4. Validação Obrigatória
Antes de submeter o PR, garanta que todos os testes passem:
```bash
python -m unittest discover -s tests -v
python integration.py verify
```
