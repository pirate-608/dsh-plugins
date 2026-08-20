[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$release = 'v0.9.2'
$repository = 'https://github.com/JUNKDOGE-JOE/after-effects-mcp'
$mcpSdk = '1.27.0'

$uv = Get-Command 'uv' -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $uv) {
    throw 'uv is required. Install the official Astral uv package, then rerun this script.'
}

if ($CheckOnly) {
    $aeMcp = Get-Command 'ae-mcp' -CommandType Application -ErrorAction SilentlyContinue
    $installedMcpSdk = $null
    $toolPython = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'uv\tools\ae-mcp\Scripts\python.exe'
    if (Test-Path -LiteralPath $toolPython -PathType Leaf) {
        $installedMcpSdk = & $toolPython -c "import importlib.metadata as md; print(md.version('mcp'))"
    }
    [pscustomobject]@{
        ok = ($null -ne $aeMcp -and $installedMcpSdk -eq $mcpSdk)
        aeMcp = if ($null -ne $aeMcp) { $aeMcp.Source } else { $null }
        mcpSdk = $installedMcpSdk
        requiredMcpSdk = $mcpSdk
        release = $release
    } | ConvertTo-Json -Depth 3
    exit 0
}

$core = "git+$repository@$release#subdirectory=packages/core"
$bridge = "git+$repository@$release#subdirectory=packages/bridge"
$snapshot = "git+$repository@$release#subdirectory=packages/snapshot-mss"

& $uv.Source tool install --force --from $core ae-mcp --with $bridge --with $snapshot --with "mcp==$mcpSdk"
if ($LASTEXITCODE -ne 0) {
    throw "ae-mcp runtime installation failed with exit code $LASTEXITCODE"
}

& $PSCommandPath -CheckOnly
