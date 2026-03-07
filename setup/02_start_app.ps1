# Step 2: Start Docker Desktop and launch the app
# Run this after restart.

$projectDir = "B:\ai\llm-book"

# --- Start Docker Desktop if not running ---
$dockerProcess = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $dockerProcess) {
    Write-Host "Starting Docker Desktop..." -ForegroundColor Cyan
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
}

# --- Wait for Docker daemon to be ready ---
Write-Host "Waiting for Docker daemon..." -ForegroundColor Yellow
$maxWait = 120
$elapsed = 0
while ($elapsed -lt $maxWait) {
    $result = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Docker is ready!" -ForegroundColor Green
        break
    }
    Start-Sleep -Seconds 3
    $elapsed += 3
    Write-Host "  ...waiting ($elapsed s)" -ForegroundColor DarkGray
}

if ($elapsed -ge $maxWait) {
    Write-Host "ERROR: Docker didn't start within $maxWait seconds." -ForegroundColor Red
    Write-Host "Open Docker Desktop manually, wait for it to finish starting, then re-run this script." -ForegroundColor Yellow
    exit 1
}

# --- Launch the stack ---
Write-Host ""
Write-Host "Starting LLM Book Club stack..." -ForegroundColor Cyan
Set-Location $projectDir

# Only start the infra + backend services (skip vibevoice/ollama which need GPU)
docker compose up -d db redis
Write-Host "Waiting for DB and Redis to be healthy..." -ForegroundColor Yellow
docker compose up -d --wait db redis

Write-Host ""
Write-Host "Building and starting API + Worker + Web..." -ForegroundColor Cyan
docker compose up -d api worker web

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " Stack is starting!" -ForegroundColor Green
Write-Host ""
Write-Host " Frontend:  http://localhost:3000" -ForegroundColor White
Write-Host " API:       http://localhost:8000" -ForegroundColor White
Write-Host " API Docs:  http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host " To watch logs:  docker compose logs -f" -ForegroundColor DarkGray
Write-Host " To stop:        docker compose down" -ForegroundColor DarkGray
Write-Host "============================================" -ForegroundColor Green
