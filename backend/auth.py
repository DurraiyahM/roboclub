"""Simple token auth for demo / ops use."""
import hashlib
import os
import secrets
from typing import Any, Dict, Optional

import database as db

_TOKEN_SECRET = os.getenv("AUTH_SECRET", "roboclub-dev-change-in-production")


def hash_password(password: str) -> str:
    return hashlib.sha256(f"{_TOKEN_SECRET}:{password}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def create_token(user_id: int, role: str) -> str:
    nonce = secrets.token_hex(8)
    raw = f"{user_id}:{role}:{nonce}"
    sig = hashlib.sha256(f"{_TOKEN_SECRET}:{raw}".encode()).hexdigest()[:16]
    return f"{raw}:{sig}"


def parse_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return None
        user_id, role, nonce, sig = parts
        raw = f"{user_id}:{role}:{nonce}"
        expected = hashlib.sha256(f"{_TOKEN_SECRET}:{raw}".encode()).hexdigest()[:16]
        if sig != expected:
            return None
        user = db.get_user(int(user_id))
        if not user or user["role"] != role:
            return None
        return user
    except (ValueError, TypeError):
        return None
