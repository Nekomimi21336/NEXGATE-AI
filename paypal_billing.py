import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path

BALANCE_CURRENCY = "JPY"
MIN_TOPUP_JPY = 500
SYSTEM_CONFIG_FILE = Path(__file__).parent / "data" / "system_config.json"

PLAN_SUBSCRIPTION_URL_ENV = {
    "plus": "PAYPAL_PLAN_PLUS_URL",
    "pro": "PAYPAL_PLAN_PRO_URL",
    "pro_plus": "PAYPAL_PLAN_PRO_PLUS_URL",
    "max": "PAYPAL_PLAN_MAX_URL",
}

SUBSCRIPTION_PLAN_IDS = tuple(PLAN_SUBSCRIPTION_URL_ENV.keys())

_token_cache = {"value": None, "expires_at": None}


def clear_token_cache():
    _token_cache["value"] = None
    _token_cache["expires_at"] = None


def get_paypal_credentials():
    from config_secrets import resolve_secret

    paypal = {}
    if SYSTEM_CONFIG_FILE.exists():
        with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        paypal = data.get("paypal") or {}
    client_id = resolve_secret(
        ("PAYPAL_CLIENT_ID",),
        paypal.get("client_id") or "",
    )
    client_secret = resolve_secret(
        ("PAYPAL_CLIENT_SECRET",),
        paypal.get("client_secret") or "",
    )
    mode = (
        (os.getenv("PAYPAL_MODE") or "").strip()
        or (paypal.get("mode") or "")
        or "sandbox"
    ).strip().lower()
    if mode not in ("sandbox", "live"):
        mode = "sandbox"
    return {"client_id": client_id, "client_secret": client_secret, "mode": mode}


def paypal_configured():
    creds = get_paypal_credentials()
    return bool(creds["client_id"] and creds["client_secret"])


def paypal_mode():
    return get_paypal_credentials()["mode"]


def paypal_api_base():
    if paypal_mode() == "live":
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def _plan_urls_from_config():
    urls = {}
    if not SYSTEM_CONFIG_FILE.exists():
        return urls
    with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    paypal = data.get("paypal") or {}
    raw = paypal.get("plan_urls") or paypal.get("plan_subscription_urls") or {}
    if not isinstance(raw, dict):
        return urls
    for plan_id in PLAN_SUBSCRIPTION_URL_ENV:
        value = (raw.get(plan_id) or "").strip()
        if value:
            urls[plan_id] = value
    return urls


def get_plan_subscription_urls():
    urls = _plan_urls_from_config()
    for plan_id, env_key in PLAN_SUBSCRIPTION_URL_ENV.items():
        if plan_id in urls:
            continue
        value = (os.getenv(env_key) or "").strip()
        if value:
            urls[plan_id] = value
    return urls


