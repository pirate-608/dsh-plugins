param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("doctor", "configure", "login", "status", "logout", "todo", "courses", "activities", "activity", "assignments", "download")]
    [string]$Operation,

    [string]$CourseId,
    [string]$ActivityId,
    [string]$ReferenceId,
    [string]$DestinationRoot,
    [string]$Filename
)

$ErrorActionPreference = "Stop"
$PluginRoot = Split-Path -Parent $PSScriptRoot

function Stop-Safely([string]$Message) {
    [Console]::Error.WriteLine($Message)
    exit 2
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv was not found on PATH. The MCP and tronclass fallback are both unavailable."
    exit 2
}

$Arguments = @($Operation)
switch ($Operation) {
    { $_ -in @("activities", "assignments") } {
        if ($CourseId -notmatch "^[0-9]{1,32}$") { Stop-Safely "$Operation requires -CourseId with a numeric opaque ID." }
        $Arguments += @("--course-id", $CourseId)
    }
    "activity" {
        if ($ActivityId -notmatch "^[0-9]{1,32}$") { Stop-Safely "activity requires -ActivityId with a numeric opaque ID." }
        $Arguments += @("--activity-id", $ActivityId)
    }
    "download" {
        if ([string]::IsNullOrWhiteSpace($ReferenceId) -or [string]::IsNullOrWhiteSpace($DestinationRoot) -or [string]::IsNullOrWhiteSpace($Filename)) {
            Stop-Safely "download requires -ReferenceId, -DestinationRoot, and -Filename."
        }
        $Arguments += @("--reference-id", $ReferenceId, "--destination-root", $DestinationRoot, "--filename", $Filename)
    }
}

& uv run --project (Join-Path $PluginRoot "fallback") --python 3.9 --frozen zju-tronclass-fallback @Arguments
exit $LASTEXITCODE
