"""
Runtime configuration, read entirely from environment variables.
"""

import os


class Settings:
    def __init__(self) -> None:
        self.api_key: str = os.environ.get("TRAINING_API_KEY", "")
        self.db_path: str = os.environ.get("DB_PATH", "invoices.db")
        # How long a document sits in PROCESSING before the background
        # "decision" flips it to ACCEPTED/REJECTED. A stand-in for a real
        # downstream call (see docs/discovery-and-design.md).
        self.processing_delay_seconds: float = float(
            os.environ.get("PROCESSING_DELAY_SECONDS", "2")
        )

    def require_api_key(self) -> str:
        if not self.api_key:
            raise RuntimeError(
                "TRAINING_API_KEY is not set. Copy .env.example to .env, "
                "fill in a value, and load it before starting the app."
            )
        return self.api_key


settings = Settings()
