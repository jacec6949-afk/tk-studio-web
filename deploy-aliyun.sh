#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.aliyun.example .env
  echo "已创建 .env，请先填写域名和密钥后重新运行。"
  exit 1
fi

if grep -q 'API_DOMAIN' nginx/conf.d/tk-studio.conf; then
  echo "请先将 nginx/conf.d/tk-studio.conf 中的 API_DOMAIN 替换为你的后端域名。"
  exit 1
fi

docker compose -f docker-compose.aliyun.yml up -d --build

echo "后端已启动。检查：curl http://127.0.0.1/api/health"
