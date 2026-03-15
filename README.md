# Brand QA Assistant

A Microsoft Teams bot that performs brand compliance reviews. Post a URL in a Teams channel and the bot will:

1. Screenshot the page with Playwright
2. Extract visible body text
3. Pass both to an Azure AI Foundry agent (gpt-4o-mini) with your brand guidelines
4. Return a structured Brand QA Report as an Adaptive Card

## Architecture

```
Teams User posts URL
  → Azure Bot Service (channel routing)
    → Container App / aiohttp server
      → Send immediate ack ("Reviewing…")
      → run_brand_review(url)
          → AI Foundry Agent (gpt-4o-mini)
              → capture_page_for_review(url)   [custom tool]
                  → Playwright headless Chromium
                  → screenshot (PNG → base64) + body text
              → file_search                     [built-in tool]
                  → Vector Store (brand PDFs)
              → Synthesizes findings → JSON
          → Build Adaptive Card
  → Teams channel shows Brand QA Report card
```

## Prerequisites

- Python 3.12+
- Azure subscription with:
  - Azure AI Foundry project with gpt-4o-mini deployed
  - Azure Blob Storage (for brand PDFs)
  - Azure Bot Service (Teams channel registration)
  - Azure Container Apps (for deployment)
- [Dev Tunnels CLI](https://aka.ms/devtunnel-download) for local testing

## Local Setup

### 1. Install dependencies

```bash
uv sync --extra dev
uv run playwright install chromium
```

### 2. Configure environment

```bash
cp .env.sample .env
# Edit .env — fill in all values except VECTOR_STORE_ID and AGENT_ID
```

### 3. Upload brand PDFs

Upload your brand guideline PDFs to the `brand-assets` container in your Azure Blob Storage account.

### 4. Update brand instructions

Edit `brand_guidelines/brand_instructions.md` with your actual brand rules (colours, typography, tone of voice, etc.).

### 5. Bootstrap (ingest + create agent)

```bash
bash scripts/bootstrap.sh
```

This will:
- Download PDFs from Blob Storage → upload to Foundry → create vector store
- Create the AI agent with your brand instructions
- Update `.env` with `VECTOR_STORE_ID` and `AGENT_ID`

### 6. Run the bot locally

```bash
uv run python -m src.bot.app
```

In a separate terminal:

```bash
bash scripts/local_tunnel.sh
```

Copy the tunnel URL and update your Azure Bot Service messaging endpoint to:
```
https://<tunnel-id>-3978.<region>.devtunnels.ms/api/messages
```

### 7. Test

- **Bot Framework Emulator**: Connect to `http://localhost:3978/api/messages`
- **Teams**: Sideload the Teams app manifest (see Teams developer portal)

Post any URL — e.g., `https://example.com` — and the bot will return a brand review card.

## Azure Deployment

### Build and push Docker image

```bash
az acr build \
  --registry <acr-name> \
  --image brand-qa-assistant:latest \
  .
```

### Deploy infrastructure

```bash
az deployment group create \
  --resource-group <rg-name> \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters botAppId=<app-id> botAppPassword=<app-secret>
```

### Run ingestion inside Container App

```bash
az containerapp exec \
  --name <ca-name> \
  --resource-group <rg-name> \
  --command "python -m src.ingestion.ingest"
```

### Store secrets in Key Vault

```bash
az keyvault secret set --vault-name <kv-name> --name vector-store-id --value '<id>'
az keyvault secret set --vault-name <kv-name> --name agent-id --value '<id>'
```

### Update Bot Service endpoint

```bash
az bot update \
  --resource-group <rg-name> \
  --name <bot-name> \
  --endpoint "https://<container-app-fqdn>/api/messages"
```

## Updating Brand Guidelines

1. Edit `brand_guidelines/brand_instructions.md`
2. Re-run `bash scripts/bootstrap.sh` — this creates a new agent version

## Project Structure

```
brand-qa-assistant/
├── src/
│   ├── config.py                   # pydantic-settings, all env vars
│   ├── bot/
│   │   ├── app.py                  # aiohttp server (port 3978)
│   │   └── activity_handler.py     # URL detection, ack, dispatch, card send
│   ├── agent/
│   │   ├── client.py               # AgentsClient singleton + bootstrap CLI
│   │   ├── tools.py                # capture_page_for_review tool definition
│   │   ├── runner.py               # run_brand_review(url) → dict
│   │   └── prompts.py              # System prompt + output schema
│   ├── screenshot/
│   │   ├── capture.py              # async capture_full_page(url) → bytes
│   │   └── page_content.py         # async get_page_content(url) → dict
│   ├── ingestion/
│   │   ├── ingest.py               # CLI: python -m src.ingestion.ingest
│   │   └── pdf_uploader.py         # Blob → Foundry files API
│   └── cards/
│       └── brand_report_card.py    # dict → Adaptive Card attachment
├── brand_guidelines/
│   └── brand_instructions.md       # Your brand rules (edit before deploying)
├── infra/                          # Bicep infrastructure
├── scripts/
│   ├── bootstrap.sh                # First-run: ingest + create agent
│   └── local_tunnel.sh             # devtunnel host -p 3978
├── Dockerfile
├── .env.sample
└── pyproject.toml
```

## Notes

- **Teams SDK**: Uses Microsoft 365 Agents SDK (`microsoft-agents-*`). Falls back to `botbuilder-integration-aiohttp` (EOL Dec 2025) if the M365 SDK is not yet stable on PyPI.
- **Screenshot cap**: Full-page screenshots are capped at 6000px height to stay within AI model context limits.
- **Teams timeout**: The bot sends an immediate acknowledgement before starting the review to avoid the 15-second Teams activity timeout.
- **Authentication**: Production uses managed identity (no secrets in env vars at runtime). Locally, `DefaultAzureCredential` picks up `az login` credentials.
