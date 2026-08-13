import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from google_token_store import (
    delete_token_record,
    get_token_record,
    has_token_record,
    set_token_record,
)

SYSTEM_CONFIG_FILE = Path(__file__).parent / "data" / "system_config.json"

SCOPE_CALENDAR = "https://www.googleapis.com/auth/calendar.events"
SCOPE_GMAIL = "https://www.googleapis.com/auth/gmail.modify"
SCOPE_OPENID = "openid"
SCOPE_EMAIL = "email"
SCOPE_PROFILE = "profile"

GOOGLE_SCOPES = [SCOPE_CALENDAR, SCOPE_GMAIL]
GOOGLE_LOGIN_SCOPES = [SCOPE_OPENID, SCOPE_EMAIL, SCOPE_PROFILE]

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USERINFO_URI = "https://www.googleapis.com/oauth2/v3/userinfo"

DEFAULT_REDIRECT_URI = "http://localhost:5000/api/auth/callback"

OAUTH_MODE_TOOLS = "tools"
OAUTH_MODE_LOGIN = "login"
OAUTH_MODE_LINK = "link"


class GoogleOAuthError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _load_stored_google_oauth():
    if not SYSTEM_CONFIG_FILE.exists():
        return {}
    with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("google_oauth")
    return raw if isinstance(raw, dict) else {}


def _scope_flags():
    stored = _load_stored_google_oauth()
    cal = stored.get("calendar_scopes_enabled")
    gmail = stored.get("gmail_scopes_enabled")
    if cal is None and gmail is None:
        return True, True
    return bool(cal if cal is not None else True), bool(
        gmail if gmail is not None else True
    )


def get_google_oauth_scopes():
    cal, gmail = _scope_flags()
    scopes = []
    if cal:
        scopes.append(SCOPE_CALENDAR)
    if gmail:
        scopes.append(SCOPE_GMAIL)
    return scopes if scopes else list(GOOGLE_SCOPES)


def get_google_login_scopes():
    return list(GOOGLE_LOGIN_SCOPES)


def get_redirect_uri():
    stored = _load_stored_google_oauth()
    return (
        (stored.get("redirect_uri") or "").strip()
        or os.getenv("GOOGLE_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()
        or DEFAULT_REDIRECT_URI
    )


def get_oauth_client_config():
    stored = _load_stored_google_oauth()
    client_id = (
        os.getenv("GOOGLE_CLIENT_ID", "").strip()
        or (stored.get("client_id") or "").strip()
    )
    client_secret = (
        os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        or (stored.get("client_secret") or "").strip()
    )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": get_redirect_uri(),
    }


def google_oauth_configured():
    cfg = get_oauth_client_config()
    return bool(cfg["client_id"] and cfg["client_secret"])


def user_google_connected(username):
    return has_token_record(username)


def _build_authorization_url(state, scopes, *, prompt="consent"):
    cfg = get_oauth_client_config()
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": prompt,
        "state": state,
    }
    return f"{AUTH_URI}?{urlencode(params)}"


def build_authorization_url(state):
    return _build_authorization_url(state, get_google_oauth_scopes(), prompt="consent")


def build_login_authorization_url(state):
    return _build_authorization_url(state, get_google_login_scopes(), prompt="select_account")


def exchange_code_for_tokens(code):
    cfg = get_oauth_client_config()
    redirect_uri = cfg["redirect_uri"]
    resp = requests.post(
        TOKEN_URI,
        data={
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        code_err = "token_exchange_failed"
        try:
            data = resp.json()
            err = (data.get("error") or "").strip()
            if err:
                code_err = err
        except (ValueError, json.JSONDecodeError):
            pass
        logger.warning(
            "Google token exchange failed (%s) redirect_uri=%s body=%s",
            code_err,
            redirect_uri,
            resp.text[:500],
        )
        raise GoogleOAuthError(code_err)
    return resp.json()


def fetch_google_userinfo(access_token):
    resp = requests.get(
        USERINFO_URI,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise RuntimeError(f"Google userinfo failed: {detail}")
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("Google userinfo returned invalid payload")
    return data


def _expiry_from_token_payload(payload):
    expires_in = int(payload.get("expires_in") or 3600)
    dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
    return dt.isoformat()


def store_tokens_for_user(username, payload):
    refresh = (payload.get("refresh_token") or "").strip()
    access = (payload.get("access_token") or "").strip()
    existing = get_token_record(username)
    if not refresh and existing:
        refresh = existing.get("refresh_token") or ""
    if not access:
        raise RuntimeError("Google did not return an access token")
    if not refresh:
        raise RuntimeError(
            "Google did not return a refresh token. Disconnect and connect again with consent."
        )
    set_token_record(
        username,
        access,
        refresh,
        _expiry_from_token_payload(payload),
        get_google_oauth_scopes(),
    )


def disconnect_user(username):
    delete_token_record(username)


def _parse_expiry(expiry_str):
    if not expiry_str:
        return None
    text = expiry_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def credentials_for_user(username):
    rec = get_token_record(username)
    if not rec or not rec.get("refresh_token"):
        return None
    cfg = get_oauth_client_config()
    creds = Credentials(
        token=rec.get("access_token") or None,
        refresh_token=rec.get("refresh_token"),
        token_uri=TOKEN_URI,
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        scopes=get_google_oauth_scopes(),
    )
    expiry = _parse_expiry(rec.get("expiry"))
    if expiry:
        creds.expiry = expiry.replace(tzinfo=None)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        set_token_record(
            username,
            creds.token,
            creds.refresh_token,
            creds.expiry.isoformat() if creds.expiry else _expiry_from_token_payload({}),
            get_google_oauth_scopes(),
        )
    return creds


def authorized_session(username):
    creds = credentials_for_user(username)
    if not creds or not creds.valid:
        creds = credentials_for_user(username)
    if not creds or not creds.token:
        raise RuntimeError("Google is not connected or token refresh failed")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {creds.token}"
    return session
