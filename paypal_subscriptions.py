import json
import os
import urllib.parse
from datetime import datetime
from pathlib import Path

from paypal_billing import (
    SUBSCRIPTION_PLAN_IDS,
    _paypal_request,
    get_access_token,
    get_paypal_plan_api_ids,
    get_plan_subscription_urls,
    paypal_configured,
)

WEBHOOK_LOG_FILE = Path(__file__).parent / "data" / "paypal_webhook_log.json"
SYSTEM_CONFIG_FILE = Path(__file__).parent / "data" / "system_config.json"
MAX_WEBHOOK_LOG = 3000

ACTIVATION_EVENTS = frozenset(
    {
        "BILLING.SUBSCRIPTION.ACTIVATED",
        "BILLING.SUBSCRIPTION.RE-ACTIVATED",
    }
)
DEACTIVATION_EVENTS = frozenset(
    {
        "BILLING.SUBSCRIPTION.CANCELLED",
        "BILLING.SUBSCRIPTION.SUSPENDED",
        "BILLING.SUBSCRIPTION.EXPIRED",
    }
)


def get_paypal_webhook_id():
    from config_secrets import resolve_secret

    webhook_id = ""
    if SYSTEM_CONFIG_FILE.exists():
        with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        paypal = data.get("paypal") or {}
        webhook_id = (paypal.get("webhook_id") or "").strip()
    return resolve_secret(("PAYPAL_WEBHOOK_ID",), webhook_id)


def billing_plan_id_for_nexgate_plan(nexgate_plan_id):
    plan_id = (nexgate_plan_id or "").strip().lower()
    if plan_id not in SUBSCRIPTION_PLAN_IDS:
        return ""
    api = get_paypal_plan_api_ids().get(plan_id) or {}
    billing = (api.get("billing_plan_id") or "").strip()
    if billing:
        return billing
    url = (get_plan_subscription_urls().get(plan_id) or "").strip()
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    values = urllib.parse.parse_qs(parsed.query).get("plan_id") or []
    return (values[0] or "").strip() if values else ""


def nexgate_plan_from_billing_plan_id(billing_plan_id):
    target = (billing_plan_id or "").strip()
    if not target:
        return ""
    for plan_id, entry in get_paypal_plan_api_ids().items():
        if (entry.get("billing_plan_id") or "").strip() == target:
            return plan_id
    for plan_id in SUBSCRIPTION_PLAN_IDS:
        url = (get_plan_subscription_urls().get(plan_id) or "").strip()
        if not url:
            continue
        parsed = urllib.parse.urlparse(url)
        values = urllib.parse.parse_qs(parsed.query).get("plan_id") or []
        if values and values[0].strip() == target:
            return plan_id
    return ""


