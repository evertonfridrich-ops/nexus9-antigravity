[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [string]$ConfigPath = 'C:\Users\QG DUS GURI\.gemini\antigravity\mcp_config.json',
    [string]$SkillPath = 'C:\Users\QG DUS GURI\.gemini\config\skills\nexus9'
)
$ErrorActionPreference = "Stop"
$projectPath = (Resolve-Path -LiteralPath $Workspace).Path
& python (Join-Path $PSScriptRoot "integration.py") doctor --config $ConfigPath --home $env:USERPROFILE --workspace $projectPath --skill-dir $SkillPath
if ($LASTEXITCODE -ne 0) { throw "Read-only integration audit failed." }
