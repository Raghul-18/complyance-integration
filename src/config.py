"""
Runtime configuration, read entirely from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()
class Settings:
    def __init__(self) -> None:
        self.api_key: str = os.environ.get("TRAINING_API_KEY", "")
        self.db_path: str = os.environ.get("DB_PATH", "invoices.db")
        self.processing_delay_seconds: float = float(
            os.environ.get("PROCESSING_DELAY_SECONDS", "2")
        )
        self.max_content_length_bytes: int = int(
            os.environ.get("MAX_CONTENT_LENGTH_BYTES", str(1 * 1024 * 1024))  # 1 MB
        )
        self.supported_source_versions = {
            v.strip() for v in os.environ.get("SUPPORTED_SOURCE_VERSIONS", "1.0").split(",") if v.strip()
        }

    def require_api_key(self) -> str:
        if not self.api_key:
            raise RuntimeError(
                "TRAINING_API_KEY is not set. Copy .env.example to .env, "
                "fill in a value, and load it before starting the app."
            )
        return self.api_key


settings = Settings()
