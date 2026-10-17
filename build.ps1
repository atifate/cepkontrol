$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m pip install pyinstaller==6.22.3
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m PyInstaller --noconfirm --clean --onefile --windowed --name CepKontrol --icon assets/icon.ico --add-data 'assets/icon.ico;assets' app.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python build-tools/package.py
exit $LASTEXITCODE
