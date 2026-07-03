#!/usr/bin/env bash
set -euo pipefail

echo "=== Setting up Pipecat Voice Bot ==="
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
uv sync

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Start LM Studio with an LLM and Whisper model on localhost:1234"
echo "  2. cp .env.example .env and edit credentials"
echo "  3. Start server: uv run python server.py"
echo "  4. Start tunnel: cloudflared tunnel --url http://localhost:8005"
echo "  5. Open the tunnel URL in a browser"
