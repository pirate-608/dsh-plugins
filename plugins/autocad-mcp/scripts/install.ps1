[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$pluginRoot = Split-Path -Parent $PSScriptRoot
$projectPath = Join-Path $pluginRoot "vendor\autocad-mcp"
$bundleSource = Join-Path $pluginRoot "autocad-plugin\DshAutoCADMCP.bundle"
$applicationPlugins = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins"
$bundleTarget = Join-Path $applicationPlugins "DshAutoCADMCP.bundle"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required and was not found on PATH."
}
if (-not (Test-Path -LiteralPath $projectPath)) {
    throw "Vendored autocad-mcp project not found: $projectPath"
}
if (-not (Test-Path -LiteralPath $bundleSource)) {
    throw "AutoCAD bundle not found: $bundleSource"
}

& uv sync --project $projectPath
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path $applicationPlugins | Out-Null
New-Item -ItemType Directory -Force -Path $bundleTarget | Out-Null
Copy-Item -LiteralPath (Join-Path $bundleSource "PackageContents.xml") -Destination $bundleTarget -Force
New-Item -ItemType Directory -Force -Path (Join-Path $bundleTarget "Contents") | Out-Null
Copy-Item -LiteralPath (Join-Path $bundleSource "Contents\mcp_dispatch.lsp") -Destination (Join-Path $bundleTarget "Contents") -Force

Write-Output "Python dependencies synchronized: $projectPath"
Write-Output "AutoCAD bundle installed: $bundleTarget"
Write-Output "Restart AutoCAD, then start a new DSH task and call system(operation='status')."
