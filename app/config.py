import os
from pydantic_settings import BaseSettings


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

os.makedirs(settings.storage_dir, exist_ok=True)
os.makedirs(settings.excel_export_dir, exist_ok=True)
os.makedirs(os.path.dirname(settings.database_url.replace("sqlite:///", "")) or ".", exist_ok=True)
