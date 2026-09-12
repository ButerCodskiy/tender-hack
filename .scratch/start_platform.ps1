# Скрипт запуска всех сервисов платформы (Postgres, Qdrant, Redis, Ollama, Backend, Frontend)

$ErrorActionPreference = "Continue"

# 1. PostgreSQL
$pgExe = "$env:LOCALAPPDATA\Programs\PostgreSQL\pgsql\bin\postgres.exe"
if (Test-Path $pgExe) {
    Write-Host "Запуск PostgreSQL на 127.0.0.1:5432..."
    Start-Process -FilePath $pgExe -ArgumentList "-D", "C:\ProgramData\pg_data", "-h", "127.0.0.1", "-p", "5432" -WindowStyle Hidden
}

# 2. Qdrant
$qdrantExe = "$env:LOCALAPPDATA\Programs\Qdrant\qdrant.exe"
if (Test-Path $qdrantExe) {
    Write-Host "Запуск Qdrant на 127.0.0.1:6333..."
    Start-Process -FilePath $qdrantExe -WindowStyle Hidden
}

# 3. Redis
$redisExe = "$env:LOCALAPPDATA\Programs\Redis\redis-server.exe"
if (Test-Path $redisExe) {
    Write-Host "Запуск Redis на 127.0.0.1:6379..."
    Start-Process -FilePath $redisExe -ArgumentList "--port", "6379" -WindowStyle Hidden
}

# 4. Ollama с поддержкой RX 6600
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (Test-Path $ollamaExe) {
    Write-Host "Запуск Ollama на 127.0.0.1:11434 (AMD RX 6600)..."
    [System.Environment]::SetEnvironmentVariable('HSA_OVERRIDE_GFX_VERSION', '10.3.0', 'Process')
    [System.Environment]::SetEnvironmentVariable('OLLAMA_HOST', '127.0.0.1:11434', 'Process')
    [System.Environment]::SetEnvironmentVariable('OLLAMA_NUM_PARALLEL', '1', 'Process')
    [System.Environment]::SetEnvironmentVariable('OLLAMA_MAX_LOADED_MODELS', '1', 'Process')
    [System.Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '24h', 'Process')
    Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
}

Start-Sleep -Seconds 3

# 5. Backend FastAPI
$backendDir = Join-Path (Split-Path $PSScriptRoot -Parent) "backend"
Write-Host "Запуск Backend API на 127.0.0.1:8000..."
$env:Path = "$env:LOCALAPPDATA\Programs\PostgreSQL\pgsql\bin;$env:LOCALAPPDATA\Programs\Qdrant;$env:LOCALAPPDATA\Programs\Ollama;$env:LOCALAPPDATA\Programs\Redis;$env:Path"
Start-Process -FilePath "uv" -ArgumentList "run", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $backendDir -WindowStyle Hidden

# 6. Frontend Vite
$frontendDir = Join-Path (Split-Path $PSScriptRoot -Parent) "frontend"
$npmCmd = "$env:LOCALAPPDATA\Programs\nodejs\npm.cmd"
Write-Host "Запуск Frontend Vite на 127.0.0.1:5173..."
$env:Path = "$env:LOCALAPPDATA\Programs\nodejs;$env:Path"
Start-Process -FilePath $npmCmd -ArgumentList "run", "dev" -WorkingDirectory $frontendDir -WindowStyle Hidden

Write-Host "Ожидание готовности сервисов..."
Start-Sleep -Seconds 4
