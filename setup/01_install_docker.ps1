# Step 1: Install Docker Desktop
# Run this, then restart your computer when prompted.
Write-Host "Installing Docker Desktop via winget..." -ForegroundColor Cyan
winget install Docker.DockerDesktop --accept-package-agreements --accept-source-agreements

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " Docker Desktop installed!" -ForegroundColor Green
Write-Host " RESTART your computer now." -ForegroundColor Yellow
Write-Host " After restart, run:" -ForegroundColor Yellow
Write-Host "   B:\ai\llm-book\setup\02_start_app.ps1" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
