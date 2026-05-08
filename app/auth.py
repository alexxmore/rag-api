from pathlib import Path

import yaml
from fastapi import Header, HTTPException, status

from app.schemas import ApiKeyConfig
from app.settings import get_settings


def load_api_keys(path: Path | None = None) -> dict[str, ApiKeyConfig]:
    settings = get_settings()
    config_path = path or settings.api_keys_file
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return {key: ApiKeyConfig(**value) for key, value in raw.get("keys", {}).items()}


API_KEYS = load_api_keys()


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> tuple[str, ApiKeyConfig]:
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key")
    return x_api_key, API_KEYS[x_api_key]
