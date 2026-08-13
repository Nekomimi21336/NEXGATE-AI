from __future__ import annotations

import json
import logging
import os
import secrets
import smtplib
import socket
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)

PENDING_FILE = Path(__file__).parent / "data" / "pending_email_verifications.json"
VERIFICATION_TTL_HOURS = 24

DEFAULT_MAIL_SERVER = {
    "enabled": False,
    "verification_required": True,
    "host": "",
    "port": 587,
    "use_tls": True,
    "use_ssl": False,
    "username": "",
    "password": "",
    "from_email": "",
    "from_name": "NEXGATE AI",
}


def normalize_mail_server(raw):
    src = raw if isinstance(raw, dict) else {}
    port = src.get("port", 587)
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 587
    if port < 1 or port > 65535:
        port = 587
    use_ssl = bool(src.get("use_ssl"))
    use_tls = bool(src.get("use_tls", True))
    if port == 465:
        use_ssl = True
        use_tls = False
    elif port == 587 and use_ssl:
        use_ssl = False
        use_tls = True
    if use_ssl:
        use_tls = False
    return {
        "enabled": bool(src.get("enabled")),
        "verification_required": bool(src.get("verification_required", True)),
        "host": str(src.get("host") or "").strip(),
        "port": port,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "username": str(src.get("username") or "").strip(),
        "password": str(src.get("password") or "").strip(),
        "from_email": str(src.get("from_email") or "").strip(),
        "from_name": str(src.get("from_name") or "NEXGATE AI").strip() or "NEXGATE AI",
    }


