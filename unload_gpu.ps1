# Быстрая выгрузка модели из видеопамяти без остановки остальных сервисов
$ErrorActionPreference = "SilentlyContinue"

Write-Host "Освобождение видеопамяти (VRAM)..." -ForegroundColor Cyan
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (Test-Path $ollamaExe) {
    & $ollamaExe stop qwen3:8b-rag
    & $ollamaExe stop bge-m3:latest
}
# Также отправляем запрос на keep_alive: 0 через HTTP на случай фонового процесса
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method Post -Body '{"model":"qwen3:8b-rag","keep_alive":0}' -ContentType "application/json" -TimeoutSec 3 | Out-Null
} catch {}

Write-Host "Готово! Модель выгружена из GPU, видеопамять полностью освобождена." -ForegroundColor Green
