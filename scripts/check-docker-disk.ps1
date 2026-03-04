# Check Docker WSL disk usage
Write-Host "=== Docker WSL Disk Usage ===" -ForegroundColor Cyan

$dockerWslPath = "$env:LOCALAPPDATA\Docker\wsl"
$vhdxFiles = Get-ChildItem -Path $dockerWslPath -Recurse -Filter "*.vhdx" -ErrorAction SilentlyContinue

foreach ($file in $vhdxFiles) {
    $sizeGB = [math]::Round($file.Length / 1GB, 2)
    Write-Host "$($file.FullName)" -ForegroundColor Yellow
    Write-Host "  Size: $sizeGB GB" -ForegroundColor White
}

# Also check main WSL disk
$wslPath = "$env:LOCALAPPData\Packages\CanonicalGroupLimited*\LocalState"
$ubuntuVhdx = Get-ChildItem -Path $wslPath -Filter "*.vhdx" -ErrorAction SilentlyContinue
foreach ($file in $ubuntuVhdx) {
    $sizeGB = [math]::Round($file.Length / 1GB, 2)
    Write-Host "$($file.FullName)" -ForegroundColor Yellow
    Write-Host "  Size: $sizeGB GB" -ForegroundColor White
}

Write-Host "`n=== Total Docker Desktop Data Folder ===" -ForegroundColor Cyan
$totalSize = (Get-ChildItem -Path "$env:LOCALAPPDATA\Docker" -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
$totalGB = [math]::Round($totalSize / 1GB, 2)
Write-Host "Docker folder total: $totalGB GB" -ForegroundColor Magenta
