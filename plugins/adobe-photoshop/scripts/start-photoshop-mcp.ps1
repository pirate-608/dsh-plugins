[CmdletBinding()]
param([switch]$Check)

$ErrorActionPreference = 'Stop'

function Resolve-PhotoshopMcpLauncher {
    $candidates = [System.Collections.Generic.List[string]]::new()
    if (-not [string]::IsNullOrWhiteSpace($env:PHOTOSHOP_MCP_LAUNCHER)) {
        $candidates.Add($env:PHOTOSHOP_MCP_LAUNCHER)
    }

    $profileRoot = [Environment]::GetFolderPath('UserProfile')
    if (-not [string]::IsNullOrWhiteSpace($profileRoot)) {
        $candidates.Add((Join-Path $profileRoot '.local\bin\photoshop-mcp-server.exe'))
        $candidates.Add((Join-Path $profileRoot '.local\bin\photoshop-mcp-server.cmd'))
    }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $pathCommand = Get-Command 'photoshop-mcp-server' -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $pathCommand) { return $pathCommand.Source }
    return $null
}

$launcher = Resolve-PhotoshopMcpLauncher

if ($Check) {
    $registeredVersions = @()
    $registryRoot = 'HKLM:\SOFTWARE\Adobe\Photoshop'
    if (Test-Path $registryRoot) {
        $registeredVersions = @(Get-ChildItem $registryRoot -ErrorAction SilentlyContinue | ForEach-Object { $_.PSChildName })
    }
    [pscustomobject]@{
        ok = ($null -ne $launcher)
        launcher = $launcher
        psVersionOverride = $env:PS_VERSION
        registeredPhotoshopVersions = $registeredVersions
        note = 'PS_VERSION is intentionally unset by default so Photoshop 2026 can be auto-discovered from the registry.'
    } | ConvertTo-Json -Depth 4
    if ($null -eq $launcher) { exit 2 }
    exit 0
}

if ($null -eq $launcher) {
    [Console]::Error.WriteLine('photoshop-mcp-server was not found. Run scripts/install-photoshop-mcp.ps1, or set PHOTOSHOP_MCP_LAUNCHER to an absolute executable path.')
    exit 127
}

& $launcher
exit $LASTEXITCODE
