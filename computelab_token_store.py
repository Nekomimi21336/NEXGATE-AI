import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

COMPUTELAB_TOKENS_FILE = Path(__file__).parent / "data" / "computelab_tokens.json"


def _fernet():
    secret = (
        os.getenv("COMPUTELAB_TOKEN_ENCRYPTION_KEY")
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


def load_computelab_tokens():
    if not COMPUTELAB_TOKENS_FILE.exists():
        return {}
    with open(COMPUTELAB_TOKENS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_computelab_tokens(store):
    COMPUTELAB_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COMPUTELAB_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def get_api_key(username):
    username = (username or "").strip().lower()
    if not username:
        return ""
    raw = load_computelab_tokens().get(username)
    if not isinstance(raw, dict):
        return ""
    return _decrypt(raw.get("api_key_enc", ""))


def set_api_key(username, api_key):
    username = (username or "").strip().lower()
    key = (api_key or "").strip()
    store = load_computelab_tokens()
    if not key:
        if username in store:
            del store[username]
        save_computelab_tokens(store)
        return
    prefix = key[:16] + "…" if len(key) > 16 else key[:8] + "…"
    store[username] = {
        "api_key_enc": _encrypt(key),
        "key_prefix": prefix,
    }
    save_computelab_tokens(store)


def get_key_prefix(username):
    username = (username or "").strip().lower()
    if not username:
        return ""
    raw = load_computelab_tokens().get(username)
    if not isinstance(raw, dict):
        return ""
    return (raw.get("key_prefix") or "").strip()


def delete_api_key(username):
    set_api_key(username, "")


def has_api_key(username):
    return bool(get_api_key(username))
