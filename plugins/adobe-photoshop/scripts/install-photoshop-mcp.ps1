[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$serverVersion = '0.1.11'
$mcpVersion = '1.29.0'
$photoshopApiVersion = '0.24.2'

$uv = Get-Command 'uv' -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $uv) {
    throw 'uv is required. Install the official Astral uv package, then rerun this script.'
}

$toolPython = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'uv\tools\photoshop-mcp-server\Scripts\python.exe'

if ($CheckOnly) {
    $launcher = Get-Command 'photoshop-mcp-server' -CommandType Application -ErrorAction SilentlyContinue
    $versions = @{}
    if (Test-Path -LiteralPath $toolPython -PathType Leaf) {
        $json = & $toolPython -c "import importlib.metadata as m, json; print(json.dumps({n:m.version(n) for n in ['photoshop-mcp-server','mcp','photoshop-python-api']}))"
        $versions = $json | ConvertFrom-Json
    }
    [pscustomobject]@{
        ok = ($null -ne $launcher -and $versions.'photoshop-mcp-server' -eq $serverVersion -and $versions.mcp -eq $mcpVersion -and $versions.'photoshop-python-api' -eq $photoshopApiVersion)
        launcher = if ($null -ne $launcher) { $launcher.Source } else { $null }
        versions = $versions
    } | ConvertTo-Json -Depth 4
    exit 0
}

& $uv.Source tool install --force --python 3.12 "photoshop-mcp-server==$serverVersion" --with "mcp==$mcpVersion" --with "photoshop-python-api==$photoshopApiVersion"
if ($LASTEXITCODE -ne 0) {
    throw "Photoshop MCP installation failed with exit code $LASTEXITCODE"
}

& $PSCommandPath -CheckOnly
