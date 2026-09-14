# Скрипт запуска платформы поддержки ЕАИСТ (Ollama AMD RX 6600, PostgreSQL, Redis, Qdrant, Backend, Frontend)
$ErrorActionPreference = "SilentlyContinue"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Запуск платформы поддержки (Tender-Hack)        " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. PostgreSQL (5432)
$pgProc = Get-Process postgres -ErrorAction SilentlyContinue
if (-not $pgProc) {
    Write-Host "[1/6] Запуск PostgreSQL (5432)..." -ForegroundColor Yellow
    $pgExe = "$env:LOCALAPPDATA\Programs\PostgreSQL\pgsql\bin\postgres.exe"
    if (Test-Path $pgExe) {
        Start-Process -FilePath $pgExe -ArgumentList "-D", "C:\ProgramData\pg_data", "-h", "127.0.0.1", "-p", "5432" -WindowStyle Hidden
    }
} else {
    Write-Host "[1/6] PostgreSQL уже запущен." -ForegroundColor Green
}

# 2. Redis (6379)
$redisProc = Get-Process redis-server -ErrorAction SilentlyContinue
if (-not $redisProc) {
    Write-Host "[2/6] Запуск Redis (6379)..." -ForegroundColor Yellow
    $redisExe = "$env:LOCALAPPDATA\Programs\Redis\redis-server.exe"
    if (Test-Path $redisExe) {
        Start-Process -FilePath $redisExe -ArgumentList "--port", "6379" -WindowStyle Hidden
    }
} else {
    Write-Host "[2/6] Redis уже запущен." -ForegroundColor Green
}

# 3. Qdrant (6333)
$qdrantProc = Get-Process qdrant -ErrorAction SilentlyContinue
if (-not $qdrantProc) {
    Write-Host "[3/6] Запуск Qdrant (6333)..." -ForegroundColor Yellow
    $qdrantExe = "$env:LOCALAPPDATA\Programs\Qdrant\qdrant.exe"
    if (Test-Path $qdrantExe) {
        Start-Process -FilePath $qdrantExe -WindowStyle Hidden
    }
} else {
    Write-Host "[3/6] Qdrant уже запущен." -ForegroundColor Green
}

# 4. Ollama (11434) с оптимизацией AMD RX 6600
$ollamaProc = Get-Process ollama -ErrorAction SilentlyContinue
if (-not $ollamaProc) {
    Write-Host "[4/6] Запуск Ollama на AMD Radeon RX 6600 (11434)..." -ForegroundColor Yellow
    [System.Environment]::SetEnvironmentVariable('HSA_OVERRIDE_GFX_VERSION', '10.3.0', 'User')
    $env:HSA_OVERRIDE_GFX_VERSION = '10.3.0'
    $env:OLLAMA_NUM_PARALLEL = '1'
    $env:OLLAMA_FLASH_ATTENTION = '1'
    $env:OLLAMA_GPU_OVERHEAD = '0'
    $env:OLLAMA_KEEP_ALIVE = '10m'
    
    $ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $ollamaExe) {
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    }
} else {
    Write-Host "[4/6] Ollama уже запущена." -ForegroundColor Green
}

Start-Sleep -Seconds 2

# 5. Backend FastAPI (8000)
$root = $PSScriptRoot
$backendDir = Join-Path $root "backend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

# Проверяем, слушает ли порт 8000
$port8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $port8000) {
    Write-Host "[5/6] Запуск Backend API (FastAPI: 8000)..." -ForegroundColor Yellow
    Start-Process -FilePath $pythonExe -ArgumentList "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload" -WorkingDirectory $backendDir -WindowStyle Hidden
} else {
    Write-Host "[5/6] Backend API уже работает на порту 8000." -ForegroundColor Green
}

# 6. Frontend Vite (5173)
$frontendDir = Join-Path $root "frontend"
$port5173 = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if (-not $port5173) {
    Write-Host "[6/6] Запуск Frontend Vite (5173)..." -ForegroundColor Yellow
    Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -WorkingDirectory $frontendDir -WindowStyle Hidden
} else {
    Write-Host "[6/6] Frontend уже работает на порту 5173." -ForegroundColor Green
}

Start-Sleep -Seconds 3

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Все сервисы запущены!" -ForegroundColor Green
Write-Host " Веб-интерфейс: http://localhost:5173" -ForegroundColor White
Write-Host " Документация API: http://localhost:8000/docs" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
