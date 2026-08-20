param(
    [Parameter(Position = 0)]
    [ValidateSet("login", "status", "logout")]
    [string]$Command = "status"
)

$ErrorActionPreference = "Stop"
$PluginRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv was not found on PATH. Install uv, then retry."
    exit 2
}

& uv run --project (Join-Path $PluginRoot "runtime") --frozen python (Join-Path $PSScriptRoot "auth_entry.py") $Command
exit $LASTEXITCODE
