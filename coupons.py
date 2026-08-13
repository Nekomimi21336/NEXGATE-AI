import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

COUPONS_FILE = Path(__file__).parent / "data" / "coupons.json"
CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")


def format_jpy_integer(amount):
    return f"{int(round(float(amount))):,}"


def normalize_coupon_code(code):
    return re.sub(r"\s+", "", (code or "").strip().upper())


def parse_datetime_value(value):
    text = (value or "").strip()
    if not text:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return datetime.fromisoformat(f"{text}T23:59:59")
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def format_datetime_iso(dt):
    if not dt:
        return ""
    return dt.replace(microsecond=0).isoformat(timespec="seconds")


def load_coupons_store():
    if not COUPONS_FILE.exists():
        return {"coupons": []}
    with open(COUPONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    coupons = data.get("coupons")
    if not isinstance(coupons, list):
        coupons = []
    return {"coupons": coupons}


def save_coupons_store(store):
    COUPONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COUPONS_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def find_coupon(store, coupon_id=None, code=None):
    coupons = store.get("coupons") or []
    if coupon_id:
        for item in coupons:
            if item.get("id") == coupon_id:
                return item
    if code:
        key = normalize_coupon_code(code)
        for item in coupons:
            if normalize_coupon_code(item.get("code")) == key:
                return item
    return None


def coupon_used_count(coupon):
    redemptions = coupon.get("redemptions") or []
    return len(redemptions)


def serialize_coupon(coupon, plan_names=None):
    plan_names = plan_names or {}
    ctype = coupon.get("type", "balance")
    used = coupon_used_count(coupon)
    max_uses = coupon.get("max_uses")
    expires_at = coupon.get("expires_at", "")
    expires_dt = parse_datetime_value(expires_at)
    now = datetime.now()

    if ctype == "plan":
        plan_id = coupon.get("plan_id", "plus")
        hours = int(coupon.get("plan_hours") or 1)
        benefit = f"{plan_names.get(plan_id, plan_id)} を {hours} 時間"
    elif ctype == "purchase":
        discount = int(round(float(coupon.get("discount_jpy") or 0)))
        target = (coupon.get("purchase_plan_id") or "").strip().lower()
        if target:
            benefit = f"購入時 ¥{format_jpy_integer(discount)} 割引（{plan_names.get(target, target)}）"
        else:
            benefit = f"購入時 ¥{format_jpy_integer(discount)} 割引"
    else:
        benefit = f"残高 +{format_jpy_integer(coupon.get('balance_amount', 0))}"

    status = "active"
    if not coupon.get("enabled", True):
        status = "disabled"
    elif expires_dt and now > expires_dt:
        status = "expired"
    elif max_uses is not None and used >= int(max_uses):
        status = "exhausted"

    return {
        "id": coupon.get("id"),
        "code": coupon.get("code"),
        "type": ctype,
        "balance_amount": coupon.get("balance_amount"),
        "discount_jpy": coupon.get("discount_jpy"),
        "purchase_plan_id": coupon.get("purchase_plan_id"),
        "plan_id": coupon.get("plan_id"),
        "plan_hours": coupon.get("plan_hours"),
        "max_uses": max_uses,
        "used_count": used,
        "expires_at": expires_at,
        "enabled": bool(coupon.get("enabled", True)),
        "created_at": coupon.get("created_at", ""),
        "benefit_label": benefit,
        "status": status,
        "redemptions": coupon.get("redemptions") or [],
    }


def list_coupons_serialized(plan_names):
    store = load_coupons_store()
    items = [
        serialize_coupon(c, plan_names)
        for c in store.get("coupons") or []
    ]
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return items


def validate_coupon_payload(data, existing_id=None):
    code = normalize_coupon_code(data.get("code"))
    if not code or not CODE_RE.match(code):
        return None, "クーポンコードは3〜32文字の英数字（-_可）で指定してください"

    store = load_coupons_store()
    for item in store.get("coupons") or []:
        if item.get("id") != existing_id and normalize_coupon_code(item.get("code")) == code:
            return None, "このクーポンコードは既に存在します"

    ctype = (data.get("type") or "balance").strip().lower()
    if ctype not in ("balance", "plan", "purchase"):
        return None, "特典タイプが不正です"

    expires_at = (data.get("expires_at") or "").strip()
    if not expires_at:
        return None, "有効期限を指定してください"
    if not parse_datetime_value(expires_at):
        return None, "有効期限の形式が正しくありません"

    max_uses_raw = data.get("max_uses")
    max_uses = None
    if max_uses_raw is not None and str(max_uses_raw).strip() != "":
        try:
            max_uses = int(max_uses_raw)
            if max_uses < 1:
                raise ValueError
        except (TypeError, ValueError):
            return None, "利用人数上限は1以上の整数で指定してください"

    payload = {
        "code": code,
        "type": ctype,
        "expires_at": expires_at,
        "max_uses": max_uses,
        "enabled": bool(data.get("enabled", True)),
    }

    if ctype == "balance":
        try:
            amount = round(float(data.get("balance_amount", 0)), 2)
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return None, "追加残高は0より大きい数値で指定してください"
        payload["balance_amount"] = amount
        payload["plan_id"] = ""
        payload["plan_hours"] = 0
        payload["discount_jpy"] = 0
        payload["purchase_plan_id"] = ""
    elif ctype == "plan":
        plan_id = (data.get("plan_id") or "plus").strip().lower()
        try:
            hours = int(data.get("plan_hours", 1))
            if hours < 1:
                raise ValueError
        except (TypeError, ValueError):
            return None, "プラン利用時間は1時間以上の整数で指定してください"
        payload["plan_id"] = plan_id
        payload["plan_hours"] = hours
        payload["balance_amount"] = 0
        payload["discount_jpy"] = 0
        payload["purchase_plan_id"] = ""
    else:
        try:
            discount = int(round(float(data.get("discount_jpy", 0))))
            if discount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return None, "割引額は1円以上の整数で指定してください"
        purchase_plan_id = (data.get("purchase_plan_id") or "").strip().lower()
        payload["discount_jpy"] = discount
        payload["purchase_plan_id"] = purchase_plan_id
        payload["balance_amount"] = 0
        payload["plan_id"] = ""
        payload["plan_hours"] = 0

    return payload, None


def create_coupon(data):
    payload, err = validate_coupon_payload(data)
    if err:
        return None, err
    store = load_coupons_store()
    coupon = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "redemptions": [],
        **payload,
    }
    store.setdefault("coupons", []).append(coupon)
    save_coupons_store(store)
    return coupon, None


