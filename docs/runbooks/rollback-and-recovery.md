# Runbook Operacional: Rollback e Recuperação de Emergência

## Objetivo
Instruções para restaurar o ambiente do desenvolvedor caso ocorra falha na instalação, concorrência de escrita no `mcp_config.json` ou corrupção do banco SQLite local.

## 1. Recuperação Automática de Instalação (Rollback)

Quando o instalador falha ou é interrompido:
1. Localize o recibo de instalação gerado em:
   ```
   %LOCALAPPDATA%\NEXUS9\installations\
   ```
2. Identifique o recibo com status `applying` ou `recovery_required` (ex: `receipt.json`).
3. Execute o script de reversão transacional:
   ```powershell
   .\rollback.ps1 -Receipt "$env:LOCALAPPDATA\NEXUS9\installations\<id>\receipt.json"
   ```
4. O script valida as somas de verificação SHA-256 e restaura a configuração MCP e as Skills para o estado anterior.

## 2. Recuperação de Integridade do Banco de Estado SQLite

Se a operação `health` retornar erro de integridade ou bloqueio:
1. Feche instâncias ativas do Antigravity/IDE que utilizem o servidor stdio.
2. Navegue até o diretório de estado:
   ```powershell
   cd "$env:LOCALAPPDATA\Nexus9\<project-hash>"
   ```
3. Verifique o banco:
   ```powershell
   sqlite3 state.sqlite3 "PRAGMA integrity_check;"
   ```
4. Se corrompido, remova o arquivo temporário `state.sqlite3`. O NEXUS9 recriará as tabelas e schemas automaticamente na próxima inicialização sem perda de código-fonte.
