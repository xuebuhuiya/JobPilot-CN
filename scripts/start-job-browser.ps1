param([switch]$Show)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$profilePath = Join-Path $repoRoot 'private\chrome-profile'
$candidates = @(
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
)
$chromePath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (!$chromePath) { throw 'Google Chrome was not found.' }
New-Item -ItemType Directory -Force -Path $profilePath | Out-Null
$argsForChrome = @(
    '--remote-debugging-address=127.0.0.1',
    '--remote-debugging-port=9222',
    ('--user-data-dir="' + $profilePath + '"'),
    '--no-first-run',
    '--no-default-browser-check'
)
if ($Show) {
    # The user-facing launcher requests an interactive browser for manual login.
    $argsForChrome += @('https://www.zhipin.com/', 'https://www.zhaopin.com/')
    Start-Process -FilePath $chromePath -ArgumentList $argsForChrome -WindowStyle Normal
} else {
    $argsForChrome += 'about:blank'
    Start-Process -FilePath $chromePath -ArgumentList $argsForChrome -WindowStyle Hidden
}
Write-Output 'Dedicated job browser requested. Profile is private/chrome-profile. Login is manual.'
