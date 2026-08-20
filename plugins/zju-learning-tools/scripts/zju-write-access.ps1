param(
    [Parameter(Position = 0)]
    [ValidateSet("enable", "status", "disable")]
    [string]$Command = "status",

    [Parameter()]
    [string[]]$Root = @()
)

$ErrorActionPreference = "Stop"
$PluginRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv was not found on PATH. Install uv, then retry."
    exit 2
}

$Arguments = @($Command)
foreach ($ApprovedRoot in $Root) {
    $Arguments += "--root"
    $Arguments += $ApprovedRoot
}

& uv run --project (Join-Path $PluginRoot "runtime") --frozen python (Join-Path $PSScriptRoot "write_access_entry.py") @Arguments
exit $LASTEXITCODE
