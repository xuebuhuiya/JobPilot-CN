param([int]$Port = 8787)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$url = "http://127.0.0.1:$Port"
try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 } catch { $health = $null }
if ($health -and $health.app -eq 'JobPilot-CN') { Write-Output "JobPilot-CN is running: $url"; exit 0 }
if ($health) { throw "Port $Port is serving another app." }
$python = (Get-Command python -ErrorAction Stop).Source
$logRoot = Join-Path $repoRoot 'data\runtime'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$process = Start-Process -FilePath $python -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
    -ArgumentList @('workbench.py', '--port', "$Port") `
    -RedirectStandardOutput (Join-Path $logRoot "jobpilot-$stamp.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "jobpilot-$stamp.stderr.log")
for ($attempt=0; $attempt -lt 20; $attempt++) {
    if ($process.HasExited) { throw 'JobPilot stopped. Check data/runtime logs.' }
    try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1 } catch { $health = $null }
    if ($health -and $health.app -eq 'JobPilot-CN') { Write-Output "JobPilot-CN started: $url"; exit 0 }
    Start-Sleep -Milliseconds 500
}
throw 'JobPilot did not become healthy. Check data/runtime logs.'
