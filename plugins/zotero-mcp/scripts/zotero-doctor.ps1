$ErrorActionPreference = "Stop"

$result = [ordered]@{
    ok = $true
    uv = $false
    zotero_process = $false
    zotero_connector_api = $false
    zotero_local_api = $false
    zotero_local_api_status = $null
    ollama_api = $false
    embedding_model = "bge-m3:latest"
    embedding_model_available = $false
    warnings = @()
}

$result.uv = $null -ne (Get-Command uvx -ErrorAction SilentlyContinue)
if (-not $result.uv) {
    $result.ok = $false
    $result.warnings += "uvx was not found on PATH."
}

$result.zotero_process = $null -ne (Get-Process zotero -ErrorAction SilentlyContinue)
if (-not $result.zotero_process) {
    $result.warnings += "Zotero is not running."
}

if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
    $connectorStatus = & curl.exe --noproxy "*" --silent --show-error --output NUL --write-out "%{http_code}" --max-time 5 "http://127.0.0.1:23119/connector/ping" 2>$null
    $result.zotero_connector_api = $LASTEXITCODE -eq 0 -and $connectorStatus -eq "200"

    $apiStatus = & curl.exe --noproxy "*" --silent --show-error --output NUL --write-out "%{http_code}" --max-time 5 --header "Zotero-API-Version: 3" "http://127.0.0.1:23119/api/users/0/items?limit=1" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $result.zotero_local_api_status = $apiStatus
        $result.zotero_local_api = $apiStatus -eq "200"
    }
} else {
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:23119/api/users/0/items?limit=1" -Headers @{ "Zotero-API-Version" = "3" } -UseBasicParsing -TimeoutSec 5
        $result.zotero_connector_api = $true
        $result.zotero_local_api = $true
        $result.zotero_local_api_status = "200"
    } catch {
        if ($_.Exception.Response) {
            $result.zotero_local_api_status = [string][int]$_.Exception.Response.StatusCode
        }
    }
}

if (-not $result.zotero_local_api) {
    if ($result.zotero_connector_api -and $result.zotero_local_api_status -eq "403") {
        $result.warnings += "Zotero is running, but local API access is disabled; enable it in Settings > Advanced."
    } else {
        $result.warnings += "Zotero local API is unavailable; start Zotero and enable local API access in Settings > Advanced."
    }
}

try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    $result.ollama_api = $true
    $result.embedding_model_available = @($tags.models | ForEach-Object { $_.name }) -contains $result.embedding_model
    if (-not $result.embedding_model_available) {
        $result.warnings += "Ollama is running but bge-m3:latest is not installed."
    }
} catch {
    $result.warnings += "Ollama is unavailable at http://127.0.0.1:11434."
}

if (-not $result.zotero_local_api -or -not $result.ollama_api -or -not $result.embedding_model_available) {
    $result.ok = $false
}

$result | ConvertTo-Json -Depth 4
if (-not $result.ok) { exit 2 }
