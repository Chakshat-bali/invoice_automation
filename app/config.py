import os
from pathlib import Path
from pydantic_settings import BaseSettings


# Get the project root directory (parent of the app directory)
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    database_url: str = "sqlite:///./storage/invoices.db"
    storage_dir: str = "./storage/uploads"
    low_confidence_threshold: float = 0.75

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    pdf_dpi: int = 150
    ocr_prefer: str = "rapid"
    bypass_native_pdf_ocr: bool = True

    use_vision_extraction: bool = True
    vision_provider: str = "groq"
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    gemini_api_key: str = ""

    google_service_account_json: str = "./credentials/service_account.json"
    google_sheet_id: str = ""
    sheets_mode: str = "flat"
    
    google_client_id: str = ""
    google_client_secret: str = ""

    excel_export_dir: str = "./storage/exports"

    export_webhook_url: str = ""

    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"
    imap_mark_seen: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# Resolve relative paths to absolute paths based on project root
def _resolve_path(path_str: str) -> str:
    p = Path(path_str)
    if p.is_absolute():
        return str(p)
    return str(PROJECT_ROOT / p)


# Ensure all path settings are resolved to absolute paths
settings.storage_dir = _resolve_path(settings.storage_dir)
settings.excel_export_dir = _resolve_path(settings.excel_export_dir)
settings.google_service_account_json = _resolve_path(settings.google_service_account_json)

os.makedirs(settings.storage_dir, exist_ok=True)
os.makedirs(settings.excel_export_dir, exist_ok=True)
os.makedirs(os.path.dirname(settings.database_url.replace("sqlite:///", "")) or ".", exist_ok=True)