def set_coupon_enabled(coupon_id, enabled):
    store = load_coupons_store()
    coupon = find_coupon(store, coupon_id=coupon_id)
    if not coupon:
        return None, "クーポンが見つかりません"
    coupon["enabled"] = bool(enabled)
    save_coupons_store(store)
    return coupon, None


def delete_coupon(coupon_id):
    cid = (coupon_id or "").strip()
    if not cid:
        return None, "クーポンが見つかりません"
    store = load_coupons_store()
    coupons = store.get("coupons") or []
    next_coupons = [c for c in coupons if c.get("id") != cid]
    if len(next_coupons) == len(coupons):
        return None, "クーポンが見つかりません"
    store["coupons"] = next_coupons
    save_coupons_store(store)
    return {"ok": True}, None


def user_redeemed_coupon(coupon, username):
    for item in coupon.get("redemptions") or []:
        if item.get("username") == username:
            return True
    return False


def coupon_common_validation_error(coupon, username):
    if not coupon:
        return "クーポンコードが見つかりません"
    if not coupon.get("enabled", True):
        return "このクーポンは無効化されています"
    expires_dt = parse_datetime_value(coupon.get("expires_at"))
    if expires_dt and datetime.now() > expires_dt:
        return "このクーポンの有効期限が切れています"
    max_uses = coupon.get("max_uses")
    used = coupon_used_count(coupon)
    if max_uses is not None and used >= int(max_uses):
        return "このクーポンは利用上限に達しています"
    if user_redeemed_coupon(coupon, username):
        return "このクーポンは既に利用済みです"
    return None


def compute_purchase_discount(coupon, plan_id, base_charge_jpy, valid_subscription_plan_ids):
    if (coupon.get("type") or "balance") != "purchase":
        return None, "このクーポンは購入時専用です"
    target = (coupon.get("purchase_plan_id") or "").strip().lower()
    if target and target != (plan_id or "").strip().lower():
        return None, "このクーポンは選択中のプランでは利用できません"
    if plan_id not in valid_subscription_plan_ids:
        return None, "プランが不正です"
    try:
        base = int(round(float(base_charge_jpy)))
        discount = int(round(float(coupon.get("discount_jpy") or 0)))
    except (TypeError, ValueError):
        return None, "割引額の設定が不正です"
    if base <= 0:
        return None, "プラン料金が設定されていません"
    if discount <= 0:
        return None, "割引額の設定が不正です"
    discount = min(discount, base)
    final_charge = max(0, base - discount)
    return {
        "discount_jpy": discount,
        "final_charge_jpy": final_charge,
        "original_charge_jpy": base,
    }, None


