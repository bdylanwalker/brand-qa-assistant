"""PDF upload helpers: Blob Storage → Azure AI Foundry files API."""

import io
import logging
from typing import Iterator

from azure.identity import DefaultAzureCredential  # type: ignore
from azure.storage.blob import BlobClient, BlobServiceClient, ContainerClient  # type: ignore

from src.config import settings

logger = logging.getLogger(__name__)


class _BlobRef:
    """Minimal blob metadata used in the ingestion pipeline."""

    def __init__(self, name: str, container_client: ContainerClient) -> None:
        self.name = name
        self._container_client = container_client

    def download(self) -> bytes:
        blob_client: BlobClient = self._container_client.get_blob_client(self.name)
        return blob_client.download_blob().readall()


def list_pdf_blobs() -> list[_BlobRef]:
    """Return a list of _BlobRef for every *.pdf in the brand-assets container."""
    service_client = BlobServiceClient(settings.blob_account_url, credential=DefaultAzureCredential())
    container_client: ContainerClient = service_client.get_container_client(
        settings.brand_assets_container
    )

    blobs = []
    for item in container_client.list_blobs():
        if item.name.lower().endswith(".pdf"):
            blobs.append(_BlobRef(name=item.name, container_client=container_client))
    return blobs


def upload_pdf_to_files_api(client, blob: _BlobRef) -> str:
    """Download a blob PDF and upload it to the Foundry files API.

    Returns the file_id string.
    """
    pdf_bytes = blob.download()
    logger.info("Downloaded %s (%d bytes)", blob.name, len(pdf_bytes))

    # The files API expects a file-like object with a name attribute
    file_obj = io.BytesIO(pdf_bytes)
    file_obj.name = blob.name  # type: ignore[attr-defined]

    uploaded = client.files.upload_and_poll(
        file=file_obj,
        purpose="assistants",
    )
    return uploaded.id
