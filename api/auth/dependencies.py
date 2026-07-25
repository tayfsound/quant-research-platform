"""Kimlik doğrulama bağımlılıkları."""
import os

from fastapi import Header, HTTPException


async def verify_api_key(x_api_key: str = Header(None)):
    """API anahtarını doğrula. Üretim ortamında test-key kullanılmamalı."""
    expected = os.getenv("API_KEY", "test-key")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {"user": "authenticated"}
