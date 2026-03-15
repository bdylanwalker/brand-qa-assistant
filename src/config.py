from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Azure AI Foundry project endpoint
    project_endpoint: str
    model_deployment: str = "gpt-4o-mini"

    # Set after running: python -m src.agent.client bootstrap
    agent_id: str = ""

    # Set after running: python -m src.ingestion.ingest
    vector_store_id: str = ""

    # Azure Blob Storage (source for brand PDFs)
    blob_connection_string: str
    brand_assets_container: str = "brand-assets"

    class Config:
        env_file = ".env"


settings = Settings()
