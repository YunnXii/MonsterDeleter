$ErrorActionPreference = "Stop"

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "叫家琦来" `
  --add-data "characters;characters" `
  --hidden-import send2trash `
  main.py

Write-Host "构建完成：dist\叫家琦来.exe"
