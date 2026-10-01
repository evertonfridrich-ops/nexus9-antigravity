[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Receipt)
$ErrorActionPreference = "Stop"
& python (Join-Path $PSScriptRoot "integration.py") rollback --receipt $Receipt
if ($LASTEXITCODE -ne 0) { throw "Rollback refused or incomplete. Review changed files and receipt; no live runtime is deleted." }
