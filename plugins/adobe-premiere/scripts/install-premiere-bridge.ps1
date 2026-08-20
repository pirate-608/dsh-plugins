[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $TempDir = (Join-Path $env:TEMP 'premiere-mcp-bridge'),
    [switch] $SkipAdobeDebugMode
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') {
    throw 'This installer supports Windows only.'
}

$pluginRoot = Split-Path -Parent $PSScriptRoot
$cepSource = Join-Path $pluginRoot 'vendor\premiere-pro-mcp\cep-plugin'
$cepParent = Join-Path $env:APPDATA 'Adobe\CEP\extensions'
$cepTarget = Join-Path $cepParent 'MCPBridgeCEP'

if (-not (Test-Path -LiteralPath $cepSource -PathType Container)) {
    throw "Bundled CEP extension not found: $cepSource"
}

New-Item -ItemType Directory -Path $cepParent -Force | Out-Null

if (Test-Path -LiteralPath $cepTarget) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = "$cepTarget.backup-$stamp"
    if ($PSCmdlet.ShouldProcess($cepTarget, "Move existing extension to $backup")) {
        Move-Item -LiteralPath $cepTarget -Destination $backup
        Write-Host "Previous CEP extension backed up to: $backup"
    }
}

if ($PSCmdlet.ShouldProcess($cepTarget, 'Install bundled MCP Bridge (CEP) extension')) {
    Copy-Item -LiteralPath $cepSource -Destination $cepTarget -Recurse
}

if (-not $SkipAdobeDebugMode) {
    foreach ($version in 9..15) {
        $key = "HKCU:\Software\Adobe\CSXS.$version"
        if ($PSCmdlet.ShouldProcess($key, 'Enable CEP PlayerDebugMode')) {
            New-Item -Path $key -Force | Out-Null
            New-ItemProperty `
                -Path $key `
                -Name 'PlayerDebugMode' `
                -Value '1' `
                -PropertyType String `
                -Force | Out-Null
        }
    }
}

if ($PSCmdlet.ShouldProcess($TempDir, 'Create Premiere MCP bridge directory')) {
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
}

Write-Host ''
Write-Host 'Premiere MCP bridge installed.'
Write-Host "CEP extension: $cepTarget"
Write-Host "Temp directory: $TempDir"
Write-Host 'Restart Premiere Pro, then open Window > Extensions > MCP Bridge (CEP).'
Write-Host 'Click Save Configuration, Start Bridge, and Test Connection.'