def _env_mail_fallback():
    host = (os.getenv("SMTP_HOST") or "").strip()
    if not host:
        return {}
    port_raw = (os.getenv("SMTP_PORT") or "587").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    use_ssl = (os.getenv("SMTP_USE_SSL") or "").strip().lower() in ("1", "true", "yes")
    use_tls = (os.getenv("SMTP_USE_TLS") or "true").strip().lower() in ("1", "true", "yes")
    if use_ssl:
        use_tls = False
    return {
        "enabled": True,
        "host": host,
        "port": port,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "username": (os.getenv("SMTP_USERNAME") or "").strip(),
        "password": (os.getenv("SMTP_PASSWORD") or "").strip(),
        "from_email": (os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_USERNAME") or "").strip(),
        "from_name": (os.getenv("SMTP_FROM_NAME") or "NEXGATE AI").strip(),
    }


def resolve_mail_server_config(stored=None):
    from config_secrets import resolve_secret

    cfg = normalize_mail_server(stored or {})
    if not cfg.get("host"):
        env = _env_mail_fallback()
        if env.get("host"):
            merged = dict(cfg)
            for key, value in env.items():
                if key == "enabled":
                    merged["enabled"] = bool(cfg.get("enabled")) or bool(value)
                elif value not in ("", None):
                    merged[key] = value
            cfg = normalize_mail_server(merged)
    if cfg.get("password"):
        cfg = dict(cfg)
        cfg["password"] = resolve_secret(
            ("SMTP_PASSWORD",),
            cfg.get("password") or "",
        )
    return cfg


def mail_server_configured(cfg=None):
    cfg = resolve_mail_server_config(cfg)
    if not cfg.get("enabled"):
        return False
    if not cfg.get("host") or not cfg.get("from_email"):
        return False
    if cfg.get("username") and not cfg.get("password"):
        return False
    return True


def email_verification_required(stored=None):
    cfg = resolve_mail_server_config(stored)
    return (
        bool(cfg.get("enabled"))
        and bool(cfg.get("verification_required"))
        and mail_server_configured(cfg)
    )


def serialize_mail_server_admin(stored=None):
    cfg = resolve_mail_server_config(stored)
    env = _env_mail_fallback()
    env_fallback = bool(not (stored or {}).get("host") and env.get("host"))
    return {
        "enabled": bool(cfg.get("enabled")),
        "verification_required": bool(cfg.get("verification_required")),
        "host": cfg.get("host") or "",
        "port": cfg.get("port") or 587,
        "use_tls": bool(cfg.get("use_tls")),
        "use_ssl": bool(cfg.get("use_ssl")),
        "username": cfg.get("username") or "",
        "from_email": cfg.get("from_email") or "",
        "from_name": cfg.get("from_name") or "NEXGATE AI",
        "password_set": bool((stored or {}).get("password") or env.get("password")),
        "configured": mail_server_configured(cfg),
        "verification_active": email_verification_required(stored),
        "env_fallback": env_fallback,
    }


def _load_pending():
    from json_store import read_json

    data = read_json(PENDING_FILE, default={})
    return data if isinstance(data, dict) else {}


def _save_pending(data):
    from json_store import write_json

    write_json(PENDING_FILE, data)


def _prune_pending(data):
    now = datetime.now()
    kept = {}
    for token, entry in (data or {}).items():
        if not isinstance(entry, dict):
            continue
        expires_raw = (entry.get("expires_at") or "").strip()
        try:
            expires = datetime.fromisoformat(expires_raw)
        except ValueError:
            continue
        if expires > now:
            kept[token] = entry
    return kept


def _remove_pending_for_identity(data, *, username="", email=""):
    username_key = (username or "").strip().lower()
    email_key = (email or "").strip().lower()
    if not username_key and not email_key:
        return data
    kept = {}
    for token, entry in (data or {}).items():
        if not isinstance(entry, dict):
            continue
        if username_key and (entry.get("username") or "").strip().lower() == username_key:
            continue
        if email_key and (entry.get("email") or "").strip().lower() == email_key:
            continue
        kept[token] = entry
    return kept


def create_pending_email_registration(
    *,
    username,
    password,
    display_name,
    email,
    phone="",
    billing=None,
):
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires = now + timedelta(hours=VERIFICATION_TTL_HOURS)
    data = _prune_pending(_load_pending())
    data = _remove_pending_for_identity(
        data, username=username, email=email
    )
    data[token] = {
        "username": (username or "").strip().lower(),
        "password_hash": generate_password_hash(password),
        "display_name": (display_name or "").strip(),
        "email": (email or "").strip().lower(),
        "phone": (phone or "").strip(),
        "billing": billing if isinstance(billing, dict) else {},
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": expires.isoformat(timespec="seconds"),
    }
    _save_pending(data)
    return token


def get_pending_email_registration(token):
    key = (token or "").strip()
    if not key:
        return None
    data = _prune_pending(_load_pending())
    if data != _load_pending():
        _save_pending(data)
    entry = data.get(key)
    if not isinstance(entry, dict):
        return None
    expires_raw = (entry.get("expires_at") or "").strip()
    try:
        expires = datetime.fromisoformat(expires_raw)
    except ValueError:
        return None
    if expires <= datetime.now():
        data.pop(key, None)
        _save_pending(data)
        return None
    return dict(entry)


def consume_pending_email_registration(token):
    key = (token or "").strip()
    if not key:
        return None, "認証リンクが無効です"
    data = _prune_pending(_load_pending())
    entry = data.pop(key, None)
    _save_pending(data)
    if not isinstance(entry, dict):
        return None, "認証リンクが無効または期限切れです"
    expires_raw = (entry.get("expires_at") or "").strip()
    try:
        expires = datetime.fromisoformat(expires_raw)
    except ValueError:
        return None, "認証リンクが無効です"
    if expires <= datetime.now():
        return None, "認証リンクの有効期限が切れています"
    return entry, None


def _smtp_local_hostname():
    try:
        name = socket.getfqdn()
        return name if name and name != "localhost" else "localhost"
    except OSError:
        return "localhost"


def _format_smtp_error(exc, *, host, port, use_ssl, use_tls):
    message = str(exc).strip() or exc.__class__.__name__
    lower = message.lower()
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in lower:
        mode = "SMTPS (SSL)" if use_ssl else ("STARTTLS" if use_tls else "平文")
        return (
            f"SMTPサーバー ({host}:{port}, {mode}) に接続できませんでした。"
            " ホスト名・ポート・暗号化設定（465=SSL / 587=STARTTLS）と、"
            "サーバーからの SMTP 送信許可（ファイアウォール）を確認してください。"
        )
    if "connection refused" in lower:
        return f"SMTPサーバー ({host}:{port}) が接続を拒否しました。ポート番号を確認してください。"
    if "authentication" in lower or "535" in lower or "534" in lower:
        return "SMTP認証に失敗しました。ユーザー名とパスワードを確認してください。"
    if "certificate" in lower or "ssl" in lower:
        return f"SMTPの暗号化接続に失敗しました。ポート {port} に合わせて SSL / STARTTLS 設定を見直してください。"
    return message or "メールの送信に失敗しました"


def _probe_smtp_socket(host, port, timeout=8):
    last_error = None
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            with socket.create_connection((host, port), timeout=timeout, source_address=None):
                return None
        except OSError as exc:
            last_error = exc
    return last_error


def _open_smtp_connection(*, host, port, use_ssl, use_tls, timeout=30):
    local_hostname = _smtp_local_hostname()
    probe_error = _probe_smtp_socket(host, port, timeout=min(timeout, 8))
    if probe_error is not None:
        raise probe_error
    if use_ssl:
        return smtplib.SMTP_SSL(
            host,
            port,
            timeout=timeout,
            local_hostname=local_hostname,
        )
    smtp = smtplib.SMTP(timeout=timeout, local_hostname=local_hostname)
    smtp.connect(host, port)
    if use_tls:
        smtp.starttls()
    return smtp


def send_email(*, cfg, to_email, subject, body_text, body_html=None):
    cfg = resolve_mail_server_config(cfg)
    if not mail_server_configured(cfg):
        return False, "メールサーバーが設定されていません"

    recipient = (to_email or "").strip()
    if not recipient:
        return False, "送信先メールアドレスが不正です"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((cfg["from_name"], cfg["from_email"]))
    message["To"] = recipient
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype="html")

    host = cfg["host"]
    port = int(cfg.get("port") or 587)
    username = cfg.get("username") or ""
    password = cfg.get("password") or ""
    use_ssl = bool(cfg.get("use_ssl"))
    use_tls = bool(cfg.get("use_tls"))

    smtp = None
    try:
        smtp = _open_smtp_connection(
            host=host,
            port=port,
            use_ssl=use_ssl,
            use_tls=use_tls,
        )
        if username:
            smtp.login(username, password)
        smtp.send_message(message)
        return True, None
    except Exception as exc:
        logger.exception("SMTP send failed")
        return False, _format_smtp_error(
            exc,
            host=host,
            port=port,
            use_ssl=use_ssl,
            use_tls=use_tls,
        )
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                try:
                    smtp.close()
                except Exception:
                    pass


