"""Trivial API-key auth: a single static token shared by Unity client and
this server. The tool is local and personal, so we don't need OAuth or JWT.

The key is sent as the HTTP header `X-API-Key`. The /health and /docs
endpoints stay public so we can confirm the server is up without a key.
"""
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import get_settings


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    expected = get_settings().coach_api_key
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


ApiKeyAuth = Depends(require_api_key)
