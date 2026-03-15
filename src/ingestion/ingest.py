"""Brand document ingestion CLI.

Downloads PDFs from the Azure Blob Storage `brand-assets` container,
uploads them to the Azure AI Foundry files API, and creates a vector store.

Usage:
    python -m src.ingestion.ingest

On completion, prints the VECTOR_STORE_ID. Copy it into .env / Key Vault.
"""

import logging
import sys

from azure.identity import DefaultAzureCredential

from src.agent.client import get_client
from src.config import settings
from src.ingestion.pdf_uploader import list_pdf_blobs, upload_pdf_to_files_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    client = get_client()

    logger.info("Listing PDFs in blob container: %s", settings.brand_assets_container)
    pdf_blobs = list_pdf_blobs()

    if not pdf_blobs:
        logger.error(
            "No PDFs found in container %r. Upload brand PDFs to Azure Blob Storage first.",
            settings.brand_assets_container,
        )
        sys.exit(1)

    logger.info("Found %d PDF(s): %s", len(pdf_blobs), [b.name for b in pdf_blobs])

    file_ids: list[str] = []
    for blob in pdf_blobs:
        logger.info("Uploading %s …", blob.name)
        file_id = upload_pdf_to_files_api(client, blob)
        file_ids.append(file_id)
        logger.info("  → file_id: %s", file_id)

    logger.info("Creating vector store from %d file(s) …", len(file_ids))
    vector_store = client.agents.vector_stores.create_and_poll(
        name="brand-guidelines",
        file_ids=file_ids,
    )

    logger.info("Vector store created: %s (status: %s)", vector_store.id, vector_store.status)

    print(f"\nVECTOR_STORE_ID={vector_store.id}")
    print("\nAdd this to your .env file or Key Vault secret.")
    print("Then run: python -m src.agent.client bootstrap")


if __name__ == "__main__":
    main()
