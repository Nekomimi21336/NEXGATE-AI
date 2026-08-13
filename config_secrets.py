from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

SYSTEM_CONFIG_FILE = Path(__file__).parent / "data" / "system_config.json"

SENSITIVE_FILE_FIELDS = (
    ("paypal", "client_secret", ("PAYPAL_CLIENT_SECRET",)),
    ("paypal", "client_id", ("PAYPAL_CLIENT_ID",)),
    ("search_engines", "tavily_api_key", ("TAVILY_API_KEY",)),
    ("search_engines", "serper_api_key", ("SERPER_API_KEY",)),
    ("mail_server", "password", ("SMTP_PASSWORD",)),
    ("google_oauth", "client_secret", ("GOOGLE_CLIENT_SECRET",)),
    ("discord_oauth", "client_secret", ("DISCORD_CLIENT_SECRET",)),
)


def resolve_secret(env_keys, file_value=""):
    for key in env_keys:
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return str(file_value or "").strip()


def env_overrides_file(env_keys, file_value="") -> bool:
    for key in env_keys:
        if (os.getenv(key) or "").strip():
            return True
    return not str(file_value or "").strip()


def log_secret_hygiene_warnings():
    if not SYSTEM_CONFIG_FILE.is_file():
        return
    try:
        import json

        with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        logger.warning("system_config.json を読み取れませんでした（シークレット診断をスキップ）")
        return

    exposed = []
    for section, field, env_keys in SENSITIVE_FILE_FIELDS:
        block = data.get(section) or {}
        file_val = str(block.get(field) or "").strip()
        if file_val and not env_overrides_file(env_keys, file_val):
            exposed.append(f"{section}.{field}")

    try:
        from image_generation_registry import IMAGE_PROVIDERS
        from model_registry import PROVIDERS
    except Exception:
        PROVIDERS = {}
        IMAGE_PROVIDERS = {}
    providers = data.get("providers") or {}
    if isinstance(providers, dict):
        for pid, meta in {**PROVIDERS, **IMAGE_PROVIDERS}.items():
            pent = providers.get(pid) or {}
            file_val = str(pent.get("api_key") or "").strip()
            env_keys = (meta.get("api_key_env"),)
            if file_val and not env_overrides_file(env_keys, file_val):
                exposed.append(f"providers.{pid}.api_key")

    if exposed:
        logger.warning(
            "機密情報が system_config.json に平文で保存されています。"
            "環境変数へ移行してください: %s",
            ", ".join(exposed),
        )
