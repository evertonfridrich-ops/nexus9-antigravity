[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [string]$ConfigPath = "",
    [string]$SkillPath = ""
)
$ErrorActionPreference = "Stop"

if (-not $ConfigPath) {
    $candidates = @(
        (Join-Path $env:USERPROFILE ".gemini\antigravity\mcp_config.json"),
        (Join-Path $env:USERPROFILE ".gemini\config\mcp_config.json")
    ) | Where-Object { Test-Path -LiteralPath $_ }
    if (@($candidates).Count -ge 1) { $ConfigPath = @($candidates)[0] }
    else { $ConfigPath = Join-Path $env:USERPROFILE ".gemini\config\mcp_config.json" }
}

if (-not $SkillPath) {
    $SkillPath = Join-Path $env:USERPROFILE ".gemini\config\skills\nexus9"
}

$projectPath = (Resolve-Path -LiteralPath $Workspace).Path
& python (Join-Path $PSScriptRoot "integration.py") doctor --config $ConfigPath --home $env:USERPROFILE --workspace $projectPath --skill-dir $SkillPath
if ($LASTEXITCODE -ne 0) { throw "Read-only integration audit failed." }
