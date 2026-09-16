$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\python.exe"
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$backend'; & '$python' -m uvicorn main:create_app --factory --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$frontend'; npm run dev"

Write-Host "Backend: http://127.0.0.1:8000/api/health"
Write-Host "Frontend (dev): http://localhost:5173"