def preview_purchase_coupon(username, code, plan_id, base_charge_jpy, valid_subscription_plan_ids):
    store = load_coupons_store()
    coupon = find_coupon(store, code=code)
    err = coupon_common_validation_error(coupon, username)
    if err:
        return None, err
    result, err = compute_purchase_discount(
        coupon, plan_id, base_charge_jpy, valid_subscription_plan_ids
    )
    if err:
        return None, err
    return {
        **result,
        "code": coupon.get("code"),
        "benefit_label": serialize_coupon(coupon).get("benefit_label"),
    }, None


def commit_purchase_coupon_redemption(username, code, plan_id, base_charge_jpy, valid_subscription_plan_ids):
    store = load_coupons_store()
    coupon = find_coupon(store, code=code)
    err = coupon_common_validation_error(coupon, username)
    if err:
        return None, err
    result, err = compute_purchase_discount(
        coupon, plan_id, base_charge_jpy, valid_subscription_plan_ids
    )
    if err:
        return None, err
    coupon.setdefault("redemptions", []).append(
        {
            "username": username,
            "redeemed_at": datetime.now().isoformat(timespec="seconds"),
            "plan_id": plan_id,
        }
    )
    save_coupons_store(store)
    return {**result, "code": coupon.get("code")}, None


def extend_user_plan_expires(record, plan_id, hours):
    now = datetime.now()
    current = parse_datetime_value(record.get("plan_expires_at"))
    base = now
    if current and current > now:
        base = current
    new_expires = base + timedelta(hours=hours)
    record["plan_expires_at"] = format_datetime_iso(new_expires)
    record["plan"] = plan_id


def redeem_coupon(
    username, code, record, valid_plan_ids, add_balance_fn, add_plan_hours_fn=None
):
    store = load_coupons_store()
    coupon = find_coupon(store, code=code)
    if not coupon:
        return None, "クーポンコードが見つかりません"

    if not coupon.get("enabled", True):
        return None, "このクーポンは無効化されています"

    expires_dt = parse_datetime_value(coupon.get("expires_at"))
    if expires_dt and datetime.now() > expires_dt:
        return None, "このクーポンの有効期限が切れています"

    max_uses = coupon.get("max_uses")
    used = coupon_used_count(coupon)
    if max_uses is not None and used >= int(max_uses):
        return None, "このクーポンは利用上限に達しています"

    if user_redeemed_coupon(coupon, username):
        return None, "このクーポンは既に利用済みです"

    ctype = coupon.get("type", "balance")
    if ctype == "purchase":
        return None, "このクーポンはプラン購入（残高払い）の確認画面でご利用ください"

    message = ""

    if ctype == "balance":
        amount = round(float(coupon.get("balance_amount", 0)), 2)
        record["balance"] = add_balance_fn(record, amount)
        message = f"残高に {format_jpy_integer(amount)} を追加しました"
    elif ctype == "plan":
        plan_id = (coupon.get("plan_id") or "plus").strip().lower()
        if plan_id not in valid_plan_ids:
            return None, "クーポンのプラン設定が不正です"
        hours = int(coupon.get("plan_hours") or 1)
        if add_plan_hours_fn:
            ent = add_plan_hours_fn(record, plan_id, hours, source="coupon")
            expires_at = (ent or {}).get("expires_at") or record.get("plan_expires_at") or ""
            message = (
                f"{plan_id} プランを {hours} 時間利用できます（期限: {expires_at}）"
            )
        else:
            extend_user_plan_expires(record, plan_id, hours)
            message = (
                f"{plan_id} プランを {hours} 時間利用できます（期限: {record['plan_expires_at']}）"
            )
    else:
        return None, "クーポンの種類が不正です"

    coupon.setdefault("redemptions", []).append(
        {
            "username": username,
            "redeemed_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_coupons_store(store)
    return {"message": message, "coupon_code": coupon.get("code"), "type": ctype}, None
