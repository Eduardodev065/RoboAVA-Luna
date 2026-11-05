$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Instale Python 3.11 ou superior (64 bits) e tente novamente.' }
}
& $python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências.' }
$env:PLAYWRIGHT_BROWSERS_PATH = '0'
$env:NODE_OPTIONS = '--use-system-ca'
& $python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar Chromium.' }
& $python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw 'Os testes falharam.' }
$pythonRoot = (& $python -c 'import sys; print(sys.base_prefix)').Trim()
$tkPackage = Join-Path $pythonRoot 'Lib\tkinter'
$tclData = Join-Path $pythonRoot 'tcl'
$tkBinary = Join-Path $pythonRoot 'DLLs\_tkinter.pyd'
$tclBinary = Join-Path $pythonRoot 'DLLs\tcl86t.dll'
$tkRuntime = Join-Path $pythonRoot 'DLLs\tk86t.dll'
& $python -m PyInstaller --noconfirm --clean --onedir --windowed --name RoboAVA-Luna --icon "assets\luna.ico" --collect-all playwright --collect-all openai --add-data "codex-rejected-cas.pem:." --add-data "assets:assets" --add-data "${tkPackage}:tkinter" --add-data "${tclData}:tcl" --add-binary "${tkBinary}:." --add-binary "${tclBinary}:." --add-binary "${tkRuntime}:." robo_ava_gui.py
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar executável.' }
& $python -m PyInstaller --noconfirm --clean --onedir --console --name RoboAVA-Worker --collect-all playwright --collect-all openai --add-data "codex-rejected-cas.pem:." robo_ava_console.py
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar processo de automação.' }
Copy-Item -LiteralPath "$PSScriptRoot\dist\RoboAVA-Worker\RoboAVA-Worker.exe" -Destination "$PSScriptRoot\dist\RoboAVA-Luna\RoboAVA-Worker.exe" -Force
$browsers = Join-Path $PSScriptRoot '.venv\Lib\site-packages\playwright\driver\package\.local-browsers'
$browserTarget = Join-Path $PSScriptRoot 'dist\RoboAVA-Luna\_internal\playwright\driver\package\.local-browsers'
if (Test-Path -LiteralPath $browsers) {
    Copy-Item -LiteralPath $browsers -Destination $browserTarget -Recurse -Force
}
Write-Host "Pronto: $PSScriptRoot\dist\RoboAVA-Luna\RoboAVA-Luna.exe"
