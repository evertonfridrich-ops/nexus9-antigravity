[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [string]$ConfigPath = "",
    [string]$SkillPath = "",
    [string]$ServerName = "nexus9",
    [string]$RuntimeBase = "",
    [ValidateSet("Light", "Standard")][string]$HardwareProfile = "Light",
    [ValidateSet("Auto", "Nexus9", "External")][string]$MemoryOwner = "Auto",
    [ValidateSet("Auto", "Nexus9", "External")][string]$CompressionOwner = "Auto",
    [switch]$InstallRule,
    [switch]$ReplaceExisting,
    [switch]$PlanOnly
)
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "This installer targets Windows. See README for the portable Python server." }
if ($ServerName -notmatch '^[a-zA-Z0-9_-]{1,64}$') { throw "Invalid ServerName." }
$projectPath = (Resolve-Path -LiteralPath $Workspace).Path
if (-not (Test-Path -LiteralPath $projectPath -PathType Container)) { throw "Workspace must be a directory." }
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) { throw "Install Python 3.12 or 3.13 with PATH enabled." }
$pythonExe = $pythonCommand.Source
& $pythonExe -c "import sys; assert sys.version_info[:2] in ((3,12),(3,13)) and sys.maxsize > 2**32, 'Python 3.12 or 3.13, 64 bit required'"
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 or 3.13 required; check python --version." }
if (-not $ConfigPath) {
    $candidates = @(
        (Join-Path $env:USERPROFILE ".gemini\antigravity\mcp_config.json"),
        (Join-Path $env:USERPROFILE ".gemini\config\mcp_config.json")
    ) | Where-Object { Test-Path -LiteralPath $_ }
    if (@($candidates).Count -gt 1) { throw "Multiple MCP configs found. Pass -ConfigPath from Antigravity View raw config." }
    if (@($candidates).Count -eq 1) { $ConfigPath = @($candidates)[0] }
    else { $ConfigPath = Join-Path $env:USERPROFILE ".gemini\config\mcp_config.json" }
}
$ConfigPath = [IO.Path]::GetFullPath($ConfigPath)
if (-not $SkillPath) { $SkillPath = Join-Path $env:USERPROFILE ".gemini\config\skills\nexus9" }
$SkillPath = [IO.Path]::GetFullPath($SkillPath)
$integration = Join-Path $PSScriptRoot "integration.py"
$integrityText = & $pythonExe $integration verify --package $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw "Release is incomplete or changed. Download and extract the full ZIP again." }
$integrity = $integrityText | ConvertFrom-Json
$auditText = & $pythonExe $integration doctor --config $ConfigPath --home $env:USERPROFILE --workspace $projectPath --skill-dir $SkillPath
if ($LASTEXITCODE -ne 0) { throw "Environment audit failed before installation." }
$audit = $auditText | ConvertFrom-Json
$selectedMemory = $MemoryOwner.ToLowerInvariant()
$selectedCompression = $CompressionOwner.ToLowerInvariant()
if ($MemoryOwner -eq "Auto") { $selectedMemory = $audit.recommended_memory_owner }
if ($CompressionOwner -eq "Auto") { $selectedCompression = $audit.recommended_compression_owner }
if (($selectedMemory -eq "nexus9" -and $audit.recommended_memory_owner -eq "external") -or
    ($selectedCompression -eq "nexus9" -and $audit.recommended_compression_owner -eq "external")) {
    Write-Warning "NEXUS ownership was explicitly selected while overlapping candidates exist. Review doctor.ps1 and pause only competing hooks/rules before using that capability."
}
if ($audit.scan_limited) { Write-Warning "Rule/hook audit was limited. Inspect Customizations and active hooks in Antigravity." }
$runtimeTag = $integrity.manifest_sha256.Substring(0, 12)
if (-not $RuntimeBase) { $RuntimeBase = Join-Path $env:LOCALAPPDATA "NEXUS9" }
$RuntimeBase = [IO.Path]::GetFullPath($RuntimeBase)
$installDir = Join-Path $RuntimeBase ("runtime-0.3.0-" + $runtimeTag)
$venvPython = Join-Path $installDir ".venv\Scripts\python.exe"
$entry = @{
    command = $venvPython
    args = @("-m", "nexus9.server", "--root", $projectPath, "--hardware", $HardwareProfile.ToLowerInvariant(),
             "--memory-owner", $selectedMemory, "--compression-owner", $selectedCompression)
    env = @{ PYTHONPATH = (Join-Path $installDir "src"); PYTHONUTF8 = "1"; PYTHONDONTWRITEBYTECODE = "1" }
}
$registration = @{ name=$ServerName; entry=$entry; replace=[bool]$ReplaceExisting;
    workspace=$projectPath; skill_dir=$SkillPath; install_rule=[bool]$InstallRule }
