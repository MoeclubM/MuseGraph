# Reset Docker WSL completely

Write-Host "=== Step 1: Stopping Docker Desktop ===" -ForegroundColor Cyan
Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

Write-Host "=== Step 2: Shutting down WSL ===" -ForegroundColor Cyan
wsl --shutdown
Start-Sleep -Seconds 3

Write-Host "=== Step 3: Unregistering Docker WSL distributions ===" -ForegroundColor Cyan

# Unregister docker-desktop
Write-Host "Removing docker-desktop..." -ForegroundColor Yellow
wsl --unregister docker-desktop 2>$null

# Unregister docker-desktop-data
Write-Host "Removing docker-desktop-data..." -ForegroundColor Yellow
wsl --unregister docker-desktop-data 2>$null

Write-Host "=== Step 4: Deleting VHDX files ===" -ForegroundColor Cyan
$dockerWslPath = "$env:LOCALAPPDATA\Docker\wsl"

# Delete disk folder
if (Test-Path "$dockerWslPath\disk") {
    Write-Host "Deleting disk folder..." -ForegroundColor Yellow
    Remove-Item "$dockerWslPath\disk" -Recurse -Force -ErrorAction SilentlyContinue
}

# Delete main folder
if (Test-Path "$dockerWslPath\main") {
    Write-Host "Deleting main folder..." -ForegroundColor Yellow
    Remove-Item "$dockerWslPath\main" -Recurse -Force -ErrorAction SilentlyContinue
}

# Delete data folder (docker-desktop-data)
if (Test-Path "$dockerWslPath\data") {
    Write-Host "Deleting data folder..." -ForegroundColor Yellow
    Remove-Item "$dockerWslPath\data" -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "=== Step 5: Checking remaining files ===" -ForegroundColor Cyan
$remainingSize = (Get-ChildItem -Path "$env:LOCALAPPDATA\Docker" -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
$remainingGB = [math]::Round($remainingSize / 1GB, 2)
Write-Host "Docker folder remaining: $remainingGB GB" -ForegroundColor Magenta

Write-Host "`n=== Done! Starting Docker Desktop (will recreate WSL) ===" -ForegroundColor Green
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

Write-Host "Docker will recreate the WSL distributions automatically." -ForegroundColor White
Write-Host "Wait about 30-60 seconds for Docker to fully start." -ForegroundColor White
