param(
    [string]$ApiBase = "http://localhost:4080",
    [string]$Email = $env:SEED_ADMIN_EMAIL,
    [string]$Password = $env:SEED_ADMIN_PASSWORD,
    [string]$Nickname = $env:SEED_ADMIN_NICKNAME
)

if ([string]::IsNullOrWhiteSpace($Email)) {
    $Email = "admin@example.com"
}
if ([string]::IsNullOrWhiteSpace($Password)) {
    # 本地测试默认密码；生产环境请务必通过环境变量覆盖。
    $Password = "Admin123!Pass"
}
if ([string]::IsNullOrWhiteSpace($Nickname)) {
    $Nickname = "Administrator"
}

$body = @{
    email = $Email
    password = $Password
    nickname = $Nickname
} | ConvertTo-Json

Write-Host "Registering admin user..."
try {
    $result = Invoke-RestMethod -Uri "$ApiBase/api/auth/register" -Method POST -Body $body -ContentType 'application/json'
    Write-Host "User registered: $($result.user.email)"
    Write-Host "Is Admin: $($result.user.is_admin)"
} catch {
    Write-Host "Error: $_"
    $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
    $reader.BaseStream.Position = 0
    $responseBody = $reader.ReadToEnd()
    Write-Host "Response: $responseBody"
}
