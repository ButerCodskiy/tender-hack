# Скрипт остановки всех сервисов платформы и полного освобождения видеопамяти и ОЗУ
$ErrorActionPreference = "SilentlyContinue"

Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "  Остановка сервисов и освобождение памяти...     " -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow

# 1. Остановка Frontend (порт 5173)
Write-Host "[1/6] Остановка Vite Frontend..." -ForegroundColor Gray
$frontConns = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $frontConns) {
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
}

# 2. Остановка Backend (порт 8000)
Write-Host "[2/6] Остановка Backend API..." -ForegroundColor Gray
$backConns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $backConns) {
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
}

# 3. Полная выгрузка Ollama и освобождение видеопамяти (VRAM)
Write-Host "[3/6] Выгрузка нейросети и остановка Ollama (освобождение VRAM)..." -ForegroundColor Magenta
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (Test-Path $ollamaExe) {
    & $ollamaExe stop qwen3:8b-rag 2>$null
    & $ollamaExe stop bge-m3:latest 2>$null
}
Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "ollama app" -Force -ErrorAction SilentlyContinue

# 4. Остановка Qdrant (порт 6333)
Write-Host "[4/6] Остановка векторной БД Qdrant..." -ForegroundColor Gray
Stop-Process -Name "qdrant" -Force -ErrorAction SilentlyContinue

# 5. Остановка Redis (порт 6379)
Write-Host "[5/6] Остановка кэша Redis..." -ForegroundColor Gray
Stop-Process -Name "redis-server" -Force -ErrorAction SilentlyContinue

# 6. Остановка PostgreSQL (порт 5432)
Write-Host "[6/6] Остановка базы данных PostgreSQL..." -ForegroundColor Gray
$pgExe = "$env:LOCALAPPDATA\Programs\PostgreSQL\pgsql\bin\pg_ctl.exe"
if (Test-Path $pgExe) {
    & $pgExe -D "C:\ProgramData\pg_data" -m fast stop 2>$null
}
Stop-Process -Name "postgres" -Force -ErrorAction SilentlyContinue

Write-Host "==================================================" -ForegroundColor Green
Write-Host " Все сервисы успешно остановлены!" -ForegroundColor Green
Write-Host " Видеопамять (VRAM) и оперативная память свободны." -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