$registrationFile = Join-Path ([IO.Path]::GetTempPath()) ("nexus9-registration-" + [Guid]::NewGuid().ToString() + ".json")
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($registrationFile, ($registration | ConvertTo-Json -Depth 20), $utf8)
try {
    & $pythonExe $integration preflight --package $PSScriptRoot --config $ConfigPath --registration $registrationFile
    if ($LASTEXITCODE -ne 0) { throw "Preflight failed. Existing config and Skill were preserved." }
    Write-Host "Hardware: $HardwareProfile; memory owner: $selectedMemory; compression owner: $selectedCompression"
    Write-Host "Config: $ConfigPath"
    Write-Host "Skill: $SkillPath"
    if ($PlanOnly) { Write-Host "Plan only: no runtime, config, Skill or hooks were changed."; return }
    $marker = Join-Path $installDir "runtime.marker.json"
    if (Test-Path -LiteralPath $installDir) {
        if (-not (Test-Path -LiteralPath $marker) -or -not (Test-Path -LiteralPath $venvPython)) {
            throw "Incomplete runtime exists: $installDir. Keep receipts and review it; the installer will not overwrite a potentially running server."
        }
        $stored = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
        if ($stored.manifest_sha256 -ne $integrity.manifest_sha256) { throw "Runtime marker mismatch." }
        & $pythonExe (Join-Path $PSScriptRoot "scripts\verify_runtime.py") --package $PSScriptRoot --runtime $installDir
        if ($LASTEXITCODE -ne 0) { throw "Runtime source integrity failed. Existing runtime was preserved." }
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $installDir) | Out-Null
        New-Item -ItemType Directory -Path $installDir | Out-Null
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "src") -Destination $installDir -Recurse
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "requirements.lock.txt") -Destination $installDir
        & $pythonExe -m venv (Join-Path $installDir ".venv")
        if ($LASTEXITCODE -ne 0) { throw "Isolated Python environment creation failed. Config and Skill were preserved." }
        & $venvPython -m pip install --only-binary=:all: --require-hashes -r (Join-Path $installDir "requirements.lock.txt")
        if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Config and Skill were preserved." }
        [IO.File]::WriteAllText($marker, ($integrity | ConvertTo-Json), $utf8)
    }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Runtime dependency check failed before registration." }
    & $venvPython (Join-Path $PSScriptRoot "scripts\smoke.py") --server-python $venvPython --src (Join-Path $installDir "src")
    if ($LASTEXITCODE -ne 0) { throw "MCP handshake or policy smoke test failed. Config and Skill were preserved." }
    $receipts = Join-Path $RuntimeBase "installations"
    $resultText = & $pythonExe $integration install --package $PSScriptRoot --config $ConfigPath --registration $registrationFile --receipt-dir $receipts
    if ($LASTEXITCODE -ne 0) { throw "Integration failed. Review recovery receipts at $receipts before retrying." }
    $result = $resultText | ConvertFrom-Json
    Write-Host "NEXUS9 integration: $($result.status). Receipt: $($result.receipt)"
    Write-Host "Refresh MCP servers and inspect Skill nexus9 in Antigravity Customizations."
    Write-Host "No HYDRA/agentMemory server or hook was modified."
} finally { Remove-Item -LiteralPath $registrationFile -ErrorAction SilentlyContinue }
