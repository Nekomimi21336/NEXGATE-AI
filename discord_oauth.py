import json
import os
from pathlib import Path
from urllib.parse import urlencode

import requests

SYSTEM_CONFIG_FILE = Path(__file__).parent / "data" / "system_config.json"

DISCORD_SCOPES = ["identify", "email"]

AUTH_URI = "https://discord.com/api/oauth2/authorize"
TOKEN_URI = "https://discord.com/api/oauth2/token"
USERINFO_URI = "https://discord.com/api/users/@me"

DEFAULT_REDIRECT_URI = "http://localhost:5000/api/auth/discord/callback"

OAUTH_MODE_LOGIN = "login"
OAUTH_MODE_LINK = "link"


def _load_stored_discord_oauth():
    if not SYSTEM_CONFIG_FILE.exists():
        return {}
    with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("discord_oauth")
    return raw if isinstance(raw, dict) else {}


def get_discord_oauth_scopes():
    return list(DISCORD_SCOPES)


def get_redirect_uri():
    stored = _load_stored_discord_oauth()
    return (
        (stored.get("redirect_uri") or "").strip()
        or os.getenv("DISCORD_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()
        or DEFAULT_REDIRECT_URI
    )


def get_oauth_client_config():
    stored = _load_stored_discord_oauth()
    client_id = (
        os.getenv("DISCORD_CLIENT_ID", "").strip()
        or (stored.get("client_id") or "").strip()
    )
    client_secret = (
        os.getenv("DISCORD_CLIENT_SECRET", "").strip()
        or (stored.get("client_secret") or "").strip()
    )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": get_redirect_uri(),
    }


def discord_oauth_configured():
    cfg = get_oauth_client_config()
    return bool(cfg["client_id"] and cfg["client_secret"])


def build_authorization_url(state):
    cfg = get_oauth_client_config()
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": " ".join(get_discord_oauth_scopes()),
        "state": state,
        "prompt": "consent",
    }
    return f"{AUTH_URI}?{urlencode(params)}"


def exchange_code_for_tokens(code):
    cfg = get_oauth_client_config()
    resp = requests.post(
        TOKEN_URI,
        data={
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": cfg["redirect_uri"],
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise RuntimeError(f"Discord token exchange failed: {detail}")
    return resp.json()


def fetch_discord_userinfo(access_token):
    resp = requests.get(
        USERINFO_URI,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise RuntimeError(f"Discord userinfo failed: {detail}")
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("Discord userinfo returned invalid payload")
    return data
