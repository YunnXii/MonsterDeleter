$ErrorActionPreference = "Stop"

python tools/build_app_icon.py

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "叫家琦来" `
  --icon "build\app.ico" `
  --add-data "characters;characters" `
  --add-data "build\app.ico;assets" `
  --hidden-import send2trash `
  main.py

Write-Host "构建完成：dist\叫家琦来.exe"
