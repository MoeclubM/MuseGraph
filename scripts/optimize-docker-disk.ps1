# Optimize Docker WSL disk

Write-Host "=== Step 1: Stopping Docker Desktop ===" -ForegroundColor Cyan
Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5

Write-Host "=== Step 2: Shutting down WSL ===" -ForegroundColor Cyan
wsl --shutdown
Start-Sleep -Seconds 5

Write-Host "=== Step 3: Optimizing Docker Data VHDX ===" -ForegroundColor Cyan
$dockerVhdx = "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx"
if (Test-Path $dockerVhdx) {
    Write-Host "Optimizing: $dockerVhdx" -ForegroundColor Yellow

    # Get size before
    $sizeBefore = (Get-Item $dockerVhdx).Length / 1GB
    Write-Host "Size before: $([math]::Round($sizeBefore, 2)) GB" -ForegroundColor White

    # Run diskpart to compact
    $diskpartScript = @"
select vdisk file="$dockerVhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
    $diskpartScript | diskpart

    # Get size after
    $sizeAfter = (Get-Item $dockerVhdx).Length / 1GB
    $saved = [math]::Round($sizeBefore - $sizeAfter, 2)
    Write-Host "Size after: $([math]::Round($sizeAfter, 2)) GB" -ForegroundColor Green
    Write-Host "Saved: $saved GB" -ForegroundColor Magenta
}

Write-Host "`n=== Step 4: Optimizing Docker Main VHDX ===" -ForegroundColor Cyan
$mainVhdx = "$env:LOCALAPPDATA\Docker\wsl\main\ext4.vhdx"
if (Test-Path $mainVhdx) {
    Write-Host "Optimizing: $mainVhdx" -ForegroundColor Yellow

    $sizeBefore = (Get-Item $mainVhdx).Length / 1GB
    Write-Host "Size before: $([math]::Round($sizeBefore, 2)) GB" -ForegroundColor White

    $diskpartScript = @"
select vdisk file="$mainVhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
    $diskpartScript | diskpart

    $sizeAfter = (Get-Item $mainVhdx).Length / 1GB
    $saved = [math]::Round($sizeBefore - $sizeAfter, 2)
    Write-Host "Size after: $([math]::Round($sizeAfter, 2)) GB" -ForegroundColor Green
    Write-Host "Saved: $saved GB" -ForegroundColor Magenta
}

Write-Host "`n=== Done! Starting Docker Desktop ===" -ForegroundColor Cyan
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
