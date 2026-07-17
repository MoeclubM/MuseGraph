#!/bin/bash
# ============================================================
# MuseGraph Docker Rebuild Script
# Rebuilds containers with latest source code optimizations
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "MuseGraph Docker Rebuild"
echo "============================================"
echo "Project dir: $PROJECT_DIR"
echo ""

# Check Docker access
if ! docker info > /dev/null 2>&1; then
    echo "[!] Docker not accessible. Trying with sudo..."
    if ! sudo docker info > /dev/null 2>&1; then
        echo "[ERROR] Cannot access Docker. Please run with sudo or add user to docker group."
        echo "  Fix: sudo usermod -aG docker \$USER && newgrp docker"
        exit 1
    fi
    DOCKER="sudo docker"
else
    DOCKER="docker"
fi

cd "$PROJECT_DIR/docker"

echo "[1/5] Stopping compose containers before prune..."
$DOCKER compose down --remove-orphans

echo "[2/5] Pruning stopped containers, unused images, networks, and build cache..."
$DOCKER system prune -a -f

echo "[3/5] Pulling latest base images..."
$DOCKER compose pull postgres redis 2>/dev/null || true

echo "[4/5] Rebuilding server and web images (this may take 5-10 minutes)..."
$DOCKER compose build --no-cache server web

echo "[5/5] Recreating containers with new images..."
$DOCKER compose up -d --force-recreate server web

echo "Waiting for services to start..."
sleep 5

# Health check
echo ""
echo "Checking health..."
for i in $(seq 1 12); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3010/api/health 2>/dev/null || echo "000")
    if [ "$STATUS" = "200" ]; then
        echo "  [OK] MuseGraph is healthy! (attempt $i)"
        break
    fi
    echo "  Waiting... (attempt $i/12, status=$STATUS)"
    sleep 5
done

echo ""
echo "============================================"
echo "Rebuild complete!"
echo "============================================"
echo ""
echo "Web UI:    http://localhost:3010"
echo "API:       http://localhost:3010/api"
echo "API Docs:  http://localhost:3010/docs"
echo ""
echo "Container status:"
$DOCKER compose ps
echo ""
echo "Included optimizations:"
echo "  [x] Agent flexible creation framework (14 text types)"
echo "  [x] i18n internationalization (en-US + zh-CN)"
echo "  [x] Agent workspace refactoring"
echo "  [x] Model pricing fix (Usage-table safety net)"
echo "  [x] Collaborative writing mode (Ctrl+Space suggest)"
echo "  [x] Backend agent framework enhancement"
echo "  [x] Memory backend improvements"
echo "  [x] Shared types expansion"
