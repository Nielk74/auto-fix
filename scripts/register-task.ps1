[CmdletBinding()]
param(
    [string]$Config = (Join-Path $PSScriptRoot '..\config.local.yaml'),
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$Time = '17:30',
    [string]$TaskName = 'AutoFix-Daily',
    [switch]$Publish
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$configPath = (Resolve-Path -LiteralPath $Config).Path
$runner = Join-Path $PSScriptRoot 'run-today.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$actionArguments = '-NoProfile -NonInteractive -File "{0}" -Config "{1}"' -f $runner, $configPath
if ($Publish) { $actionArguments += ' -Publish' }

$action = New-ScheduledTaskAction -Execute $powershell -Argument $actionArguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::ParseExact($Time, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture))
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited

# Interactive logon uses this account's existing session; no password or token is stored.
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Investigate TeamCity C++ test failures and prepare verified fixes.' -Force
