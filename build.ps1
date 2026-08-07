$ErrorActionPreference = "Stop"

# Keep this script ASCII-only so Windows PowerShell 5.1 does not misread UTF-8
# source text. Build the Chinese product name from Unicode code points instead.
$appName = "$([char]0x53EB)$([char]0x5BB6)$([char]0x7426)$([char]0x6765)"

python tools/build_app_icon.py

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name $appName `
  --icon "build\app.ico" `
  --add-data "characters;characters" `
  --add-data "build\app.ico;assets" `
  --hidden-import send2trash `
  main.py

Write-Host "Build complete: dist\$appName.exe"
