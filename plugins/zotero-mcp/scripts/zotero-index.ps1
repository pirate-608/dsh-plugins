param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("status", "index", "rebuild")]
    [string]$Operation
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    Write-Error "uvx was not found on PATH."
    exit 2
}

try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
} catch {
    Write-Error "Ollama is unavailable at http://127.0.0.1:11434."
    exit 2
}

if (@($tags.models | ForEach-Object { $_.name }) -notcontains "bge-m3:latest") {
    Write-Error "The required Ollama model bge-m3:latest is not installed."
    exit 2
}

$env:ZOTERO_LOCAL = "true"
$env:ZOTERO_EMBEDDING_MODEL = "ollama"
$env:OLLAMA_EMBEDDING_MODEL = "bge-m3:latest"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"

$package = "zotero-mcp-server[semantic,pdf]==0.9.1"
$command = @("--from", $package, "zotero-mcp-server")

switch ($Operation) {
    "status" { $command += "db-status" }
    "index" { $command += @("update-db", "--fulltext") }
    "rebuild" { $command += @("update-db", "--fulltext", "--force-rebuild") }
}

& uvx @command
exit $LASTEXITCODE
