#!/bin/bash

echo "正在停止并移除所有容器和卷..."
docker compose -f docker-compose.local.yml down -v

echo "环境已重置，请运行 ./local-dev.sh 重新初始化环境" 