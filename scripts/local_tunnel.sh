#!/usr/bin/env bash
# local_tunnel.sh — Expose the local web server via Dev Tunnels for external access.
#
# Prerequisites:
#   - devtunnel CLI installed: https://aka.ms/devtunnel-download
#   - Logged in: devtunnel user login  (uses your Azure/Microsoft account)
#   - App server running: python -m src.web.app

set -euo pipefail

PORT=8080

if ! command -v devtunnel &> /dev/null; then
  echo "Error: devtunnel not found. Install from https://aka.ms/devtunnel-download"
  exit 1
fi

echo "Starting Dev Tunnel on port ${PORT}..."
echo "After the tunnel starts, open the printed URL in your browser."
echo ""

devtunnel host -p "${PORT}" --allow-anonymous