def build_verification_email(verify_url, display_name=""):
    name = (display_name or "").strip() or "ユーザー"
    subject = "NEXGATE AI — メールアドレスの確認"
    text = (
        f"{name} 様\n\n"
        "NEXGATE AI へのアカウント登録ありがとうございます。\n"
        "以下のリンクを開いて、メールアドレスの確認を完了してください。\n\n"
        f"{verify_url}\n\n"
        f"このリンクは {VERIFICATION_TTL_HOURS} 時間有効です。\n"
        "心当たりがない場合は、このメールを無視してください。\n"
    )
    html = (
        f"<p>{name} 様</p>"
        "<p>NEXGATE AI へのアカウント登録ありがとうございます。</p>"
        "<p>以下のボタンをクリックして、メールアドレスの確認を完了してください。</p>"
        f'<p><a href="{verify_url}">メールアドレスを確認する</a></p>'
        f"<p>このリンクは {VERIFICATION_TTL_HOURS} 時間有効です。</p>"
        "<p>心当たりがない場合は、このメールを無視してください。</p>"
    )
    return subject, text, html


def send_verification_email(*, cfg, to_email, verify_url, display_name=""):
    subject, text, html = build_verification_email(verify_url, display_name)
    return send_email(
        cfg=cfg,
        to_email=to_email,
        subject=subject,
        body_text=text,
        body_html=html,
    )
