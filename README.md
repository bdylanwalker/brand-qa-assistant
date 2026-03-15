# Brand QA Assistant

A web app that performs brand compliance reviews. Enter a URL and the app will:

1. Screenshot the page with Playwright
2. Extract visible body text
3. Pass both to an Azure AI Foundry agent (gpt-4o-mini) with your brand guidelines
4. Return a structured Brand QA Report rendered in the browser

## Architecture

```
User enters URL in browser
  → POST /api/review (aiohttp, port 8080)
    → run_brand_review(url)
        → AI Foundry Agent (gpt-4o-mini)
            → capture_page_for_review(url)   [custom tool]
                → Playwright headless Chromium
                → screenshot (PNG → base64) + body text
            → file_search                     [built-in tool]
                → Vector Store (brand PDFs)
            → Synthesises findings → JSON
    → HTML report rendered in browser
```

## Prerequisites

- Python 3.12+
- Azure subscription with:
  - Azure AI Foundry project with gpt-4o-mini deployed
  - Azure Blob Storage (for brand PDFs)
  - Azure Container Apps (for deployment)
  - Azure Container Registry (for Docker image)

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

### 4. Bootstrap (ingest PDFs + create agent)

```bash
bash scripts/bootstrap.sh
```

This will:
- Download PDFs from Blob Storage → upload to Foundry → create vector store
- Create the AI agent with your brand instructions
- Update `.env` with `VECTOR_STORE_ID` and `AGENT_ID`

### 5. Run locally

```bash
uv run python -m src.web.app
```

Open [http://localhost:8080](http://localhost:8080) in your browser.

## Azure Deployment

Deployment is handled by two Azure DevOps pipelines defined in `.azure/pipelines/`.

### First-time setup

#### 1. Create an ARM service connection

In Azure DevOps: **Project Settings → Service connections → New service connection → Azure Resource Manager**.

#### 2. Create a variable group

In Azure DevOps: **Pipelines → Library → Variable groups → New variable group**.

Name it `brand-qa-assistant` and add the following variables:

| Variable | Description |
| --- | --- |
| `AZURE_SERVICE_CONNECTION` | Name of the ARM service connection |
| `RESOURCE_GROUP` | e.g. `rg-brand-qa-assistant-prod` |
| `LOCATION` | e.g. `eastus2` |
| `ENVIRONMENT_NAME` | e.g. `prod` |
| `ACR_NAME` | ACR name (without `.azurecr.io`) — set after first infra deploy |
| `CONTAINER_APP_NAME` | Container App name — set after first infra deploy |

#### 3. Register the pipelines

Add both YAML files as pipelines in ADO:
- `.azure/pipelines/infra.yml` — Infrastructure
- `.azure/pipelines/app.yml` — Build & Deploy

#### 4. Run the infra pipeline first

Triggers automatically on changes to `infra/` on `main`, or run it manually for the first deploy. After it completes, retrieve `ACR_NAME` and `CONTAINER_APP_NAME` from the deployment output:

```bash
az deployment group show \
  --resource-group <rg> \
  --name infra-<buildId> \
  --query "properties.outputs"
```

Add these values to the variable group, then the app pipeline can run.

#### 5. Run bootstrap inside the Container App

After the first app deploy, run ingestion to populate the vector store:

```bash
az containerapp exec \
  --name <container-app-name> \
  --resource-group <rg> \
  --command "python -m src.ingestion.ingest"
```

Then bootstrap the agent:

```bash
az containerapp exec \
  --name <container-app-name> \
  --resource-group <rg> \
  --command "python -m src.agent.client bootstrap"
```

Store the printed `VECTOR_STORE_ID` and `AGENT_ID` in Key Vault:

```bash
az keyvault secret set --vault-name <kv-name> --name vector-store-id --value '<id>'
az keyvault secret set --vault-name <kv-name> --name agent-id --value '<id>'
```

## Updating Brand Guidelines

1. Upload revised PDFs to the `brand-assets` Blob container
2. Re-run ingestion and bootstrap inside the Container App (step 5 above)

## Project Structure

```
brand-qa-assistant/
├── src/
│   ├── config.py                   # pydantic-settings, all env vars
│   ├── web/
│   │   ├── app.py                  # aiohttp server (port 8080)
│   │   └── static/
│   │       └── index.html          # Single-page UI
│   ├── agent/
│   │   ├── client.py               # AgentsClient singleton + bootstrap CLI
│   │   ├── tools.py                # capture_page_for_review tool definition
│   │   ├── runner.py               # run_brand_review(url) → dict
│   │   └── prompts.py              # System prompt + output schema
│   ├── screenshot/
│   │   ├── capture.py              # async capture_full_page(url) → bytes
│   │   └── page_content.py         # async get_page_content(url) → dict
│   └── ingestion/
│       ├── ingest.py               # CLI: python -m src.ingestion.ingest
│       └── pdf_uploader.py         # Blob → Foundry files API
├── brand_guidelines/
│   └── brand_instructions.md       # Brand rules injected into agent system prompt
├── infra/                          # Bicep infrastructure
│   ├── main.bicep
│   ├── main.bicepparam
│   └── modules/
│       ├── ai-foundry.bicep
│       ├── container-app.bicep
│       ├── container-registry.bicep
│       ├── keyvault.bicep
│       └── storage.bicep
├── .azure/
│   └── pipelines/
│       ├── infra.yml               # Infrastructure pipeline
│       └── app.yml                 # Build & deploy pipeline
├── scripts/
│   ├── bootstrap.sh                # First-run: ingest + create agent
│   └── local_tunnel.sh             # devtunnel host -p 8080
├── Dockerfile
├── .env.sample
└── pyproject.toml
```

## Notes

- **Screenshot cap**: Full-page screenshots are capped at 6000px height to stay within model context limits.
- **Authentication**: Production uses managed identity (no secrets in env vars at runtime). Locally, `DefaultAzureCredential` picks up `az login` credentials.
- **Scaling**: The Container App scales on HTTP concurrency (10 concurrent requests per replica, 1–3 replicas).
