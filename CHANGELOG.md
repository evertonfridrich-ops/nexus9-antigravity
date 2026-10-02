# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [0.3.0] - 2026-10-02

### Adicionado
- Logotipo oficial vetorial e assets dinâmicos para documentação institucional.
- Contrato legal sob licença AGPL-3.0 com suporte a Dual Licensing corporativo.
- Contributor License Agreement (CLA) e política formal de proteção de marcas.
- Suite de testes de integração cobrindo 87 cenários com 85 aprovações imediatas.

### Corrigido
- Compatibilidade com sistemas de arquivos Windows que retornam `st_nlink=0` no `os.scandir()`.
- Prevenção de deadlocks e checagens estritas de NTFS Alternate Data Streams (ADS).

## [0.2.0] - 2026-09-15
### Adicionado
- Implementação dos módulos Guard Rails com sanitização de caminhos e redação de credenciais.
- Suporte a transações SQLite3 no gerenciamento de sessões, deltas e orçamentos de bytes.

## [0.1.0] - 2026-08-20
### Adicionado
- Versão inicial do motor NEXUS9 com as 9 cabeças funcionais.
- Descoberta progressiva via protocolo MCP (`nexus_catalog`, `nexus_query`, `nexus_manage`).
- Parsers Tree-sitter para Python, JavaScript e TypeScript.
