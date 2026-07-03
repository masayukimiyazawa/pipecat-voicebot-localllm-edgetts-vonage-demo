#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TUNNEL_LOG="$SCRIPT_DIR/tunnel.log"
SERVER_LOG="$SCRIPT_DIR/server.log"

echo "=== Starting cloudflared tunnel ==="

# Kill existing cloudflared
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1

# Start cloudflared in background
cloudflared tunnel --url http://localhost:8005 > "$TUNNEL_LOG" 2>&1 &
CLOUDFLARED_PID=$!
echo "cloudflared PID: $CLOUDFLARED_PID"

# Wait for the tunnel URL to appear in logs
TUNNEL_URL=""
echo "Waiting for tunnel URL..."
for i in $(seq 1 30); do
    TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -n 1 || true)
    if [ -n "$TUNNEL_URL" ]; then
        echo "Found URL: $TUNNEL_URL"
        break
    fi
    sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
    echo "Failed to get tunnel URL. Last 10 lines of tunnel log:"
    tail -n 10 "$TUNNEL_LOG"
    exit 1
fi

echo "Tunnel URL: $TUNNEL_URL"

# Restart server
echo "=== Restarting server ==="
lsof -ti:8005 | xargs kill -9 2>/dev/null || true
sleep 2

cd "$SCRIPT_DIR" && nohup uv run python server.py > "$SERVER_LOG" 2>&1 &
echo "Server PID: $!"

# Wait for server to be ready (models are pre-loaded at startup, may take ~60s)
echo "Waiting for server to start (model preloading)..."
for i in $(seq 1 90); do
    if curl -s http://localhost:8005/health > /dev/null 2>&1; then
        echo "Server is UP!"
        break
    fi
    if [ $i -eq 90 ]; then
        echo "Server failed to start. Check $SERVER_LOG"
        tail -n 20 "$SERVER_LOG"
        exit 1
    fi
    sleep 1
done

echo "=== Done ==="
echo ""
echo "Video Demo: ${TUNNEL_URL}"
echo ""
echo "Vonage Voice API Webhook URL (set as Answer URL):"
echo "${TUNNEL_URL}/voice/webhook"
echo ""