def _load_webhook_log():
    if not WEBHOOK_LOG_FILE.exists():
        return []
    try:
        with open(WEBHOOK_LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        ids = data.get("event_ids")
        return list(ids) if isinstance(ids, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_webhook_log(event_ids):
    WEBHOOK_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    trimmed = event_ids[-MAX_WEBHOOK_LOG:]
    with open(WEBHOOK_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump({"event_ids": trimmed}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def webhook_event_seen(event_id):
    event_id = (event_id or "").strip()
    if not event_id:
        return False
    return event_id in _load_webhook_log()


def mark_webhook_event_seen(event_id):
    event_id = (event_id or "").strip()
    if not event_id:
        return
    ids = _load_webhook_log()
    if event_id in ids:
        return
    ids.append(event_id)
    _save_webhook_log(ids)


def verify_webhook_signature(headers, event_body):
    webhook_id = get_paypal_webhook_id()
    if not webhook_id:
        return False, "PayPal Webhook ID が未設定です（PAYPAL_WEBHOOK_ID または管理画面）"

    if not paypal_configured():
        return False, "PayPal API 認証が未設定です"

    transmission_id = (headers.get("Paypal-Transmission-Id") or headers.get("PAYPAL-TRANSMISSION-ID") or "").strip()
    transmission_time = (headers.get("Paypal-Transmission-Time") or headers.get("PAYPAL-TRANSMISSION-TIME") or "").strip()
    transmission_sig = (headers.get("Paypal-Transmission-Sig") or headers.get("PAYPAL-TRANSMISSION-SIG") or "").strip()
    cert_url = (headers.get("Paypal-Cert-Url") or headers.get("PAYPAL-CERT-URL") or "").strip()
    auth_algo = (headers.get("Paypal-Auth-Algo") or headers.get("PAYPAL-AUTH-ALGO") or "").strip()

    if not all([transmission_id, transmission_time, transmission_sig, cert_url, auth_algo]):
        return False, "PayPal Webhook ヘッダーが不足しています"

    token = get_access_token()
    payload = {
        "auth_algo": auth_algo,
        "cert_url": cert_url,
        "transmission_id": transmission_id,
        "transmission_sig": transmission_sig,
        "transmission_time": transmission_time,
        "webhook_id": webhook_id,
        "webhook_event": event_body,
    }
    result = _paypal_request(
        "POST",
        "/v1/notifications/verify-webhook-signature",
        payload,
        token,
    )
    status = (result.get("verification_status") or "").upper()
    if status == "SUCCESS":
        return True, None
    return False, f"Webhook 署名検証に失敗しました（{status or '不明'}）"


def _subscription_approve_url(subscription_data):
    for link in subscription_data.get("links") or []:
        if (link.get("rel") or "").lower() == "approve":
            return (link.get("href") or "").strip()
    return ""


def create_billing_subscription(username, email, nexgate_plan_id, return_url, cancel_url):
    if not paypal_configured():
        return None, "PayPalが設定されていません（管理者にお問い合わせください）"

    username = (username or "").strip().lower()[:127]
    if not username:
        return None, "ユーザー名が不正です"

    plan_key = (nexgate_plan_id or "").strip().lower()
    if plan_key not in SUBSCRIPTION_PLAN_IDS:
        return None, "プランが不正です"

    billing_plan_id = billing_plan_id_for_nexgate_plan(plan_key)
    if not billing_plan_id:
        return None, "PayPal 請求プラン ID が未設定です（管理画面でプランを作成/同期してください）"

    token = get_access_token()
    subscriber = {}
    email = (email or "").strip()
    if email:
        subscriber["email_address"] = email[:254]

    payload = {
        "plan_id": billing_plan_id,
        "custom_id": username,
        "application_context": {
            "brand_name": "NEXGATE AI",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "SUBSCRIBE_NOW",
            "return_url": (return_url or "").strip()[:4000],
            "cancel_url": (cancel_url or "").strip()[:4000],
        },
    }
    if subscriber:
        payload["subscriber"] = subscriber

    result = _paypal_request(
        "POST",
        "/v1/billing/subscriptions",
        payload,
        token,
        request_id=True,
    )
    subscription_id = (result.get("id") or "").strip()
    approve_url = _subscription_approve_url(result)
    if not subscription_id or not approve_url:
        return None, "PayPal サブスクリプションの作成に失敗しました"

    return {
        "subscription_id": subscription_id,
        "approve_url": approve_url,
        "billing_plan_id": billing_plan_id,
        "nexgate_plan_id": plan_key,
    }, None


def get_billing_subscription(subscription_id):
    subscription_id = (subscription_id or "").strip()
    if not subscription_id:
        return None, "サブスクリプション ID が不正です"
    if not paypal_configured():
        return None, "PayPalが設定されていません"
    token = get_access_token()
    result = _paypal_request(
        "GET",
        f"/v1/billing/subscriptions/{subscription_id}",
        None,
        token,
    )
    return result, None


def parse_subscription_resource(resource):
    if not isinstance(resource, dict):
        return {}
    plan = resource.get("plan_id")
    if isinstance(plan, dict):
        billing_plan_id = (plan.get("id") or "").strip()
    else:
        billing_plan_id = (plan or "").strip()
    subscriber = resource.get("subscriber") or {}
    if not isinstance(subscriber, dict):
        subscriber = {}
    return {
        "subscription_id": (resource.get("id") or "").strip(),
        "status": (resource.get("status") or "").strip().upper(),
        "custom_id": (resource.get("custom_id") or "").strip().lower(),
        "billing_plan_id": billing_plan_id,
        "nexgate_plan_id": nexgate_plan_from_billing_plan_id(billing_plan_id),
        "subscriber_email": (subscriber.get("email_address") or "").strip().lower(),
    }


def subscription_event_action(event_type, resource_status):
    status = (resource_status or "").upper()
    if event_type in DEACTIVATION_EVENTS:
        return "deactivate"
    if event_type in ACTIVATION_EVENTS:
        return "activate"
    if status == "ACTIVE":
        return "activate"
    if status in ("CANCELLED", "SUSPENDED", "EXPIRED"):
        return "deactivate"
    return None
