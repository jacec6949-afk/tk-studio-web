$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .env)) {
  Copy-Item .env.aliyun.example .env
  Write-Host '已创建 .env，请先填写域名和密钥后重新运行。'
  exit 1
}
$text = Get-Content -Raw -Encoding UTF8 nginx/conf.d/tk-studio.conf
if ($text.Contains('API_DOMAIN')) {
  Write-Host '请先将 nginx/conf.d/tk-studio.conf 中的 API_DOMAIN 替换为你的后端域名。'
  exit 1
}
docker compose -f docker-compose.aliyun.yml up -d --build
Write-Host '后端已启动。检查：Invoke-RestMethod http://127.0.0.1/api/health'
