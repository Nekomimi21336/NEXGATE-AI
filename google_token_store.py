import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

GOOGLE_TOKENS_FILE = Path(__file__).parent / "data" / "google_tokens.json"


def _fernet():
    secret = (
        os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY")
        or os.getenv("FLASK_SECRET_KEY")
        or "nexgate-dev-secret-change-me"
    )
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _encrypt(value):
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value):
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def load_google_tokens():
    if not GOOGLE_TOKENS_FILE.exists():
        return {}
    with open(GOOGLE_TOKENS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_google_tokens(store):
    GOOGLE_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(GOOGLE_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def get_token_record(username):
    username = (username or "").strip().lower()
    if not username:
        return None
    raw = load_google_tokens().get(username)
    if not isinstance(raw, dict):
        return None
    return {
        "access_token": _decrypt(raw.get("access_token_enc", "")),
        "refresh_token": _decrypt(raw.get("refresh_token_enc", "")),
        "expiry": raw.get("expiry", ""),
        "scopes": raw.get("scopes") or [],
    }


def set_token_record(username, access_token, refresh_token, expiry, scopes):
    username = (username or "").strip().lower()
    store = load_google_tokens()
    store[username] = {
        "access_token_enc": _encrypt(access_token or ""),
        "refresh_token_enc": _encrypt(refresh_token or ""),
        "expiry": expiry or "",
        "scopes": list(scopes or []),
    }
    save_google_tokens(store)


def delete_token_record(username):
    username = (username or "").strip().lower()
    store = load_google_tokens()
    if username in store:
        del store[username]
        save_google_tokens(store)


def has_token_record(username):
    rec = get_token_record(username)
    return bool(rec and rec.get("refresh_token"))
