import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Security(_header_scheme)) -> str:
    """
    Validate the X-API-Key header against the API_KEY environment variable.
    Raises 401 if the header is absent, 403 if the key is wrong.
    """
    expected = os.environ.get("API_KEY", "")
    if not expected:
        raise RuntimeError("API_KEY environment variable not set")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
