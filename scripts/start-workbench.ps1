param([int]$Port = 8686)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot '..\upstream\BossHunter'))
$runner = Join-Path $sourceRoot '.venv\Scripts\bosshunter.exe'
$configPath = Join-Path $sourceRoot 'config.yaml'
$logRoot = Join-Path $repoRoot 'data\runtime'
$url = "http://127.0.0.1:$Port"
if (!(Test-Path -LiteralPath $runner) -or !(Test-Path -LiteralPath $configPath)) {
    throw 'BossHunter installation or local config is missing. See docs/deployment-windows.md.'
}
try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 } catch { $health = $null }
if ($health -and $health.status -eq 'ok' -and $health.version -eq '2.4.0') {
    Write-Output "BossHunter is already running: $url/config"
    exit 0
}
if ($health) { throw "Port $Port is serving an unexpected application. No process was stopped." }
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$errorLog = Join-Path $logRoot "workbench-$stamp.stderr.log"
$process = Start-Process -FilePath $runner -WorkingDirectory $sourceRoot -WindowStyle Hidden -PassThru `
    -ArgumentList @('--config', ('"' + $configPath + '"'), 'web', '--no-open', '--port', "$Port") `
    -RedirectStandardOutput (Join-Path $logRoot "workbench-$stamp.stdout.log") -RedirectStandardError $errorLog
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if ($process.HasExited) { throw "BossHunter stopped. See $errorLog" }
    try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1 } catch { $health = $null }
    if ($health -and $health.status -eq 'ok' -and $health.version -eq '2.4.0') {
        [pscustomobject]@{ pid = $process.Id; url = $url; started_at = (Get-Date).ToString('o') } |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logRoot 'workbench.json') -Encoding utf8
        Write-Output "BossHunter started: $url/config"
        exit 0
    }
    Start-Sleep -Milliseconds 500
}
throw "Workbench did not become healthy. See $errorLog"
