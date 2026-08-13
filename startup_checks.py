from __future__ import annotations

import logging
from pathlib import Path

from config_secrets import log_secret_hygiene_warnings
from mail_server import mail_server_configured, resolve_mail_server_config
from paypal_billing import get_paypal_credentials, paypal_configured
from paypal_subscriptions import get_paypal_webhook_id

logger = logging.getLogger(__name__)

SYSTEM_CONFIG_FILE = Path(__file__).parent / "data" / "system_config.json"


def run_startup_checks(config=None):
    log_secret_hygiene_warnings()

    if config is None:
        from json_store import read_json

        config = read_json(SYSTEM_CONFIG_FILE, default={}) or {}

    mail_cfg = resolve_mail_server_config(config.get("mail_server"))
    if mail_server_configured(mail_cfg):
        if not mail_cfg.get("verification_required", True):
            logger.warning(
                "SMTPは設定済みですが verification_required=false です。"
                "不正登録防止のため管理画面でメール確認を有効化してください。"
            )
    elif mail_cfg.get("host") and not mail_cfg.get("enabled"):
        logger.warning(
            "SMTPホストは設定されていますが mail_server.enabled=false です。"
            "メール確認を使う場合は有効化してください。"
        )

    creds = get_paypal_credentials()
    if paypal_configured() and creds.get("mode") == "live":
        if not get_paypal_webhook_id():
            logger.warning(
                "PayPal live モードですが webhook_id / PAYPAL_WEBHOOK_ID が未設定です。"
                "サブスク状態の自動同期ができません。"
            )
