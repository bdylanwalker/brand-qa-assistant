"""AgentsClient singleton and agent bootstrap.

Usage (CLI):
    python -m src.agent.client bootstrap

This creates (or recreates) the agent with the current brand instructions
and prints the AGENT_ID to stdout. Store it in .env / Key Vault.
"""

import json
import logging
import sys
from pathlib import Path

from azure.ai.agents import AgentsClient  # type: ignore
from azure.ai.agents.models import (  # type: ignore
    FileSearchTool,
    FunctionTool,
    ToolSet,
)
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

from src.agent.prompts import BRAND_GUIDELINES_SECTION, SYSTEM_PROMPT_TEMPLATE
from src.agent.tools import CAPTURE_PAGE_TOOL_DEFINITION
from src.config import settings

logger = logging.getLogger(__name__)

BRAND_INSTRUCTIONS_PATH = Path(__file__).parent.parent.parent / "brand_guidelines" / "brand_instructions.md"

_client: AgentsClient | None = None


def get_client() -> AgentsClient:
    """Return a cached AgentsClient instance.

    Uses ManagedIdentityCredential inside Azure (Container App with system-assigned
    managed identity); falls back to DefaultAzureCredential locally.
    """
    global _client
    if _client is None:
        try:
            credential = ManagedIdentityCredential()
            # Probe to confirm it works; will raise if not in a managed-identity context
            credential.get_token("https://cognitiveservices.azure.com/.default")
        except Exception:
            credential = DefaultAzureCredential()

        _client = AgentsClient(
            endpoint=settings.project_endpoint,
            credential=credential,
        )
    return _client


def _build_system_prompt() -> str:
    brand_text = BRAND_INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip()
    guidelines = BRAND_GUIDELINES_SECTION.format(brand_instructions=brand_text) if brand_text else ""
    return SYSTEM_PROMPT_TEMPLATE + guidelines


def bootstrap_agent() -> str:
    """Create the brand review agent and return its ID.

    Run once (or after updating brand_instructions.md). Prints the AGENT_ID
    so you can copy it into .env / Key Vault.
    """
    client = get_client()

    if not settings.vector_store_id:
        raise RuntimeError(
            "VECTOR_STORE_ID is not set. Run `python -m src.ingestion.ingest` first."
        )

    toolset = ToolSet()
    toolset.add(FileSearchTool(vector_store_ids=[settings.vector_store_id]))
    toolset.add(FunctionTool(definitions=[CAPTURE_PAGE_TOOL_DEFINITION]))

    system_prompt = _build_system_prompt()

    agent = client.create_agent(
        model=settings.model_deployment,
        name="brand-qa-agent",
        instructions=system_prompt,
        tools=toolset.definitions,
        tool_resources=toolset.resources,
    )

    logger.info("Agent created: %s", agent.id)
    return agent.id


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2 or sys.argv[1] != "bootstrap":
        print("Usage: python -m src.agent.client bootstrap")
        sys.exit(1)

    agent_id = bootstrap_agent()
    print(f"\nAGENT_ID={agent_id}")
    print("\nAdd this to your .env file or Key Vault secret.")
