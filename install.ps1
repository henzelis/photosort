# PhotoSort installer for Windows.
# Usage: powershell -c "irm https://raw.githubusercontent.com/henzelis/photosort/main/install.ps1 | iex"
$ErrorActionPreference = "Stop"

$PkgUrl = "https://github.com/henzelis/photosort/archive/refs/heads/main.zip"
$Base   = Join-Path $env:LOCALAPPDATA "photosort"
$Venv   = Join-Path $Base "venv"
$Bin    = Join-Path $Base "bin"

Write-Host "==> Встановлюю PhotoSort..."

$Py = $null
foreach ($name in @("py", "python")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $Py = $cmd.Source; break }
}
if (-not $Py) {
    Write-Error "Потрібен Python 3.9+ — встановіть з https://www.python.org/downloads/ (увімкніть 'Add to PATH') і повторіть."
    exit 1
}

if (Test-Path $Base) { Remove-Item -Recurse -Force $Base }
& $Py -m venv $Venv
& (Join-Path $Venv "Scripts\python.exe") -m pip install -q --upgrade pip
& (Join-Path $Venv "Scripts\python.exe") -m pip install -q $PkgUrl

New-Item -ItemType Directory -Force $Bin | Out-Null
$Exe = Join-Path $Venv "Scripts\photosort.exe"
Set-Content -Path (Join-Path $Bin "photosort.cmd") -Value "@`"$Exe`" %*" -Encoding ASCII

try {
    & $Exe --version | Out-Null
    Write-Host "==> Готово! $(& $Exe --version)"
} catch {
    Write-Error "Помилка встановлення."
    exit 1
}

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$Bin*") {
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$Bin", "User")
    Write-Host ""
    Write-Host "⚠ Перезапустіть термінал, щоб команда photosort стала доступною."
}

Write-Host ""
Write-Host "Запуск:  photosort          — графічний інтерфейс (браузер)"
Write-Host "         photosort --help   — командний рядок"
