[CmdletBinding()]
param([string]$Package = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = "Stop"
$testBase = Join-Path ([IO.Path]::GetTempPath()) ("nexus9 acceptance " + [Guid]::NewGuid().ToString())
$projectPath = Join-Path $testBase "project with spaces"
$configPath = Join-Path $testBase "profile\mcp_config.json"
$skillPath = Join-Path $testBase "skills\nexus9"
$runtimeBase = Join-Path $testBase "runtime"
New-Item -ItemType Directory -Force -Path $projectPath | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $configPath) | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$original = '{"mcpServers":{"hydra-tools-mcp":{"command":"preserve-hydra"},"agentMemory":{"command":"preserve-memory"}},"other":true}'
[IO.File]::WriteAllText($configPath, $original, $utf8)
try {
    & (Join-Path $Package "install.ps1") -Workspace $projectPath -ConfigPath $configPath -SkillPath $skillPath -RuntimeBase $runtimeBase -PlanOnly
    if (Test-Path -LiteralPath $runtimeBase) { throw "PlanOnly changed runtime." }
    if ([IO.File]::ReadAllText($configPath) -ne $original) { throw "PlanOnly changed config." }
    & (Join-Path $Package "install.ps1") -Workspace $projectPath -ConfigPath $configPath -SkillPath $skillPath -RuntimeBase $runtimeBase
    $data = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath (Join-Path $skillPath "SKILL.md"))) { throw "Native Skill missing." }
    if ($data.mcpServers.'hydra-tools-mcp'.command -ne "preserve-hydra" -or $data.mcpServers.agentMemory.command -ne "preserve-memory") { throw "Other servers changed." }
    if ($data.mcpServers.nexus9.args -notcontains "external" -or $data.mcpServers.nexus9.args -notcontains "light") { throw "Auto ownership or light policy missing." }
    $receipt = Get-ChildItem -LiteralPath (Join-Path $runtimeBase "installations") -Filter receipt.json -Recurse | Select-Object -First 1
    & (Join-Path $Package "rollback.ps1") -Receipt $receipt.FullName
    if ([IO.File]::ReadAllText($configPath) -ne $original) { throw "Rollback did not restore exact original config." }
    if (Test-Path -LiteralPath (Join-Path $skillPath "SKILL.md")) { throw "Rollback retained newly installed Skill." }
    Write-Host "Windows acceptance passed: plan, spaces, install, coexistence, MCP smoke and rollback."
} finally { Remove-Item -LiteralPath $testBase -Recurse -Force -ErrorAction SilentlyContinue }
