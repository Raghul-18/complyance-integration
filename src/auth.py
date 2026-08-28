"""
API key authentication.
"""
import hmac

from fastapi import Header, HTTPException, status

from src.config import settings

GENERIC_AUTH_MESSAGE = "Missing or invalid API key."


def require_api_key(x_api_key: str = Header(default=None, alias="X-API-Key")) -> None:
    expected = settings.require_api_key()
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": GENERIC_AUTH_MESSAGE},
        )