def normalize_plan_subscription_url(value):
    url = (value or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        raise ValueError("URLは http:// または https:// で始めてください")
    return url


def _load_system_config_data():
    if not SYSTEM_CONFIG_FILE.exists():
        return {}
    with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_paypal_plan_api_ids():
    data = _load_system_config_data()
    paypal = data.get("paypal") or {}
    raw = paypal.get("plan_api_ids") or {}
    if not isinstance(raw, dict):
        return {}
    result = {}
    for plan_id in SUBSCRIPTION_PLAN_IDS:
        entry = raw.get(plan_id)
        if not isinstance(entry, dict):
            continue
        product_id = (entry.get("product_id") or "").strip()
        billing_plan_id = (entry.get("billing_plan_id") or "").strip()
        if product_id and billing_plan_id:
            result[plan_id] = {
                "product_id": product_id,
                "billing_plan_id": billing_plan_id,
            }
    return result


def save_paypal_plan_api_ids(updates):
    if not SYSTEM_CONFIG_FILE.exists():
        raise FileNotFoundError("system_config.json が見つかりません")
    data = _load_system_config_data()
    paypal = dict(data.get("paypal") or {})
    stored = dict(paypal.get("plan_api_ids") or {})
    for plan_id, entry in updates.items():
        if plan_id not in SUBSCRIPTION_PLAN_IDS or not isinstance(entry, dict):
            continue
        stored[plan_id] = {
            "product_id": (entry.get("product_id") or "").strip(),
            "billing_plan_id": (entry.get("billing_plan_id") or "").strip(),
        }
    paypal["plan_api_ids"] = stored
    data["paypal"] = paypal
    with open(SYSTEM_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return get_paypal_plan_api_ids()


def paypal_checkout_host():
    if paypal_mode() == "live":
        return "www.paypal.com"
    return "www.sandbox.paypal.com"


def build_plan_subscribe_url(billing_plan_id):
    plan_id = (billing_plan_id or "").strip()
    if not plan_id:
        raise ValueError("PayPal billing plan ID が空です")
    qs = urllib.parse.urlencode({"plan_id": plan_id})
    return f"https://{paypal_checkout_host()}/webapps/billing/plans/subscribe?{qs}"


def _format_usd_amount(price_usd):
    try:
        amount = float(price_usd)
    except (TypeError, ValueError):
        raise ValueError("USD 料金が不正です") from None
    if amount <= 0:
        raise ValueError("USD 料金は 0 より大きい必要があります")
    return f"{amount:.2f}"


def create_catalog_product(access_token, name, description=""):
    payload = {
        "name": (name or "NEXGATE AI Plan")[:127],
        "description": (description or name or "")[:256],
        "type": "SERVICE",
        "category": "SOFTWARE",
    }
    result = _paypal_request(
        "POST",
        "/v1/catalogs/products",
        payload,
        access_token,
        request_id=True,
    )
    product_id = (result.get("id") or "").strip()
    if not product_id:
        raise RuntimeError("PayPal 商品（Product）の作成に失敗しました")
    return product_id


def create_billing_plan(access_token, product_id, name, description, price_usd):
    amount = _format_usd_amount(price_usd)
    payload = {
        "product_id": product_id,
        "name": (name or "Monthly Plan")[:127],
        "description": (description or name or "")[:256],
        "billing_cycles": [
            {
                "frequency": {
                    "interval_unit": "MONTH",
                    "interval_count": 1,
                },
                "tenure_type": "REGULAR",
                "sequence": 1,
                "total_cycles": 0,
                "pricing_scheme": {
                    "fixed_price": {
                        "value": amount,
                        "currency_code": "USD",
                    }
                },
            }
        ],
        "payment_preferences": {
            "auto_bill_outstanding": True,
            "setup_fee_failure_action": "CONTINUE",
            "payment_failure_threshold": 3,
        },
    }
    result = _paypal_request(
        "POST",
        "/v1/billing/plans",
        payload,
        access_token,
        request_id=True,
    )
    plan_id = (result.get("id") or "").strip()
    if not plan_id:
        raise RuntimeError("PayPal 請求プラン（Billing Plan）の作成に失敗しました")
    status = (result.get("status") or "").upper()
    if status != "ACTIVE":
        _paypal_request(
            "POST",
            f"/v1/billing/plans/{plan_id}/activate",
            {},
            access_token,
            request_id=True,
        )
    return plan_id


def deactivate_billing_plan(access_token, billing_plan_id):
    plan_id = (billing_plan_id or "").strip()
    if not plan_id:
        raise ValueError("PayPal billing plan ID が空です")
    _paypal_request(
        "POST",
        f"/v1/billing/plans/{plan_id}/deactivate",
        {},
        access_token,
        request_id=True,
    )


def deactivate_paypal_subscription_plan(billing_plan_id):
    if not paypal_configured():
        raise RuntimeError(
            "PayPal API 認証が未設定です（PayPal設定タブで Client ID / Secret を設定）"
        )
    token = get_access_token()
    deactivate_billing_plan(token, billing_plan_id)


def clear_paypal_plan_local(plan_ids):
    if not SYSTEM_CONFIG_FILE.exists():
        raise FileNotFoundError("system_config.json が見つかりません")
    ids = [pid for pid in plan_ids if pid in SUBSCRIPTION_PLAN_IDS]
    if not ids:
        return get_plan_subscription_urls(), get_paypal_plan_api_ids()
    data = _load_system_config_data()
    paypal = dict(data.get("paypal") or {})
    stored_urls = dict(paypal.get("plan_urls") or {})
    stored_api = dict(paypal.get("plan_api_ids") or {})
    for plan_id in ids:
        stored_urls[plan_id] = ""
        stored_api.pop(plan_id, None)
    paypal["plan_urls"] = stored_urls
    paypal["plan_api_ids"] = stored_api
    data["paypal"] = paypal
    with open(SYSTEM_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return get_plan_subscription_urls(), get_paypal_plan_api_ids()


def create_paypal_subscription_plan(paypal_name, description, price_usd):
    if not paypal_configured():
        raise RuntimeError(
            "PayPal API 認証が未設定です（PayPal設定タブで Client ID / Secret を設定）"
        )
    token = get_access_token()
    product_id = create_catalog_product(token, paypal_name, description)
    billing_plan_id = create_billing_plan(
        token, product_id, paypal_name, description, price_usd
    )
    subscribe_url = build_plan_subscribe_url(billing_plan_id)
    return {
        "product_id": product_id,
        "billing_plan_id": billing_plan_id,
        "subscribe_url": subscribe_url,
    }


def save_plan_subscription_urls(updates):
    if not SYSTEM_CONFIG_FILE.exists():
        raise FileNotFoundError("system_config.json が見つかりません")
    with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    paypal = dict(data.get("paypal") or {})
    stored = dict(paypal.get("plan_urls") or {})
    for plan_id in SUBSCRIPTION_PLAN_IDS:
        if plan_id not in updates:
            continue
        stored[plan_id] = normalize_plan_subscription_url(updates[plan_id])
    paypal["plan_urls"] = stored
    data["paypal"] = paypal
    with open(SYSTEM_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return get_plan_subscription_urls()


def public_config():
    creds = get_paypal_credentials()
    client_id = creds["client_id"]
    return {
        "enabled": paypal_configured(),
        "client_id": client_id if paypal_configured() else "",
        "mode": creds["mode"],
        "currency": BALANCE_CURRENCY,
        "min_topup_jpy": MIN_TOPUP_JPY,
        "plan_subscription_urls": get_plan_subscription_urls(),
    }


def _paypal_request(method, path, payload=None, access_token=None, request_id=False):
    url = f"{paypal_api_base()}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if request_id:
        headers["PayPal-Request-Id"] = str(uuid.uuid4())
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            message = parsed.get("message") or detail
        except json.JSONDecodeError:
            message = detail or str(e)
        raise RuntimeError(message) from e


def get_access_token():
    global _token_cache
    now = datetime.now()
    if _token_cache["value"] and _token_cache["expires_at"] and now < _token_cache["expires_at"]:
        return _token_cache["value"]

    creds = get_paypal_credentials()
    client_id = creds["client_id"]
    secret = creds["client_secret"]
    creds_b64 = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    url = f"{paypal_api_base()}/v1/oauth2/token"
    req = urllib.request.Request(
        url,
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {creds_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError("PayPal認証に失敗しました") from e

    token = data.get("access_token")
    if not token:
        raise RuntimeError("PayPal認証トークンを取得できませんでした")
    expires_in = int(data.get("expires_in", 3000))
    _token_cache["value"] = token
    _token_cache["expires_at"] = now + timedelta(seconds=max(expires_in - 60, 60))
    return token


def validate_topup_amount(amount_jpy):
    try:
        amount = int(amount_jpy)
    except (TypeError, ValueError):
        return None, "チャージ金額が不正です"
    if amount < MIN_TOPUP_JPY:
        return None, f"チャージ金額は{MIN_TOPUP_JPY}円以上で指定してください"
    if amount > 1_000_000:
        return None, "チャージ金額が大きすぎます"
    return amount, None


def create_checkout_order(username, amount_jpy):
    if not paypal_configured():
        return None, "PayPalが設定されていません（管理者にお問い合わせください）"

    amount, err = validate_topup_amount(amount_jpy)
    if err:
        return None, err

    token = get_access_token()
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": BALANCE_CURRENCY,
                    "value": str(amount),
                },
                "custom_id": username[:127],
                "description": f"NEXGATE AI 残高チャージ ¥{amount}",
            }
        ],
        "application_context": {
            "brand_name": "NEXGATE AI",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW",
        },
    }
    result = _paypal_request("POST", "/v2/checkout/orders", payload, token)
    order_id = result.get("id")
    if not order_id:
        return None, "PayPal注文の作成に失敗しました"
    return {"order_id": order_id, "amount_jpy": amount}, None


def _extract_capture(order_data):
    for unit in order_data.get("purchase_units") or []:
        payments = unit.get("payments") or {}
        for capture in payments.get("captures") or []:
            return capture, unit
    return None, None


def capture_checkout_order(username, order_id):
    if not paypal_configured():
        return None, "PayPalが設定されていません"

    order_id = (order_id or "").strip()
    if not order_id:
        return None, "注文IDが不正です"

    token = get_access_token()
    result = _paypal_request(
        "POST", f"/v2/checkout/orders/{order_id}/capture", {}, token
    )
    status = result.get("status")
    if status != "COMPLETED":
        return None, f"決済が完了していません（状態: {status or '不明'}）"

    capture, unit = _extract_capture(result)
    if not capture:
        return None, "決済情報の取得に失敗しました"

    if (unit.get("custom_id") or "") != username:
        return None, "決済ユーザーが一致しません"

    amount_info = capture.get("amount") or unit.get("amount") or {}
    if amount_info.get("currency_code") != BALANCE_CURRENCY:
        return None, "決済通貨が一致しません"

    try:
        paid_jpy = int(float(amount_info.get("value", 0)))
    except (TypeError, ValueError):
        return None, "決済金額が不正です"

    if paid_jpy < MIN_TOPUP_JPY:
        return None, "決済金額が不足しています"

    capture_id = capture.get("id") or order_id
    return {
        "order_id": order_id,
        "capture_id": capture_id,
        "amount_jpy": paid_jpy,
        "payer_email": (result.get("payer") or {}).get("email_address", ""),
    }, None
