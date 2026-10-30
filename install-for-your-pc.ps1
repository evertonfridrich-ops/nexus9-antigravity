[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [string]$ConfigPath = "",
    [string]$SkillPath = "",
    [ValidateSet("Light", "Standard")][string]$HardwareProfile = "Light",
    [ValidateSet("Auto", "Nexus9", "External")][string]$MemoryOwner = "Auto",
    [ValidateSet("Auto", "Nexus9", "External")][string]$CompressionOwner = "Auto",
    [switch]$InstallRule,
    [switch]$PlanOnly,
    [switch]$ReplaceExisting
)

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

& (Join-Path $PSScriptRoot "install.ps1") -Workspace $Workspace `
    -ConfigPath $ConfigPath `
    -SkillPath $SkillPath `
    -HardwareProfile $HardwareProfile -MemoryOwner $MemoryOwner -CompressionOwner $CompressionOwner `
    -InstallRule:$InstallRule -PlanOnly:$PlanOnly -ReplaceExisting:$ReplaceExisting
