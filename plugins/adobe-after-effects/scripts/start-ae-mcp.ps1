[CmdletBinding()]
param([switch]$Check)

$ErrorActionPreference = 'Stop'

function Resolve-AeMcpLauncher {
    $candidatePaths = [System.Collections.Generic.List[string]]::new()
    if (-not [string]::IsNullOrWhiteSpace($env:AE_MCP_LAUNCHER)) {
        $candidatePaths.Add($env:AE_MCP_LAUNCHER)
    }

    $profileRoot = [Environment]::GetFolderPath('UserProfile')
    if (-not [string]::IsNullOrWhiteSpace($profileRoot)) {
        $candidatePaths.Add((Join-Path $profileRoot '.ae-mcp\bin\ae-mcp.exe'))
        $candidatePaths.Add((Join-Path $profileRoot '.ae-mcp\bin\ae-mcp.cmd'))
        $candidatePaths.Add((Join-Path $profileRoot '.ae-mcp\bin\ae-mcp'))
        $candidatePaths.Add((Join-Path $profileRoot '.local\bin\ae-mcp.exe'))
        $candidatePaths.Add((Join-Path $profileRoot '.local\bin\ae-mcp.cmd'))
    }

    foreach ($candidatePath in $candidatePaths) {
        if (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidatePath).Path
        }
    }

    $pathCommand = Get-Command 'ae-mcp' -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $pathCommand) {
        return $pathCommand.Source
    }
    return $null
}

$launcher = Resolve-AeMcpLauncher
$pluginUrl = if ([string]::IsNullOrWhiteSpace($env:AE_MCP_PLUGIN_URL)) {
    'http://127.0.0.1:11488'
} else {
    $env:AE_MCP_PLUGIN_URL
}

if ($Check) {
    [pscustomobject]@{
        ok = ($null -ne $launcher)
        launcher = $launcher
        pluginUrl = $pluginUrl
        expectedLaunchers = @(
            '%USERPROFILE%\.ae-mcp\bin\ae-mcp.exe',
            '%USERPROFILE%\.local\bin\ae-mcp.exe'
        )
        panelMenu = 'Window > Extensions > ae-mcp'
    } | ConvertTo-Json -Depth 3
    if ($null -eq $launcher) { exit 2 }
    exit 0
}

if ($null -eq $launcher) {
    [Console]::Error.WriteLine('ae-mcp launcher not found. Install the official matching ae-mcp release, open the ae-mcp panel in After Effects, and run scripts/install-ae-mcp-runtime.ps1. You may override the path with AE_MCP_LAUNCHER.')
    exit 127
}

if ([string]::IsNullOrWhiteSpace($env:AE_MCP_BACKEND)) {
    $env:AE_MCP_BACKEND = 'ae-mcp'
}
$env:AE_MCP_PLUGIN_URL = $pluginUrl

& $launcher
exit $LASTEXITCODE
