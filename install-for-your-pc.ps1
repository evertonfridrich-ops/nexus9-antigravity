[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [ValidateSet("Auto", "Nexus9", "External")][string]$MemoryOwner = "Auto",
    [ValidateSet("Auto", "Nexus9", "External")][string]$CompressionOwner = "Auto",
    [switch]$PlanOnly,
    [switch]$ReplaceExisting
)
& (Join-Path $PSScriptRoot "install.ps1") -Workspace $Workspace `
    -ConfigPath 'C:\Users\QG DUS GURI\.gemini\antigravity\mcp_config.json' `
    -SkillPath 'C:\Users\QG DUS GURI\.gemini\config\skills\nexus9' `
    -HardwareProfile Light -MemoryOwner $MemoryOwner -CompressionOwner $CompressionOwner `
    -PlanOnly:$PlanOnly -ReplaceExisting:$ReplaceExisting
