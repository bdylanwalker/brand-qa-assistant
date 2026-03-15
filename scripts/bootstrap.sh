#!/usr/bin/env bash
# bootstrap.sh — First-run setup: ingest brand PDFs and create the AI agent.
#
# Prerequisites:
#   - Python env with project installed: uv sync --extra dev
#   - .env filled in from .env.sample (except VECTOR_STORE_ID and AGENT_ID)
#   - Brand PDFs uploaded to the Azure Blob Storage brand-assets container
#
# Run from the project root:
#   bash scripts/bootstrap.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

echo "============================================================"
echo " Brand QA Assistant — Bootstrap"
echo "============================================================"
echo ""

# ---- Step 1: Ingest brand PDFs → create vector store ----
echo "[1/2] Running document ingestion..."
echo "      (Downloads PDFs from Azure Blob Storage → creates vector store)"
echo ""
INGEST_OUTPUT=$(python -m src.ingestion.ingest 2>&1)
echo "${INGEST_OUTPUT}"

VECTOR_STORE_ID=$(echo "${INGEST_OUTPUT}" | grep "^VECTOR_STORE_ID=" | cut -d= -f2)

if [[ -z "${VECTOR_STORE_ID}" ]]; then
  echo ""
  echo "ERROR: Failed to extract VECTOR_STORE_ID from ingestion output."
  echo "       Check the error messages above."
  exit 1
fi

echo ""
echo "✓ Vector store created: ${VECTOR_STORE_ID}"

# Update .env
if [[ -f ".env" ]]; then
  if grep -q "^VECTOR_STORE_ID=" .env; then
    sed -i.bak "s|^VECTOR_STORE_ID=.*|VECTOR_STORE_ID=${VECTOR_STORE_ID}|" .env && rm -f .env.bak
  else
    echo "VECTOR_STORE_ID=${VECTOR_STORE_ID}" >> .env
  fi
  echo "✓ Updated .env with VECTOR_STORE_ID"
fi

# Export so the agent bootstrap step picks it up
export VECTOR_STORE_ID="${VECTOR_STORE_ID}"

# ---- Step 2: Bootstrap agent ----
echo ""
echo "[2/2] Creating brand review agent..."
echo "      (Reads brand_guidelines/brand_instructions.md → creates agent)"
echo ""
AGENT_OUTPUT=$(python -m src.agent.client bootstrap 2>&1)
echo "${AGENT_OUTPUT}"

AGENT_ID=$(echo "${AGENT_OUTPUT}" | grep "^AGENT_ID=" | cut -d= -f2)

if [[ -z "${AGENT_ID}" ]]; then
  echo ""
  echo "ERROR: Failed to extract AGENT_ID from agent bootstrap output."
  echo "       Check the error messages above."
  exit 1
fi

echo ""
echo "✓ Agent created: ${AGENT_ID}"

# Update .env
if [[ -f ".env" ]]; then
  if grep -q "^AGENT_ID=" .env; then
    sed -i.bak "s|^AGENT_ID=.*|AGENT_ID=${AGENT_ID}|" .env && rm -f .env.bak
  else
    echo "AGENT_ID=${AGENT_ID}" >> .env
  fi
  echo "✓ Updated .env with AGENT_ID"
fi

echo ""
echo "============================================================"
echo " Bootstrap complete!"
echo "============================================================"
echo ""
echo "  VECTOR_STORE_ID = ${VECTOR_STORE_ID}"
echo "  AGENT_ID        = ${AGENT_ID}"
echo ""
echo "If deploying to Azure, store these in Key Vault:"
echo "  az keyvault secret set --vault-name <kv-name> --name vector-store-id --value '${VECTOR_STORE_ID}'"
echo "  az keyvault secret set --vault-name <kv-name> --name agent-id --value '${AGENT_ID}'"
echo ""
echo "Start the bot locally:"
echo "  uv run python -m src.bot.app"
