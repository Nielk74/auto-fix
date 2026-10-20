[CmdletBinding()]
param(
    [string]$Config = (Join-Path $PSScriptRoot '..\config.local.yaml'),
    [string]$Date,
    [switch]$Publish,
    [switch]$RetryBlocked
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$configPath = (Resolve-Path -LiteralPath $Config).Path
$executable = Join-Path $projectRoot '.venv\Scripts\auto-fix.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw 'Missing .venv executable. Run uv sync --locked --extra dev --python 3.12 first.'
}

$cliArguments = @('run', '--config', $configPath)
if ($Date) { $cliArguments += @('--date', $Date) }
if ($Publish) { $cliArguments += '--publish' }
if ($RetryBlocked) { $cliArguments += '--retry-blocked' }

# Tokens are inherited from the worker account or loaded by the CLI from local .env.
Push-Location -LiteralPath $projectRoot
try {
    & $executable @cliArguments
    $resultCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $resultCode
