import calendar
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import quote, urlencode

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from announcements_store import list_announcements
from chat_agent import (
    format_chat_provider_error,
    stream_agent_chat,
    stream_chat_completion,
    stream_resume_after_ask_user,
)
from chat_share import (
    VISIBILITY_LOGIN_REQUIRED,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    get_session_share,
    load_share,
    upsert_share,
)
from chat_session_collab import (
    COLLAB_PARTICIPATE,
    COLLAB_PRIVATE,
    COLLAB_VIEW_ONLY,
    collab_public_payload,
    find_collab_by_id,
    get_collab_record,
    resolve_session_access,
    set_collab_mode,
)
from memory_storage import (
    add_memory,
    build_memory_summary,
    delete_memory,
    load_user_memories,
    update_memory,
)
from custom_agents_storage import (
    REASONING_DISPLAY_FORCE_SHOW,
    REASONING_DISPLAY_HIDE,
    REASONING_DISPLAY_USER,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    VISIBILITY_UNLISTED,
    apply_custom_agent_chat_reasoning_prefs,
    create_custom_agent,
    delete_custom_agent,
    enrich_custom_agent,
    find_custom_agent,
    find_custom_agent_by_share_id,
    increment_custom_agent_usage,
    load_user_custom_agents,
    update_custom_agent,
)
from deep_research import (
    get_user_deep_research_prefs,
    normalize_deep_research_prefs,
    resolve_user_deep_research_enabled,
)
from intelligent_search_override import resolve_user_intelligent_search_override_enabled
from info_experts_storage import (
    create_info_expert,
    delete_info_expert,
    find_info_expert,
    load_user_info_experts,
    serialize_expert,
    update_info_expert,
)
from expert_sessions_storage import (
    delete_expert_session,
    delete_expert_sessions_for_expert,
    get_expert_session_messages,
    get_expert_session_meta,
    list_expert_sessions,
    new_expert_session_id,
    upsert_expert_session,
)
from expert_knowledge_storage import delete_all_knowledge, list_knowledge_items
from expert_chat_agent import stream_expert_creation_chat
from full_info_trace import make_traced_sse_event
from tasks_storage import (
    load_user_tasks,
    resolve_user_memory_enabled,
    resolve_user_tasks_enabled,
    save_user_tasks,
)
from projects_storage import (
    find_accessible_project,
    load_user_projects,
    load_user_projects_bundle,
    resolve_user_projects_enabled,
    save_owner_project,
    save_user_projects,
)
from project_realtime import (
    init_project_realtime,
    notify_project_participants,
    publish_members_updated,
    publish_project_deleted,
    publish_project_patch,
    publish_user_sync,
)
from chat_realtime import init_chat_realtime
from chat_ws_handlers import build_chat_ws_handlers
from project_ws_handlers import build_project_ws_handlers
from project_members import (
    PERMISSIONS,
    add_incoming_invite,
    attach_project_access,
    get_member_role,
    has_permission,
    normalize_invites,
    normalize_members,
    normalize_role,
    remove_incoming_invite,
    serialize_invite_public,
    serialize_member_public,
    sync_member_indexes,
    load_incoming_invites,
    save_incoming_invites,
)
from project_chat_agent import (
    normalize_project_mode,
    prepare_project_chat_messages,
    stream_project_chat,
)
from geolocation import reverse_geocode_city, sanitize_location_context
from model_api_test import test_model_api
from model_registry import (
    PROVIDERS,
    get_default_model_id,
    get_default_model_public_id,
    get_model_api_id,
    get_provider_credentials,
    make_openai_client_for_provider,
    models_for_chat_list,
    models_for_openai_api,
    normalize_model_entry,
    normalize_providers_config,
    raw_models_missing_public_id,
    resolve_chat_model,
    validate_model_id,
    validate_unique_api_ids,
)
from model_usage import (
    DEFAULT_CHART_RANGE,
    build_usage_chart,
    load_usage_series,
    normalize_model_usage,
    normalize_models_config,
    record_model_usage_in_config,
    serialize_models_admin,
)
from mail_server import (
    consume_pending_email_registration,
    create_pending_email_registration,
    email_verification_required,
    mail_server_configured,
    normalize_mail_server,
    resolve_mail_server_config,
    send_email,
    send_verification_email,
    serialize_mail_server_admin,
)
from portal_sso import consume_portal_sso_token, create_portal_sso_token
from admin_session_monitor import (
    begin_monitored_chat,
    end_monitored_chat,
    init_admin_session_monitor,
    is_chat_aborted,
    list_active_sessions,
    list_session_logs,
    request_chat_abort,
    stream_with_abort,
    update_monitored_chat,
)
from chat_sessions_storage import (
    delete_chat_session,
    get_chat_session_messages,
    get_chat_session_meta,
    list_chat_sessions,
    sync_chat_sessions_from_client,
    upsert_chat_session,
)
from request_session_detail import (
    begin_request_detail,
    finish_request_detail,
    last_user_message_text,
    load_request_detail,
    record_request_detail_sse,
    serialize_request_detail_for_api,
    summarize_messages_for_audit,
)
from billing_entitlements import (
    active_entitlements,
    add_plan_entitlement,
    billing_model_note,
    create_billing_event,
    ensure_legacy_entitlements,
    highest_plan_from_entitlements,
    list_billing_events_for_user,
    normalize_entitlement,
    normalize_entitlements,
    serialize_billing_event,
    sync_record_plan_state,
    update_billing_event,
    usage_pool_summary,
)
from usage_accounting import (
    MIN_ON_DEMAND_START_JPY,
    allocate_usd_across_entitlements,
    billing_lock,
    commit_usage_reserve,
    entitlement_pool_used_usd,
    estimate_chat_reserve_usd,
    release_usage_reserve,
    try_reserve_usage,
)
from user_usage import (
    compute_turn_price_usd,
    normalize_user_usage,
    on_demand_balance_block_message,
    plan_ai_budget_usd,
    plan_tool_budget_usd,
    split_turn_billing_usd,
    usage_block_message,
    usage_display_label,
    usage_percent,
    usage_status,
    usage_warning_message,
)
from token_usage import (
    empty_usage,
    estimate_turn_tokens,
    merge_usage,
    resolve_turn_token_usage,
)
from coupons import (
    commit_purchase_coupon_redemption,
    create_coupon,
    delete_coupon,
    format_datetime_iso,
    list_coupons_serialized,
    normalize_coupon_code,
    parse_datetime_value,
    preview_purchase_coupon,
    redeem_coupon,
    serialize_coupon,
    set_coupon_enabled,
)
from paypal_billing import (
    BALANCE_CURRENCY,
    MIN_TOPUP_JPY,
    PLAN_SUBSCRIPTION_URL_ENV,
    SUBSCRIPTION_PLAN_IDS,
    capture_checkout_order,
    clear_token_cache,
    create_checkout_order,
    clear_paypal_plan_local,
    create_paypal_subscription_plan,
    deactivate_paypal_subscription_plan,
    get_plan_subscription_urls,
    get_paypal_plan_api_ids,
    normalize_plan_subscription_url,
    paypal_configured,
    paypal_mode,
    public_config as paypal_public_config,
    save_plan_subscription_urls,
    save_paypal_plan_api_ids,
)
from paypal_subscriptions import (
    create_billing_subscription,
    get_paypal_webhook_id,
    mark_webhook_event_seen,
    parse_subscription_resource,
    subscription_event_action,
    verify_webhook_signature,
    webhook_event_seen,
)
from plan_features import (
    DEFAULT_PLAN_FLAG_VALUES,
    PLAN_EXTENDED_TIER_DEFAULTS,
    PLAN_OCR_TIER_DEFAULTS,
    PLAN_SEARCH_TIER_DEFAULTS,
    admin_flag_catalog,
    admin_flag_groups,
    PLAN_GOOGLE_TIER_DEFAULTS,
    apply_flag_overrides,
    extract_plan_flags,
    extract_search_plan_flags,
    normalize_plan_flags_payload,
    normalize_search_plan_flags_payload,
    search_plan_flag_catalog,
)
from search_settings import (
    DEFAULT_SEARCH_ENGINES,
    get_search_engines_config,
    merge_search_engines_config,
    resolve_engines_for_plan,
    serialize_search_engines_admin,
)
from extended_models_registry import (
    get_anthropic_api_key,
    normalize_extended_models_config,
    normalize_ocr_engine,
    ocr_globally_enabled,
    resolve_ocr_model_for_plan,
    serialize_ocr_admin,
    validate_ocr_model_id,
    normalize_ocr_model_entry,
)
from image_generation_prefs import (
    list_image_models_for_plan,
    normalize_user_image_generation_prefs,
    serialize_image_generation_options,
)
from image_generation_registry import (
    IMAGE_PROVIDERS,
    normalize_image_generation_config,
    normalize_image_model_entry,
    plan_has_image_generation,
    serialize_image_generation_admin,
    validate_image_model_id,
)
from image_generation_storage import can_access_image, strip_generated_image_markdown
from image_ocr import (
    MAX_IMAGE_UPLOAD_BYTES,
    message_has_images,
    preprocess_messages_with_ocr,
)
from pdf_extract import (
    MAX_PDF_UPLOAD_BYTES,
    message_has_pdfs,
    preprocess_messages_with_pdf,
)
from web_search import extract_user_text
from discord_oauth import (
    OAUTH_MODE_LINK as DISCORD_OAUTH_MODE_LINK,
    OAUTH_MODE_LOGIN as DISCORD_OAUTH_MODE_LOGIN,
    build_authorization_url as build_discord_authorization_url,
    discord_oauth_configured,
    exchange_code_for_tokens as exchange_discord_code_for_tokens,
    fetch_discord_userinfo,
    get_redirect_uri as get_discord_redirect_uri,
)
from google_oauth import (
    OAUTH_MODE_LINK,
    OAUTH_MODE_LOGIN,
    OAUTH_MODE_TOOLS,
    build_authorization_url,
    build_login_authorization_url,
    disconnect_user,
    GoogleOAuthError,
    exchange_code_for_tokens,
    fetch_google_userinfo,
    get_google_oauth_scopes,
    get_redirect_uri,
    google_oauth_configured,
    store_tokens_for_user,
    user_google_connected,
)
from computelab_token_store import (
    delete_api_key as delete_computelab_api_key,
    get_key_prefix as get_computelab_key_prefix,
    has_api_key as user_computelab_connected,
    set_api_key as set_computelab_api_key,
)
from computelab_services import (
    test_connection as test_computelab_connection,
    verify_api_key as verify_computelab_api_key,
)
from api_auth import (
    resolve_api_auth,
    user_api_access_enabled,
    user_plan_api_access_allowed,
)
from api_tokens_storage import create_user_token, list_user_tokens, revoke_user_token
from system_api_keys import (
    MAX_SYSTEM_API_KEYS,
    create_system_api_key,
    list_system_api_keys,
    revoke_system_api_key,
)
from rate_limit import check_rate_limit
from openai_compat import (
    build_models_list,
    openai_error,
    parse_chat_completions_request,
)
from v1_chat_service import (
    format_v1_provider_error,
    iter_v1_chat_stream,
    run_v1_chat_sync,
)
from server_control import (
    get_restart_request,
    request_service_restart,
    service_label,
    sync_restart_status,
)
from server_health import (
    DEFAULT_DEPLOYMENT,
    OPERATION_MODES,
    local_health_payload,
    normalize_deployment,
    probe_service,
    serialize_deployment_admin,
)
from server_split import (
    SERVER_MODE_API,
    SERVER_MODE_API_PORTAL,
    SERVER_MODE_COMBINED,
    SERVER_MODE_FRONTEND,
    api_portal_base_url,
    apply_server_mode,
    get_server_mode,
    public_api_base_url,
    public_base_url,
    public_page_url,
    register_ws_proxy,
)

load_dotenv()

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
_MAX_ATTACHMENT_BYTES = max(MAX_IMAGE_UPLOAD_BYTES, MAX_PDF_UPLOAD_BYTES)
app.config["MAX_CONTENT_LENGTH"] = _MAX_ATTACHMENT_BYTES * 8
_flask_secret_key = os.getenv("FLASK_SECRET_KEY", "").strip()
if not _flask_secret_key:
    _debug_mode = os.getenv("FLASK_DEBUG", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if _debug_mode:
        _flask_secret_key = secrets.token_hex(32)
        logging.getLogger(__name__).warning(
            "FLASK_SECRET_KEY が未設定のため一時キーを使用します。"
            "再起動するとセッションが無効になります。"
        )
    else:
        raise RuntimeError("FLASK_SECRET_KEY 環境変数を設定してください")
app.secret_key = _flask_secret_key

USERS_FILE = Path(__file__).parent / "data" / "users.json"
SYSTEM_CONFIG_FILE = Path(__file__).parent / "data" / "system_config.json"

DEFAULT_FEATURES = {
    "chat_disabled": False,
    "search_disabled": False,
    "registration_disabled": False,
    "upload_disabled": False,
    "billing_disabled": False,
    "coupon_disabled": False,
    "google_login_disabled": False,
    "discord_login_disabled": False,
}

DEFAULT_PAYPAL = {
    "client_id": "",
    "client_secret": "",
    "mode": "sandbox",
    "webhook_id": "",
}

DEFAULT_GOOGLE_OAUTH = {
    "client_id": "",
    "client_secret": "",
    "redirect_uri": "",
    "calendar_scopes_enabled": True,
    "gmail_scopes_enabled": True,
}

DEFAULT_DISCORD_OAUTH = {
    "client_id": "",
    "client_secret": "",
    "redirect_uri": "",
}

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

DEFAULT_SERVICE_URLS = {
    "frontend_base_url": "",
    "api_portal_base_url": "",
    "api_base_url": "",
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "deepseek-v4-flash")

THINK_BLOCK_RE = re.compile(
    "<" + "think" + r">[\s\S]*?<" + "/think" + ">",
    re.IGNORECASE,
)


def load_users():
    from json_store import read_json

    return read_json(USERS_FILE, default={}) or {}


def save_users(users):
    from json_store import write_json

    write_json(USERS_FILE, users)


_config_loading = False


def normalize_service_urls(raw):
    src = raw if isinstance(raw, dict) else {}
    return {
        key: str(src.get(key) or "").strip().rstrip("/")
        for key in DEFAULT_SERVICE_URLS
    }


def load_system_config():
    global _config_loading
    if not SYSTEM_CONFIG_FILE.exists():
        return {
            "features": dict(DEFAULT_FEATURES),
            "plans": {},
            "paypal": dict(DEFAULT_PAYPAL),
            "google_oauth": dict(DEFAULT_GOOGLE_OAUTH),
            "discord_oauth": dict(DEFAULT_DISCORD_OAUTH),
            "mail_server": dict(DEFAULT_MAIL_SERVER),
            "deployment": dict(DEFAULT_DEPLOYMENT),
            "search_engines": dict(DEFAULT_SEARCH_ENGINES),
            "service_urls": dict(DEFAULT_SERVICE_URLS),
            "usd_jpy_rate": parse_usd_jpy_rate(None),
        }
    with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    features = {**DEFAULT_FEATURES, **(data.get("features") or {})}
    paypal = {**DEFAULT_PAYPAL, **(data.get("paypal") or {})}
    google_oauth = {**DEFAULT_GOOGLE_OAUTH, **(data.get("google_oauth") or {})}
    discord_oauth = {**DEFAULT_DISCORD_OAUTH, **(data.get("discord_oauth") or {})}
    mail_server = normalize_mail_server(
        {**DEFAULT_MAIL_SERVER, **(data.get("mail_server") or {})}
    )
    deployment = normalize_deployment(
        {**DEFAULT_DEPLOYMENT, **(data.get("deployment") or {})}
    )
    search_engines = {
        **DEFAULT_SEARCH_ENGINES,
        **(data.get("search_engines") or {}),
    }
    result = {
        "features": features,
        "plans": normalize_plans_config(data.get("plans")),
        "paypal": paypal,
        "google_oauth": google_oauth,
        "discord_oauth": discord_oauth,
        "mail_server": mail_server,
        "deployment": deployment,
        "search_engines": search_engines,
        "models": normalize_models_config(data.get("models")),
        "model_usage": normalize_model_usage(data.get("model_usage")),
        "providers": normalize_providers_config(data.get("providers")),
        "default_model": (data.get("default_model") or "").strip(),
        "extended_models": normalize_extended_models_config(data.get("extended_models")),
        "image_generation": normalize_image_generation_config(data.get("image_generation")),
        "service_urls": normalize_service_urls(data.get("service_urls")),
        "usd_jpy_rate": parse_usd_jpy_rate(data.get("usd_jpy_rate")),
    }
    if not _config_loading and raw_models_missing_public_id(data.get("models")):
        _config_loading = True
        try:
            save_system_config(result)
        finally:
            _config_loading = False
    return result


def save_system_config(config):
    SYSTEM_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    current = load_system_config()
    payload = {
        "features": {**DEFAULT_FEATURES, **(config.get("features") or current["features"])},
        "plans": normalize_plans_config(
            config.get("plans") if "plans" in config else current["plans"]
        ),
        "paypal": {**DEFAULT_PAYPAL, **(config.get("paypal") or current["paypal"])},
        "google_oauth": {
            **DEFAULT_GOOGLE_OAUTH,
            **(config.get("google_oauth") or current.get("google_oauth") or {}),
        },
        "discord_oauth": {
            **DEFAULT_DISCORD_OAUTH,
            **(config.get("discord_oauth") or current.get("discord_oauth") or {}),
        },
        "mail_server": normalize_mail_server(
            {
                **DEFAULT_MAIL_SERVER,
                **(config.get("mail_server") or current.get("mail_server") or {}),
            }
        ),
        "deployment": normalize_deployment(
            {
                **DEFAULT_DEPLOYMENT,
                **(config.get("deployment") or current.get("deployment") or {}),
            }
        ),
        "search_engines": merge_search_engines_config(
            config.get("search_engines") if "search_engines" in config else None,
            current.get("search_engines"),
        ),
        "models": normalize_models_config(
            config.get("models") if "models" in config else current.get("models")
        ),
        "model_usage": normalize_model_usage(
            config.get("model_usage")
            if "model_usage" in config
            else current.get("model_usage")
        ),
        "providers": normalize_providers_config(
            config.get("providers") if "providers" in config else current.get("providers")
        ),
        "default_model": (
            config.get("default_model")
            if "default_model" in config
            else current.get("default_model", "")
        ),
        "extended_models": normalize_extended_models_config(
            config.get("extended_models")
            if "extended_models" in config
            else current.get("extended_models")
        ),
        "image_generation": normalize_image_generation_config(
            config.get("image_generation")
            if "image_generation" in config
            else current.get("image_generation")
        ),
        "usd_jpy_rate": parse_usd_jpy_rate(
            config.get("usd_jpy_rate")
            if "usd_jpy_rate" in config
            else current.get("usd_jpy_rate")
        ),
        "service_urls": normalize_service_urls(
            config.get("service_urls")
            if "service_urls" in config
            else current.get("service_urls")
        ),
    }
    with open(SYSTEM_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def admin_models_payload(config, chart_range=None):
    return serialize_models_admin(
        config["models"],
        config["model_usage"],
        get_default_model_id(config),
        chart_range=chart_range,
        providers_config=config.get("providers"),
        default_model_id=get_default_model_id(config),
    )


def serialize_google_oauth_admin():
    from urllib.parse import urlparse

    cfg = load_system_config()["google_oauth"]
    client_id = (cfg.get("client_id") or "").strip()
    secret = (cfg.get("client_secret") or "").strip()
    redirect_uri = (cfg.get("redirect_uri") or "").strip()
    env_fallback = bool(
        not client_id
        and os.getenv("GOOGLE_CLIENT_ID")
        and os.getenv("GOOGLE_CLIENT_SECRET")
    )
    effective_redirect = redirect_uri or get_redirect_uri()
    origin_hint = ""
    try:
        parsed = urlparse(effective_redirect)
        if parsed.scheme and parsed.netloc:
            origin_hint = f"{parsed.scheme}://{parsed.netloc}"
    except ValueError:
        origin_hint = ""
    return {
        "client_id": client_id or os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        "redirect_uri": effective_redirect,
        "configured": google_oauth_configured(),
        "secret_set": bool(secret or (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()),
        "env_fallback": env_fallback,
        "calendar_scopes_enabled": bool(cfg.get("calendar_scopes_enabled", True)),
        "gmail_scopes_enabled": bool(cfg.get("gmail_scopes_enabled", True)),
        "javascript_origins_hint": origin_hint,
        "scopes": get_google_oauth_scopes(),
    }


def serialize_discord_oauth_admin():
    config = load_system_config()
    cfg = config["discord_oauth"]
    features = config["features"]
    client_id = (cfg.get("client_id") or "").strip()
    secret = (cfg.get("client_secret") or "").strip()
    redirect_uri = (cfg.get("redirect_uri") or "").strip()
    env_fallback = bool(
        not client_id
        and os.getenv("DISCORD_CLIENT_ID")
        and os.getenv("DISCORD_CLIENT_SECRET")
    )
    effective_redirect = redirect_uri or get_discord_redirect_uri()
    login_disabled = bool(features.get("discord_login_disabled"))
    return {
        "client_id": client_id or os.getenv("DISCORD_CLIENT_ID", "").strip(),
        "redirect_uri": effective_redirect,
        "configured": discord_oauth_configured(),
        "secret_set": bool(secret or (os.getenv("DISCORD_CLIENT_SECRET") or "").strip()),
        "env_fallback": env_fallback,
        "discord_login_disabled": login_disabled,
        "discord_login_available": discord_oauth_configured() and not login_disabled,
    }


def serialize_paypal_admin():
    paypal = load_system_config()["paypal"]
    client_id = (paypal.get("client_id") or "").strip()
    secret = (paypal.get("client_secret") or "").strip()
    mode = (paypal.get("mode") or "sandbox").strip().lower()
    if mode not in ("sandbox", "live"):
        mode = "sandbox"
    env_fallback = bool(
        not client_id
        and os.getenv("PAYPAL_CLIENT_ID")
        and os.getenv("PAYPAL_CLIENT_SECRET")
    )
    webhook_id = (paypal.get("webhook_id") or os.getenv("PAYPAL_WEBHOOK_ID") or "").strip()
    return {
        "client_id": client_id or os.getenv("PAYPAL_CLIENT_ID", "").strip(),
        "mode": mode,
        "configured": paypal_configured(),
        "secret_set": bool(secret),
        "webhook_id": webhook_id,
        "webhook_id_set": bool(webhook_id),
        "env_fallback": env_fallback,
        "min_topup_jpy": MIN_TOPUP_JPY,
        "currency": BALANCE_CURRENCY,
    }


def serialize_subscriptions_admin():
    catalog = get_plan_catalog()
    merged_urls = get_plan_subscription_urls()
    config = load_system_config()
    stored = (config.get("paypal") or {}).get("plan_urls") or {}
    if not isinstance(stored, dict):
        stored = {}
    plans = []
    for key in SUBSCRIPTION_PLAN_IDS:
        info = catalog[key]
        url = merged_urls.get(key, "")
        env_key = PLAN_SUBSCRIPTION_URL_ENV[key]
        env_val = (os.getenv(env_key) or "").strip()
        config_val = (stored.get(key) or "").strip()
        if config_val:
            source = "config"
        elif env_val:
            source = "env"
        else:
            source = ""
        price_usd = info.get("price_usd")
        plans.append(
            {
                "id": key,
                "name": info["name"],
                "price_usd": price_usd,
                "price_label": info.get("price_label") or "",
                "paypal_url": url,
                "url_configured": bool(url),
                "url_source": source,
            }
        )
    mode = paypal_mode()
    plan_api_ids = get_paypal_plan_api_ids()
    return {
        "plans": plans,
        "plan_urls": {key: merged_urls.get(key, "") for key in SUBSCRIPTION_PLAN_IDS},
        "plan_api_ids": {
            key: plan_api_ids.get(key, {}) for key in SUBSCRIPTION_PLAN_IDS
        },
        "mode": mode,
        "mode_label": "live（本番）" if mode == "live" else "sandbox（テスト）",
        "paypal_configured": paypal_configured(),
        "env_keys": PLAN_SUBSCRIPTION_URL_ENV,
    }


def get_feature_flags():
    return load_system_config()["features"]


def feature_blocked(flag_name):
    return bool(get_feature_flags().get(flag_name))


def get_plan_catalog():
    overrides = load_system_config().get("plans") or {}
    catalog = {}
    for key, base in PLANS.items():
        ov = overrides.get(key) or {}
        price_usd = ov["price_usd"] if "price_usd" in ov else base["price_usd"]
        if "price_label" in ov and ov["price_label"]:
            price_label = str(ov["price_label"]).strip()
        elif price_usd is None:
            price_label = base["price_label"]
        else:
            price_label = f"${price_usd}/月"
        ja_desc, en_desc = plan_descriptions_from_override(ov)
        catalog[key] = {
            "name": base["name"],
            "paypal_name": base.get("paypal_name") or base["name"],
            "price_usd": price_usd,
            "price_label": price_label,
            "description_ja": ja_desc,
            "description_en": en_desc,
            "description": ja_desc,
        }
    return catalog


def get_plan_info(plan_key):
    return get_plan_catalog()[normalize_plan(plan_key)]


def init_system_config():
    changed = False
    if not SYSTEM_CONFIG_FILE.exists():
        paypal = dict(DEFAULT_PAYPAL)
        if os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_CLIENT_SECRET"):
            paypal["client_id"] = os.getenv("PAYPAL_CLIENT_ID", "").strip()
            paypal["client_secret"] = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
            paypal["mode"] = (os.getenv("PAYPAL_MODE") or "sandbox").strip().lower()
        google_oauth = dict(DEFAULT_GOOGLE_OAUTH)
        if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"):
            google_oauth["client_id"] = os.getenv("GOOGLE_CLIENT_ID", "").strip()
            google_oauth["client_secret"] = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
            google_oauth["redirect_uri"] = (
                os.getenv("GOOGLE_REDIRECT_URI", "").strip()
                or get_redirect_uri()
            )
        discord_oauth = dict(DEFAULT_DISCORD_OAUTH)
        if os.getenv("DISCORD_CLIENT_ID") and os.getenv("DISCORD_CLIENT_SECRET"):
            discord_oauth["client_id"] = os.getenv("DISCORD_CLIENT_ID", "").strip()
            discord_oauth["client_secret"] = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
            discord_oauth["redirect_uri"] = (
                os.getenv("DISCORD_REDIRECT_URI", "").strip()
                or get_discord_redirect_uri()
            )
        save_system_config(
            {
                "features": dict(DEFAULT_FEATURES),
                "plans": {},
                "paypal": paypal,
                "google_oauth": google_oauth,
                "discord_oauth": discord_oauth,
            }
        )
        return

    config = load_system_config()
    raw = {}
    with open(SYSTEM_CONFIG_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    if "paypal" not in raw:
        config["paypal"] = dict(DEFAULT_PAYPAL)
        changed = True
    if "google_oauth" not in raw:
        config["google_oauth"] = dict(DEFAULT_GOOGLE_OAUTH)
        changed = True
    if "discord_oauth" not in raw:
        config["discord_oauth"] = dict(DEFAULT_DISCORD_OAUTH)
        changed = True
    for key in DEFAULT_FEATURES:
        if key not in config["features"]:
            config["features"][key] = DEFAULT_FEATURES[key]
            changed = True
    if "models" not in raw:
        config["models"] = normalize_models_config({})
        changed = True
    if "model_usage" not in raw:
        config["model_usage"] = normalize_model_usage({})
        changed = True
    if "providers" not in raw:
        config["providers"] = normalize_providers_config({})
        changed = True
    if not config.get("default_model"):
        config["default_model"] = get_default_model_id(config)
        changed = True
    if "extended_models" not in raw:
        config["extended_models"] = normalize_extended_models_config({})
        changed = True
    if "image_generation" not in raw:
        config["image_generation"] = normalize_image_generation_config({})
        changed = True
    if changed:
        save_system_config(config)


def record_model_usage(model_id, token_usage):
    if not model_id or not token_usage:
        return
    config = load_system_config()
    config = record_model_usage_in_config(config, model_id, token_usage)
    save_system_config(config)


PLAN_ORDER = ("free", "plus", "pro", "pro_plus", "max", "enterprise")

PLAN_ALIASES = {
    "basic": "plus",
    "proplus": "pro_plus",
    "pro+": "pro_plus",
    "pro-plus": "pro_plus",
}

PLANS = {
    "free": {"name": "Free", "price_label": "無料", "price_usd": 0},
    "plus": {
        "name": "PASS+",
        "paypal_name": "NEXGATE AI | PASS+",
        "price_label": "$10/月",
        "price_usd": 10,
    },
    "pro": {
        "name": "PASS Pro",
        "paypal_name": "NEXGATE AI | PASS Pro",
        "price_label": "$20/月",
        "price_usd": 20,
    },
    "pro_plus": {
        "name": "PASS Pro+",
        "paypal_name": "NEXGATE AI | PASS Pro+",
        "price_label": "$60/月",
        "price_usd": 60,
    },
    "max": {
        "name": "PASS MAX",
        "paypal_name": "NEXGATE AI | PASS MAX",
        "price_label": "$100/月",
        "price_usd": 100,
    },
    "enterprise": {
        "name": "Enterprise",
        "price_label": "未設定",
        "price_usd": None,
    },
}

PLAN_MONTHLY_AI_BUDGET_USD = {
    "free": 0.20,
    "plus": 6.0,
    "pro": 12.0,
    "pro_plus": 36.0,
    "max": 60.0,
    "enterprise": None,
}

PLAN_CHAT_BLOCKED_MSG = (
    "現在のプランではチャットを利用できません。"
    "プラン/課金ページからプランをアップグレードするか、残高をチャージしてください。"
)

DEFAULT_USERS = {}


def normalize_plan(plan):
    key = (plan or "free").strip().lower()
    key = PLAN_ALIASES.get(key, key)
    return key if key in PLANS else "free"


def plan_tier_rank(plan_key):
    key = normalize_plan(plan_key)
    try:
        return PLAN_ORDER.index(key)
    except ValueError:
        return 0


def parse_usd_jpy_rate(value):
    if value is None or value == "":
        env = (os.getenv("USD_JPY_RATE") or "").strip()
        if env:
            try:
                return max(1.0, float(env))
            except (TypeError, ValueError):
                pass
        return 150.0
    try:
        return max(1.0, float(value))
    except (TypeError, ValueError):
        return 150.0


def get_usd_jpy_rate():
    return parse_usd_jpy_rate(load_system_config().get("usd_jpy_rate"))


def plan_charge_jpy(plan_key):
    key = normalize_plan(plan_key)
    if key not in SUBSCRIPTION_PLAN_IDS:
        return None
    overrides = load_system_config().get("plans") or {}
    ov = overrides.get(key) or {}
    if "price_jpy" in ov and ov["price_jpy"] is not None:
        try:
            return max(0, int(round(float(ov["price_jpy"]))))
        except (TypeError, ValueError):
            pass
    price_usd = get_plan_info(key).get("price_usd")
    if price_usd is None:
        return None
    try:
        usd = float(price_usd)
    except (TypeError, ValueError):
        return None
    if usd <= 0:
        return None
    return max(0, int(round(usd * get_usd_jpy_rate())))


def add_one_calendar_month(dt):
    year = dt.year
    month = dt.month + 1
    if month > 12:
        month = 1
        year += 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, max_day)
    return dt.replace(year=year, month=month, day=day, microsecond=0)


def extend_user_plan_one_month(record, plan_id, quantity=1, source="balance"):
    add_plan_entitlement(
        record,
        plan_id,
        months=1,
        quantity=quantity,
        source=source,
        plan_budget_fn=plan_monthly_ai_budget_usd,
        normalize_plan_fn=normalize_plan,
        add_one_month_fn=add_one_calendar_month,
        plan_tier_rank_fn=plan_tier_rank,
    )


def apply_balance_plan_subscription(record, plan_id, username=None, coupon_code=None):
    plan_id = normalize_plan(plan_id)
    charge_jpy = plan_charge_jpy(plan_id)
    if charge_jpy is None or charge_jpy <= 0:
        return None, "プラン料金が設定されていません"

    original_charge_jpy = int(charge_jpy)
    discount_jpy = 0
    applied_coupon_code = ""
    if coupon_code and str(coupon_code).strip():
        if not username:
            return None, "クーポンの適用に失敗しました"
        coupon_result, err = commit_purchase_coupon_redemption(
            username,
            coupon_code,
            plan_id,
            original_charge_jpy,
            set(SUBSCRIPTION_PLAN_IDS),
        )
        if err:
            return None, err
        discount_jpy = int(coupon_result.get("discount_jpy") or 0)
        charge_jpy = int(coupon_result.get("final_charge_jpy") or original_charge_jpy)
        applied_coupon_code = coupon_result.get("code") or normalize_coupon_code(coupon_code)
    else:
        charge_jpy = original_charge_jpy

    balance = user_balance(record)
    if balance < charge_jpy:
        shortfall = int(round(charge_jpy - balance))
        return None, f"残高が不足しています（あと ¥{shortfall:,} 必要です）"

    plan_name = get_plan_info(plan_id)["name"]
    payment_id = str(uuid.uuid4())
    records = normalize_payment_records(record.get("payment_records"))
    note = f"{plan_name} プラン（1ヶ月）"
    if applied_coupon_code and discount_jpy > 0:
        note = f"{note} · クーポン {applied_coupon_code}（-{format_balance_jpy(discount_jpy)}）"
    records.append(
        {
            "id": payment_id,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": int(charge_jpy),
            "method": "残高",
            "note": note,
            "status": "paid",
        }
    )
    record["payment_records"] = records
    record["balance"] = round(balance - float(charge_jpy), 2)
    extend_user_plan_one_month(record, plan_id)
    return {
        "plan": plan_id,
        "plan_name": plan_name,
        "charge_jpy": charge_jpy,
        "original_charge_jpy": original_charge_jpy,
        "discount_jpy": discount_jpy,
        "coupon_code": applied_coupon_code,
        "balance": record["balance"],
    }, None


def normalize_plan_description(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip()


def plan_descriptions_from_override(ov):
    if not isinstance(ov, dict):
        ov = {}
    legacy = normalize_plan_description(ov.get("description", ""))
    ja = normalize_plan_description(ov.get("description_ja", "")) or legacy
    en = normalize_plan_description(ov.get("description_en", ""))
    return ja, en


def plan_description_for_language(ja, en, lang):
    key = (lang or "ja").strip().lower()
    if key == "ja":
        return ja or en
    if key in ("en", "ko"):
        return en or ja
    return ja or en


def normalize_plan_config_entry(entry):
    if not isinstance(entry, dict):
        return {}
    out = dict(entry)
    ja, en = plan_descriptions_from_override(out)
    if ja:
        out["description_ja"] = ja
    if en:
        out["description_en"] = en
    if "description" in out:
        out.pop("description", None)
    if "price_jpy" in out and out["price_jpy"] is not None:
        try:
            out["price_jpy"] = max(0, int(round(float(out["price_jpy"]))))
        except (TypeError, ValueError):
            out.pop("price_jpy", None)
    return out


def normalize_plans_config(plans):
    if not isinstance(plans, dict):
        return {}
    return {
        key: normalize_plan_config_entry(entry)
        for key, entry in plans.items()
        if key in PLANS and isinstance(entry, dict)
    }


def _parse_optional_budget_usd(value):
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError("月間利用枠（USD）が不正です")
    if n < 0:
        raise ValueError("月間利用枠は0以上にしてください")
    return round(n, 4)


def default_plan_features(plan_key):
    key = normalize_plan(plan_key)
    budget = PLAN_MONTHLY_AI_BUDGET_USD.get(key)
    if budget is None:
        chat_enabled = True
    else:
        chat_enabled = float(budget) > 0
    merged = {
        "monthly_ai_budget_usd": budget,
        "chat_enabled": chat_enabled,
        **DEFAULT_PLAN_FLAG_VALUES,
    }
    merged.update(PLAN_GOOGLE_TIER_DEFAULTS.get(key, {}))
    merged.update(PLAN_OCR_TIER_DEFAULTS.get(key, {}))
    merged.update(PLAN_SEARCH_TIER_DEFAULTS.get(key, {}))
    merged.update(PLAN_EXTENDED_TIER_DEFAULTS.get(key, {}))
    return merged


def get_plan_features(plan_key):
    key = normalize_plan(plan_key)
    merged = default_plan_features(key)
    ov = (load_system_config().get("plans") or {}).get(key) or {}
    feat_ov = ov.get("features") or {}
    if not isinstance(feat_ov, dict):
        return merged
    if "monthly_ai_budget_usd" in feat_ov:
        merged["monthly_ai_budget_usd"] = _parse_optional_budget_usd(
            feat_ov["monthly_ai_budget_usd"]
        )
    if "chat_enabled" in feat_ov:
        merged["chat_enabled"] = bool(feat_ov["chat_enabled"])
    apply_flag_overrides(merged, feat_ov)
    return merged


def plan_monthly_ai_budget_usd(plan_key):
    """Monthly AI usage budget (USD, provider price). None = unlimited."""
    feat = get_plan_features(plan_key)
    budget = feat.get("monthly_ai_budget_usd")
    if budget is None:
        return None
    return round(float(budget), 4)


def usage_pool_for_record(record):
    ensure_legacy_entitlements(
        record, plan_monthly_ai_budget_usd, normalize_plan
    )
    return usage_pool_summary(
        record,
        plan_monthly_ai_budget_usd,
        normalize_plan,
        plan_tier_rank_fn=plan_tier_rank,
    )


def effective_plan_for_features(record):
    ents = active_entitlements(record, plan_budget_fn=plan_monthly_ai_budget_usd)
    if ents:
        return highest_plan_from_entitlements(
            ents, normalize_plan, plan_tier_rank_fn=plan_tier_rank
        )
    return normalize_plan(record.get("plan"))


def plan_web_search_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("web_search_enabled", True))


def plan_geolocation_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("geolocation_enabled", False))


def plan_tasks_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("tasks_enabled", False))


def plan_memory_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("memory_enabled", False))


def plan_projects_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("projects_enabled", False))


def plan_deep_research_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("deep_research_enabled", False))


def plan_image_generation_enabled(plan_key):
    if not bool(get_plan_features(plan_key).get("image_generation_enabled", False)):
        return False
    config = load_system_config()
    return plan_has_image_generation(plan_key, config.get("image_generation"))


def plan_computelab_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("computelab_enabled", False))


def plan_custom_agents_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("custom_agents_enabled", False))


def plan_api_access_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("api_access_enabled", False))


def plan_chat_share_enabled(plan_key):
    return bool(
        get_plan_features(plan_key).get(
            "chat_share_enabled",
            DEFAULT_PLAN_FLAG_VALUES.get("chat_share_enabled", True),
        )
    )


def plan_reasoning_cards_enabled(plan_key):
    return bool(
        get_plan_features(plan_key).get(
            "reasoning_cards_enabled",
            DEFAULT_PLAN_FLAG_VALUES.get("reasoning_cards_enabled", True),
        )
    )


def plan_tool_trace_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("tool_trace_enabled", False))


def plan_full_info_display_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("full_info_display_enabled", False))


def plan_file_upload_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("file_upload_enabled", True))


def plan_ocr_enabled(plan_key):
    return bool(get_plan_features(plan_key).get("ocr_enabled", False))


def plan_google_calendar_enabled(plan_key):
    return bool(
        get_plan_features(plan_key).get(
            "google_calendar_enabled",
            DEFAULT_PLAN_FLAG_VALUES.get("google_calendar_enabled", False),
        )
    )


def plan_google_gmail_enabled(plan_key):
    return bool(
        get_plan_features(plan_key).get(
            "google_gmail_enabled",
            DEFAULT_PLAN_FLAG_VALUES.get("google_gmail_enabled", False),
        )
    )


def user_google_plan_calendar_allowed(record):
    if not record:
        return False
    if record.get("role") == "admin":
        return True
    return plan_google_calendar_enabled(normalize_plan(record.get("plan")))


def user_google_plan_gmail_allowed(record):
    if not record:
        return False
    if record.get("role") == "admin":
        return True
    return plan_google_gmail_enabled(normalize_plan(record.get("plan")))


def normalize_plan_features_payload(plan_key, raw_features):
    if not isinstance(raw_features, dict):
        return None
    out = {}
    if "monthly_ai_budget_usd" in raw_features:
        out["monthly_ai_budget_usd"] = _parse_optional_budget_usd(
            raw_features["monthly_ai_budget_usd"]
        )
    if "chat_enabled" in raw_features:
        out["chat_enabled"] = bool(raw_features["chat_enabled"])
    flag_part = normalize_plan_flags_payload(raw_features)
    if flag_part:
        out.update(flag_part)
    return out or None


def serialize_admin_plan(plan_key):
    key = normalize_plan(plan_key)
    info = get_plan_catalog()[key]
    feat = get_plan_features(key)
    return {
        "id": key,
        "name": info["name"],
        "paypal_name": info.get("paypal_name") or info["name"],
        "price_usd": info["price_usd"],
        "price_label": info["price_label"],
        "description": info.get("description_ja") or info.get("description", ""),
        "description_ja": info.get("description_ja", ""),
        "description_en": info.get("description_en", ""),
        "features": feat,
        "monthly_ai_budget_usd": feat.get("monthly_ai_budget_usd"),
    }


def usage_summary_for_record(record, lang="ja"):
    pool = usage_pool_for_record(record)
    plan = effective_plan_for_features(record)
    pinfo = get_plan_info(plan)
    budget = pool["ai_budget_usd"]
    usage = pool["usage"]
    cost = float(usage.get("usage_cost_usd") or 0)
    percent = pool["usage_percent"]
    return {
        "usage_cost_usd": cost,
        "tool_usage_cost_usd": float(usage.get("tool_usage_cost_usd") or 0),
        "ai_budget_usd": budget,
        "tool_budget_usd": plan_tool_budget_usd(pinfo.get("price_usd")),
        "usage_percent": percent,
        "usage_unlimited": pool["usage_unlimited"],
        "usage_display_label": usage_display_label(percent, budget, lang),
        "usage_status": pool["usage_status"],
        "usage_is_over_limit": percent >= 100 and budget is not None,
        "usage_warning": usage_warning_message(percent, lang),
        "usage_pool_id": pool["pool_id"],
        "usage_pool_expires_at": pool.get("pool_expires_at") or "",
        "active_entitlements": pool.get("active_entitlements") or [],
        "ai_available_usd": pool.get("ai_available_usd"),
    }


def try_reserve_chat_usage(username, request_id, model_entry=None):
    with billing_lock():
        users = load_users()
        record = users.get(username)
        if not record or record.get("role") == "admin":
            return True, None
        pool = usage_pool_for_record(record)
        if pool.get("usage_unlimited"):
            return True, None
        budget = pool["ai_budget_usd"]
        amount = estimate_chat_reserve_usd(model_entry)
        ok, _err = try_reserve_usage(
            username,
            request_id,
            amount,
            record,
            pool["active_entitlements"],
            budget,
        )
        if ok:
            users[username] = record
            save_users(users)
            return True, None
        lang = (record.get("language") or "ja").strip().lower()
        if lang not in ("ja", "en", "ko"):
            lang = "ja"
        on_demand = user_on_demand_billing_enabled(record)
        balance = user_balance(record)
        if on_demand and balance >= MIN_ON_DEMAND_START_JPY:
            return True, None
        if on_demand:
            return False, on_demand_balance_block_message(lang)
        return False, usage_block_message(lang)


def release_chat_usage_reserve(username, request_id):
    with billing_lock():
        users = load_users()
        record = users.get(username)
        if not record:
            return
        release_usage_reserve(record, request_id)
        users[username] = record
        save_users(users)


def plan_allows_chat(username):
    with billing_lock():
        users = load_users()
        record = users.get(username)
        if not record:
            return False, "ユーザーが見つかりません"
        if record.get("role") == "admin":
            return True, None
        plan = effective_plan_for_features(record)
        feat = get_plan_features(plan)
        if not feat.get("chat_enabled", True):
            return False, PLAN_CHAT_BLOCKED_MSG
        pool = usage_pool_for_record(record)
        budget = pool["ai_budget_usd"]
        if budget is None:
            return True, None
        lang = (record.get("language") or "ja").strip().lower()
        if lang not in ("ja", "en", "ko"):
            lang = "ja"
        on_demand = user_on_demand_billing_enabled(record)
        balance = user_balance(record)
        available = pool.get("ai_available_usd")
        if budget <= 0:
            if on_demand and balance >= MIN_ON_DEMAND_START_JPY:
                return True, None
            return False, PLAN_CHAT_BLOCKED_MSG
        if available is not None and available > 1e-9:
            return True, None
        if on_demand:
            if balance >= MIN_ON_DEMAND_START_JPY:
                return True, None
            return False, on_demand_balance_block_message(lang)
        return False, usage_block_message(lang)


def current_usage_period():
    return datetime.now().strftime("%Y-%m")


def get_user_usage(username):
    with billing_lock():
        users = load_users()
        record = users.setdefault(username, {})
        pool = usage_pool_for_record(record)
        usage = pool["usage"]
        if record.get("usage") != usage:
            record["usage"] = usage
            users[username] = record
            save_users(users)
        return usage


def request_client_ip():
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.remote_addr or "").strip()[:64]


def admin_monitor_token_snapshot(turn_usage, prepared, stream_text, api_model):
    recorded = {
        "prompt_tokens": int(turn_usage.get("prompt_tokens") or 0),
        "completion_tokens": int(turn_usage.get("completion_tokens") or 0),
        "reasoning_tokens": int(turn_usage.get("reasoning_tokens") or 0),
        "total_tokens": int(turn_usage.get("total_tokens") or 0),
        "input_cache_hit_tokens": int(turn_usage.get("input_cache_hit_tokens") or 0),
        "input_cache_miss_tokens": int(turn_usage.get("input_cache_miss_tokens") or 0),
    }
    if not prepared:
        return recorded
    est = estimate_turn_tokens(
        prepared,
        (stream_text or {}).get("output") or "",
        (stream_text or {}).get("reasoning") or "",
        api_model,
    )
    if not recorded.get("input_cache_hit_tokens") and not recorded.get(
        "input_cache_miss_tokens"
    ):
        recorded["input_cache_hit_tokens"] = 0
        recorded["input_cache_miss_tokens"] = recorded["prompt_tokens"]
    return {
        "prompt_tokens": max(
            recorded["prompt_tokens"], int(est.get("prompt_tokens") or 0)
        ),
        "completion_tokens": max(
            recorded["completion_tokens"], int(est.get("completion_tokens") or 0)
        ),
        "reasoning_tokens": max(
            recorded["reasoning_tokens"], int(est.get("reasoning_tokens") or 0)
        ),
        "total_tokens": max(recorded["total_tokens"], int(est.get("total_tokens") or 0)),
        "input_cache_hit_tokens": recorded["input_cache_hit_tokens"],
        "input_cache_miss_tokens": recorded["input_cache_miss_tokens"],
    }


def record_chat_usage(
    username,
    token_usage=None,
    model=None,
    tool_cost_usd=0.0,
    billing_event_id=None,
):
    request_id = (billing_event_id or "").strip()
    with billing_lock():
        users = load_users()
        record = users.setdefault(username, {})
        pool = usage_pool_for_record(record)
        usage = pool["usage"]
        ents = pool["active_entitlements"]
        token_usage = token_usage or empty_usage()

        config = load_system_config()
        model_id = model or get_default_model_id(config)
        models = config.get("models") or {}
        entry = models.get(model_id) or normalize_model_entry(model_id, {})
        turn_cost = compute_turn_price_usd(token_usage, entry)
        billable = turn_cost + max(0.0, float(tool_cost_usd or 0))
        budget = pool["ai_budget_usd"]
        plan_portion = 0.0
        on_demand_portion = 0.0

        if request_id:
            commit_usage_reserve(record, request_id)

        if record.get("role") == "admin" or budget is None:
            plan_portion = billable
            if ents:
                _, _, ent_usage = allocate_usd_across_entitlements(
                    billable, usage, ents
                )
                usage["entitlement_usage"] = ent_usage
                usage["usage_cost_usd"] = entitlement_pool_used_usd(usage, ents)
            else:
                usage["usage_cost_usd"] = round(
                    float(usage.get("usage_cost_usd") or 0) + billable, 6
                )
        else:
            plan_portion, on_demand_portion, ent_usage = (
                allocate_usd_across_entitlements(billable, usage, ents)
            )
            usage["entitlement_usage"] = ent_usage
            usage["usage_cost_usd"] = entitlement_pool_used_usd(usage, ents)
            if on_demand_portion > 0 and user_on_demand_billing_enabled(record):
                jpy_cost = usd_usage_cost_to_jpy(on_demand_portion)
                balance = user_balance(record)
                if jpy_cost > balance:
                    jpy_cost = int(balance)
                record["balance"] = round(max(0.0, balance - jpy_cost), 2)
                usage["on_demand_cost_usd"] = round(
                    float(usage.get("on_demand_cost_usd") or 0) + on_demand_portion, 6
                )

        if tool_cost_usd:
            usage["tool_usage_cost_usd"] = round(
                float(usage.get("tool_usage_cost_usd") or 0) + float(tool_cost_usd), 6
            )

        record["usage"] = usage
        users[username] = record
        save_users(users)
    record_model_usage(model_id, token_usage)

    if billing_event_id:
        billing_plan = event_billing_plan_label(
            record, plan_portion, on_demand_portion
        )
        if record.get("role") == "admin" or budget is None:
            payment_type = "included"
        elif on_demand_portion > 0:
            payment_type = "metered"
        else:
            payment_type = "subscription"
        update_billing_event(
            billing_event_id,
            cost_usd=billable,
            token_usage=token_usage,
            model_id=model_id,
            billing_plan=billing_plan,
            payment_type=payment_type,
            cost_plan_usd=plan_portion,
            cost_on_demand_usd=on_demand_portion,
        )
    return billable


def find_user_for_paypal_subscription(users, custom_id, email, subscription_id=None):
    custom_id = (custom_id or "").strip().lower()
    email = (email or "").strip().lower()
    subscription_id = (subscription_id or "").strip()
    if custom_id and custom_id in users:
        return custom_id
    if subscription_id:
        for uname, rec in users.items():
            if (rec.get("paypal_subscription_id") or "").strip() == subscription_id:
                return uname
    if email:
        matches = [
            uname
            for uname, rec in users.items()
            if normalize_email(rec.get("email")).lower() == email
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def apply_paypal_subscription_activation(
    record, nexgate_plan_id, subscription_id, billing_plan_id
):
    plan = normalize_plan(nexgate_plan_id)
    if plan in ("free", "enterprise") or plan not in PLANS:
        return False
    record["plan"] = plan
    record["plan_expires_at"] = ""
    ents = [
        e
        for e in normalize_entitlements(
            record.get("entitlements"), plan_monthly_ai_budget_usd
        )
        if e.get("source") != "paypal"
    ]
    ents.append(
        normalize_entitlement(
            {
                "id": str(uuid.uuid4()),
                "plan_id": plan,
                "quantity": 1,
                "starts_at": format_datetime_iso(datetime.now()),
                "expires_at": "",
                "source": "paypal",
            },
            plan_monthly_ai_budget_usd,
        )
    )
    record["entitlements"] = ents
    record["paypal_subscription_id"] = (subscription_id or "").strip()
    record["paypal_billing_plan_id"] = (billing_plan_id or "").strip()
    record["paypal_subscription_status"] = "ACTIVE"
    record["paypal_subscription_updated_at"] = datetime.now().isoformat(
        timespec="seconds"
    )
    return True


def apply_paypal_subscription_deactivation(record):
    if record.get("role") == "admin":
        return True
    ents = normalize_entitlements(
        record.get("entitlements"), plan_monthly_ai_budget_usd
    )
    record["entitlements"] = [e for e in ents if e.get("source") != "paypal"]
    sync_record_plan_state(
        record,
        plan_monthly_ai_budget_usd,
        normalize_plan,
        plan_tier_rank_fn=plan_tier_rank,
    )
    record["paypal_subscription_status"] = "CANCELLED"
    record["paypal_subscription_updated_at"] = datetime.now().isoformat(
        timespec="seconds"
    )
    return True


def process_paypal_subscription_webhook_event(event):
    event_id = (event.get("id") or "").strip()
    if event_id and webhook_event_seen(event_id):
        return True, "already_processed"

    event_type = (event.get("event_type") or "").strip()
    resource = event.get("resource") or {}
    info = parse_subscription_resource(resource)
    subscription_id = info.get("subscription_id")
    if not subscription_id:
        if event_id:
            mark_webhook_event_seen(event_id)
        return True, "ignored_non_subscription"

    action = subscription_event_action(event_type, info.get("status"))
    if not action:
        if event_id:
            mark_webhook_event_seen(event_id)
        return True, "ignored_event_type"

    users = load_users()
    username = find_user_for_paypal_subscription(
        users,
        info.get("custom_id"),
        info.get("subscriber_email"),
        subscription_id,
    )
    if not username:
        if event_id:
            mark_webhook_event_seen(event_id)
        return False, "user_not_found"

    record = users[username]
    if action == "activate":
        plan_id = info.get("nexgate_plan_id")
        if not plan_id:
            if event_id:
                mark_webhook_event_seen(event_id)
            return False, "plan_not_mapped"
        if not apply_paypal_subscription_activation(
            record,
            plan_id,
            subscription_id,
            info.get("billing_plan_id"),
        ):
            if event_id:
                mark_webhook_event_seen(event_id)
            return False, "activation_failed"
    else:
        apply_paypal_subscription_deactivation(record)

    save_users(users)
    if event_id:
        mark_webhook_event_seen(event_id)
    return True, action


def build_billing_summary(username):
    users = load_users()
    record = users.get(username, {})
    plan = normalize_plan(record.get("plan"))
    usage = get_user_usage(username)

    catalog = get_plan_catalog()
    subscription_urls = get_plan_subscription_urls()
    current_rank = plan_tier_rank(plan)
    lang = (record.get("language") or "ja").strip().lower()
    if lang not in ("ja", "en", "ko"):
        lang = "ja"
    usage_info = usage_summary_for_record(record, lang)
    plans = []
    for key in PLAN_ORDER:
        info = catalog[key]
        rank = plan_tier_rank(key)
        paypal_url = subscription_urls.get(key, "")
        is_enterprise = key == "enterprise"
        is_clickable = (
            not is_enterprise
            and key != "free"
            and rank > current_rank
        )
        charge_jpy = plan_charge_jpy(key) if is_clickable else None
        user_bal = user_balance(record)
        ja_desc = info.get("description_ja", "")
        en_desc = info.get("description_en", "")
        plans.append(
            {
                "id": key,
                "name": info["name"],
                "price_label": info["price_label"],
                "price_jpy": charge_jpy,
                "price_jpy_label": format_balance_jpy(charge_jpy)
                if charge_jpy is not None
                else "",
                "balance_sufficient": charge_jpy is not None
                and user_bal >= charge_jpy,
                "description": plan_description_for_language(ja_desc, en_desc, lang),
                "description_ja": ja_desc,
                "description_en": en_desc,
                "is_current": key == plan,
                "tier_rank": rank,
                "paypal_url": paypal_url,
                "is_clickable": is_clickable,
                "is_enterprise": is_enterprise,
            }
        )

    pinfo = catalog[plan]
    pinfo_ja = pinfo.get("description_ja", "")
    pinfo_en = pinfo.get("description_en", "")
    expires_raw = record.get("plan_expires_at", "")
    return {
        "plan": plan,
        "plan_name": pinfo["name"],
        "plan_price_label": pinfo["price_label"],
        "plan_description": plan_description_for_language(pinfo_ja, pinfo_en, lang),
        "balance": user_balance(record),
        "plan_expires_at": expires_raw,
        "plan_expires_label": format_plan_expires_label(expires_raw),
        "usage_reset_label": format_usage_reset_label(plan, expires_raw, lang),
        "usage_pool_expires_at": usage_info.get("usage_pool_expires_at") or "",
        "usage_pool_expires_label": format_plan_expires_label(
            usage_info.get("usage_pool_expires_at") or ""
        ),
        "active_entitlements": usage_info.get("active_entitlements") or [],
        "billing_model_note": billing_model_note(lang),
        "period": usage.get("period", current_usage_period()),
        "usage_cost_usd": usage_info["usage_cost_usd"],
        "ai_budget_usd": usage_info["ai_budget_usd"],
        "usage_percent": usage_info["usage_percent"],
        "usage_unlimited": usage_info["usage_unlimited"],
        "usage_display_label": usage_info["usage_display_label"],
        "usage_status": usage_info["usage_status"],
        "usage_is_over_limit": usage_info["usage_is_over_limit"],
        "usage_warning": usage_info["usage_warning"],
        "on_demand_billing_enabled": user_on_demand_billing_enabled(record),
        "on_demand_cost_usd": float(usage.get("on_demand_cost_usd") or 0),
        "billing_currency": normalize_billing_currency(record.get("billing_currency")),
        "plans": plans,
        "plan_tier_rank": current_rank,
        "balance_currency": BALANCE_CURRENCY,
        "balance_label": format_balance_jpy(user_balance(record)),
        "min_topup_jpy": MIN_TOPUP_JPY,
        "usd_jpy_rate": get_usd_jpy_rate(),
        "paypal": paypal_public_config(),
        "features": get_feature_flags(),
    }


SUPPORTED_BILLING_CURRENCIES = frozenset({"JPY", "USD", "EUR", "KRW"})


def default_billing():
    return {"name": "", "postal_code": "", "address": "", "country": ""}


def normalize_billing_currency(value):
    code = (value or "JPY").strip().upper()
    return code if code in SUPPORTED_BILLING_CURRENCIES else "JPY"


def user_on_demand_billing_enabled(record):
    if not record:
        return False
    if record.get("role") == "admin":
        return True
    return bool(record.get("on_demand_billing_enabled"))


def usd_usage_cost_to_jpy(cost_usd, rate=None):
    try:
        usd = max(0.0, float(cost_usd or 0))
    except (TypeError, ValueError):
        return 0
    fx = float(rate if rate is not None else get_usd_jpy_rate())
    return max(0, int(round(usd * fx)))


def event_billing_plan_label(record, plan_portion_usd, on_demand_portion_usd):
    if float(on_demand_portion_usd or 0) > 0:
        return "on-demand"
    if float(plan_portion_usd or 0) <= 0:
        return ""
    plan = effective_plan_for_features(record)
    return get_plan_info(plan).get("name") or plan


def user_web_search_enabled(record):
    if not record:
        return True
    plan = normalize_plan(record.get("plan"))
    if not plan_web_search_enabled(plan):
        return False
    if "web_search_enabled" in record:
        return bool(record.get("web_search_enabled"))
    return True


def user_geolocation_enabled(record):
    if not record:
        return False
    plan = normalize_plan(record.get("plan"))
    if not plan_geolocation_enabled(plan):
        return False
    if "geolocation_enabled" in record:
        return bool(record.get("geolocation_enabled"))
    return False


def user_user_questions_enabled(record):
    if not record:
        return False
    return bool(record.get("user_questions_enabled"))


def user_tasks_enabled(record):
    if not record:
        return False
    plan = normalize_plan(record.get("plan"))
    if not plan_tasks_enabled(plan):
        return False
    if "tasks_enabled" in record:
        return bool(record.get("tasks_enabled"))
    return False


def user_memory_enabled(record):
    if not record:
        return False
    plan = normalize_plan(record.get("plan"))
    if not plan_memory_enabled(plan):
        return False
    if "memory_enabled" in record:
        return bool(record.get("memory_enabled"))
    return False


def user_projects_enabled(record):
    if not record:
        return False
    plan = normalize_plan(record.get("plan"))
    if not plan_projects_enabled(plan):
        return False
    if "projects_enabled" in record:
        return bool(record.get("projects_enabled"))
    return False


def user_deep_research_enabled(record):
    if not record:
        return False
    plan = normalize_plan(record.get("plan"))
    if not plan_deep_research_enabled(plan):
        return False
    if "deep_research_enabled" in record:
        return bool(record.get("deep_research_enabled"))
    return False


def user_intelligent_search_override_enabled(record):
    if not record:
        return False
    if not user_web_search_enabled(record):
        return False
    return resolve_user_intelligent_search_override_enabled(record)


def user_info_expert_enabled(record):
    if not record:
        return False
    return bool(record.get("info_expert_enabled"))


def user_image_generation_enabled(record):
    if not record:
        return False
    plan = normalize_plan(record.get("plan"))
    if not plan_image_generation_enabled(plan):
        return False
    if "image_generation_enabled" in record:
        return bool(record.get("image_generation_enabled"))
    return False


def get_user_image_generation_prefs(record, plan_key=None):
    plan = normalize_plan((record or {}).get("plan") if plan_key is None else plan_key)
    config = load_system_config()
    raw = (record or {}).get("image_generation_prefs")
    if not isinstance(raw, dict):
        raw = {
            "model_id": (record or {}).get("image_generation_model_id"),
            "width": (record or {}).get("image_generation_width"),
            "height": (record or {}).get("image_generation_height"),
            "size_preset": (record or {}).get("image_generation_size_preset"),
        }
    return normalize_user_image_generation_prefs(
        raw, plan_key=plan, image_generation=config.get("image_generation")
    )


def user_file_upload_enabled(record):
    if not record:
        return False
    if (record.get("role") or "").strip().lower() == "admin":
        return True
    if feature_blocked("upload_disabled"):
        return False
    plan = normalize_plan(record.get("plan"))
    return plan_file_upload_enabled(plan)


def user_ocr_enabled(record):
    if not record:
        return False
    if record.get("role") == "admin":
        return True
    if feature_blocked("upload_disabled"):
        return False
    plan = normalize_plan(record.get("plan"))
    return plan_ocr_enabled(plan)


def user_reasoning_cards_enabled(record):
    if not record:
        return False
    if record.get("role") == "admin":
        return True
    plan = normalize_plan(record.get("plan"))
    if not plan_reasoning_cards_enabled(plan):
        return False
    if "reasoning_cards_enabled" in record:
        return bool(record.get("reasoning_cards_enabled"))
    return False


def user_tool_trace_enabled(record):
    if not record:
        return False
    if record.get("role") == "admin":
        return True
    plan = normalize_plan(record.get("plan"))
    if not plan_tool_trace_enabled(plan):
        return False
    return bool(record.get("tool_trace_enabled"))


def user_full_info_display_enabled(record):
    if not record:
        return False
    plan = normalize_plan(record.get("plan"))
    if not plan_full_info_display_enabled(plan):
        return False
    return bool(record.get("full_info_display_enabled"))


def user_expression_extension_enabled(record):
    if not record:
        return False
    return bool(record.get("expression_extension_enabled"))


def user_custom_agents_enabled(record):
    if not record:
        return False
    plan = effective_plan_for_features(record)
    return plan_custom_agents_enabled(plan)


def user_chat_share_enabled(record):
    if not record:
        return False
    if record.get("role") == "admin":
        return True
    plan = normalize_plan(record.get("plan"))
    return plan_chat_share_enabled(plan)


def user_reasoning_disabled(record):
    if not record:
        return False
    return bool(record.get("reasoning_disabled"))


def user_cost_performance_maximized(record):
    if not record:
        return False
    return bool(record.get("cost_performance_maximized"))


def user_reasoning_in_english(record):
    if not record:
        return False
    return bool(record.get("reasoning_in_english"))


def effective_reasoning_in_english(record, provider_id=None, disable_reasoning=None):
    if not user_reasoning_in_english(record):
        return False
    if disable_reasoning if disable_reasoning is not None else user_reasoning_disabled(record):
        return False
    from model_registry import provider_supports_thinking

    if not provider_supports_thinking(provider_id):
        return False
    return True


def user_google_calendar_enabled(record, username=None):
    if not record:
        return False
    uname = (username or "").strip().lower()
    if not uname or not user_google_connected(uname):
        return False
    if not user_google_plan_calendar_allowed(record):
        return False
    return bool(record.get("google_calendar_enabled"))


def user_google_gmail_enabled(record, username=None):
    if not record:
        return False
    uname = (username or "").strip().lower()
    if not uname or not user_google_connected(uname):
        return False
    if not user_google_plan_gmail_allowed(record):
        return False
    return bool(record.get("google_gmail_enabled"))


def system_google_login_allowed():
    return google_oauth_configured() and not feature_blocked("google_login_disabled")


def user_google_login_enabled(record):
    return bool(record.get("google_login_enabled"))


def user_google_login_linked(record):
    return bool((record.get("google_sub") or "").strip())


def find_user_by_google_sub(users, google_sub):
    sub = (google_sub or "").strip()
    if not sub:
        return None, None
    for username, record in users.items():
        if (record.get("google_sub") or "").strip() == sub:
            return username, record
    return None, None


def find_user_by_google_email(users, email):
    normalized = normalize_email(email)
    if not normalized:
        return None, None
    for username, record in users.items():
        if normalize_email(record.get("google_email")) == normalized:
            return username, record
        if normalize_email(record.get("email")) == normalized:
            return username, record
    return None, None


def derive_username_from_google_email(email, users):
    local = normalize_email(email).split("@")[0].lower()
    base = re.sub(r"[^a-z0-9_-]", "", local) or "user"
    if len(base) < 3:
        base = f"{base}00"[:32]
    base = base[:32]
    if base not in users and validate_new_username(base) is None:
        return base
    for i in range(1, 1000):
        suffix = str(i)
        candidate = f"{base[: 32 - len(suffix)]}{suffix}"
        if candidate not in users and validate_new_username(candidate) is None:
            return candidate
    raise RuntimeError("Could not derive username")


def create_google_user_record(*, display_name, email, google_sub, google_email):
    users = load_users()
    username = derive_username_from_google_email(email, users)
    password = secrets.token_urlsafe(32)
    record = create_user_record(
        password,
        display_name=display_name,
        email=email,
    )
    record["google_login_enabled"] = True
    record["google_sub"] = google_sub
    record["google_email"] = normalize_email(google_email)
    return username, record


def serialize_google_integration(username, record):
    connected = user_google_connected(username)
    return {
        "configured": google_oauth_configured(),
        "connected": connected,
        "google_calendar_enabled": user_google_calendar_enabled(record, username),
        "google_gmail_enabled": user_google_gmail_enabled(record, username),
        "plan_google_calendar": user_google_plan_calendar_allowed(record),
        "plan_google_gmail": user_google_plan_gmail_allowed(record),
        "user_calendar_toggle": bool(record.get("google_calendar_enabled")),
        "user_gmail_toggle": bool(record.get("google_gmail_enabled")),
        "google_login_enabled": user_google_login_enabled(record),
        "google_login_linked": user_google_login_linked(record),
        "google_email": normalize_email(record.get("google_email")),
        "system_google_login_allowed": system_google_login_allowed(),
    }


def system_discord_login_allowed():
    return discord_oauth_configured() and not feature_blocked("discord_login_disabled")


def user_discord_login_enabled(record):
    return bool(record.get("discord_login_enabled"))


def user_discord_login_linked(record):
    return bool((record.get("discord_id") or "").strip())


def find_user_by_discord_id(users, discord_id):
    did = (discord_id or "").strip()
    if not did:
        return None, None
    for username, record in users.items():
        if (record.get("discord_id") or "").strip() == did:
            return username, record
    return None, None


def find_user_by_discord_email(users, email):
    normalized = normalize_email(email)
    if not normalized:
        return None, None
    for username, record in users.items():
        if normalize_email(record.get("email")) == normalized:
            return username, record
    return None, None


def derive_username_from_discord_email(email, users):
    return derive_username_from_google_email(email, users)


def create_discord_user_record(*, display_name, email, discord_id, discord_username):
    users = load_users()
    username = derive_username_from_discord_email(email, users)
    password = secrets.token_urlsafe(32)
    record = create_user_record(
        password,
        display_name=display_name,
        email=email,
    )
    record["discord_login_enabled"] = True
    record["discord_id"] = discord_id
    record["discord_username"] = (discord_username or "").strip()
    return username, record


def serialize_discord_integration(record):
    linked = user_discord_login_linked(record)
    return {
        "configured": discord_oauth_configured(),
        "connected": linked,
        "discord_login_enabled": user_discord_login_enabled(record),
        "discord_login_linked": linked,
        "discord_username": (record.get("discord_username") or "").strip(),
        "system_discord_login_allowed": system_discord_login_allowed(),
    }


def user_computelab_tools_enabled(record, username=None):
    uname = (username or "").strip().lower()
    if not uname:
        return False
    if not user_computelab_connected(uname):
        return False
    plan = normalize_plan((record or {}).get("plan"))
    if not plan_computelab_enabled(plan):
        return False
    return bool(record.get("computelab_tools_enabled"))


def serialize_computelab_integration(username, record):
    connected = user_computelab_connected(username)
    return {
        "connected": connected,
        "key_prefix": get_computelab_key_prefix(username) if connected else "",
        "computelab_tools_enabled": user_computelab_tools_enabled(record, username),
        "user_tools_toggle": bool(record.get("computelab_tools_enabled")),
    }


def normalize_billing(raw):
    if not isinstance(raw, dict):
        raw = {}
    return {
        "name": (raw.get("name") or "").strip(),
        "postal_code": (raw.get("postal_code") or "").strip(),
        "address": (raw.get("address") or "").strip(),
        "country": (raw.get("country") or "").strip()[:64],
    }


def normalize_email(email):
    return (email or "").strip()


def normalize_phone(phone):
    return (phone or "").strip()


def normalize_chat_background_pattern(value):
    pattern = (value or "simple").strip().lower()
    return pattern if pattern in ("simple", "grid") else "simple"


def is_valid_email(email):
    if not email:
        return True
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def find_user_by_email(users, email):
    key = normalize_email(email).lower()
    if not key or "@" not in key:
        return None, None
    for username, record in users.items():
        if normalize_email(record.get("email")).lower() == key:
            return username, record
    return None, None


def create_user_from_pending_registration(pending):
    record = create_user_record(
        secrets.token_urlsafe(32),
        display_name=pending.get("display_name"),
        email=pending.get("email"),
        phone=pending.get("phone"),
    )
    record["password_hash"] = pending.get("password_hash") or record["password_hash"]
    record["billing"] = normalize_billing(pending.get("billing"))
    record["email_verified"] = True
    return record


def user_balance(record):
    try:
        return round(float(record.get("balance", 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def format_balance_jpy(amount):
    value = int(round(float(amount)))
    return f"¥{value:,}"


def payment_already_recorded(record, payment_id):
    pid = (payment_id or "").strip()
    if not pid:
        return False
    for item in normalize_payment_records(record.get("payment_records")):
        if item.get("id") == pid:
            return True
    return False


def append_balance_topup(record, amount_jpy, paypal_order_id, capture_id=None):
    payment_id = (capture_id or paypal_order_id or "").strip()
    if payment_already_recorded(record, payment_id):
        return False, user_balance(record)

    records = normalize_payment_records(record.get("payment_records"))
    records.append(
        {
            "id": payment_id,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": int(amount_jpy),
            "method": "PayPal",
            "note": f"残高チャージ（{paypal_order_id[:12]}）",
            "status": "paid",
        }
    )
    record["payment_records"] = records
    record["balance"] = round(user_balance(record) + float(amount_jpy), 2)
    return True, record["balance"]


def is_user_blocked(record):
    return bool(record.get("blocked"))


def normalize_real_name_field(value):
    return (value or "").strip()[:64]


def normalize_plan_expires_at(value):
    text = (value or "").strip()
    if not text:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return f"{text}T23:59:59"
    return text[:19]


def format_plan_expires_label(value):
    from coupons import parse_datetime_value

    dt = parse_datetime_value(value)
    if not dt:
        return "—"
    return dt.strftime("%Y/%m/%d %H:%M")


def format_usage_reset_label(plan, expires_raw, lang="ja"):
    from coupons import parse_datetime_value

    if normalize_plan(plan) == "free":
        return ""
    dt = parse_datetime_value(expires_raw)
    if not dt:
        return ""
    if lang == "en":
        return f"Resets {dt.strftime('%b')} {dt.day}"
    if lang == "ko":
        return f"{dt.month}월 {dt.day}일에 리셋"
    return f"{dt.month}月{dt.day}日にリセット"


def normalize_payment_records(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:100]:
        if not isinstance(item, dict):
            continue
        rec_id = (item.get("id") or "").strip() or str(uuid.uuid4())
        try:
            amount = round(float(item.get("amount", 0)), 2)
        except (TypeError, ValueError):
            amount = 0.0
        status = (item.get("status") or "paid").strip().lower()
        if status not in ("paid", "pending", "refunded", "failed"):
            status = "paid"
        out.append(
            {
                "id": rec_id,
                "date": normalize_plan_expires_at(item.get("date")),
                "amount": amount,
                "method": (item.get("method") or "").strip()[:64],
                "note": (item.get("note") or "").strip()[:240],
                "status": status,
            }
        )
    return out


def user_full_name(record):
    last = normalize_real_name_field(record.get("last_name"))
    first = normalize_real_name_field(record.get("first_name"))
    if last or first:
        return f"{last} {first}".strip()
    return record.get("display_name", "")


def admin_user_billing_kind(record):
    sub_status = (record.get("paypal_subscription_status") or "").strip().upper()
    sub_id = (record.get("paypal_subscription_id") or "").strip()
    if sub_id and sub_status == "ACTIVE":
        return {
            "kind": "paypal_subscription",
            "label": "PayPalサブスク",
            "status": sub_status,
        }
    ents = active_entitlements(record, plan_budget_fn=plan_monthly_ai_budget_usd)
    if any((e.get("source") or "") == "paypal" for e in ents):
        return {
            "kind": "paypal_subscription",
            "label": "PayPalサブスク",
            "status": sub_status or "ACTIVE",
        }
    if ents:
        sources = {(e.get("source") or "").strip() for e in ents}
        if "admin" in sources:
            return {"kind": "admin_grant", "label": "管理者付与", "status": ""}
        if sources & {"balance", "coupon"}:
            return {"kind": "balance", "label": "残高プラン", "status": ""}
        return {"kind": "entitlement", "label": "プラン枠", "status": ""}
    plan = normalize_plan(record.get("plan"))
    if plan != "free":
        return {"kind": "legacy_plan", "label": "レガシー", "status": ""}
    return {"kind": "free", "label": "無料", "status": ""}


def admin_user_billing_payload(record):
    kind = admin_user_billing_kind(record)
    sub_id = (record.get("paypal_subscription_id") or "").strip()
    billing_plan_id = (record.get("paypal_billing_plan_id") or "").strip()
    return {
        **kind,
        "paypal_subscription_id": sub_id,
        "paypal_billing_plan_id": billing_plan_id,
        "paypal_subscription_status": (
            record.get("paypal_subscription_status") or ""
        ).strip(),
        "paypal_subscription_updated_at": (
            record.get("paypal_subscription_updated_at") or ""
        ).strip(),
        "api_enabled": bool(record.get("api_enabled")),
        "api_access_allowed": user_api_access_enabled(record),
        "stored_plan": normalize_plan(record.get("plan")),
    }


def serialize_admin_user(username, record, detailed=False):
    pool = usage_pool_for_record(record)
    usage = pool["usage"]
    plan = effective_plan_for_features(record)
    pinfo = get_plan_info(plan)
    usage_info = usage_summary_for_record(record)
    override = record.get("usage_quota_override_usd")
    payload = {
        "username": username,
        "display_name": record.get("display_name", username),
        "last_name": normalize_real_name_field(record.get("last_name")),
        "first_name": normalize_real_name_field(record.get("first_name")),
        "full_name": user_full_name(record),
        "role": record.get("role", "user"),
        "plan": plan,
        "plan_name": pinfo["name"],
        "plan_price_label": pinfo["price_label"],
        "balance": user_balance(record),
        "created_at": record.get("created_at", ""),
        "plan_expires_at": normalize_plan_expires_at(record.get("plan_expires_at")),
        "blocked": is_user_blocked(record),
        "email": normalize_email(record.get("email")),
        "phone": normalize_phone(record.get("phone")),
        "usage": {
            "period": usage.get("period", current_usage_period()),
            "usage_cost_usd": usage_info["usage_cost_usd"],
            "tool_usage_cost_usd": usage_info["tool_usage_cost_usd"],
        },
        "monthly_ai_budget_usd": usage_info["ai_budget_usd"],
        "usage_percent": usage_info["usage_percent"],
        "usage_quota_override_usd": override,
        "usage_pool_expires_at": usage_info.get("usage_pool_expires_at") or "",
        "entitlements": usage_info.get("active_entitlements") or [],
        "billing": admin_user_billing_payload(record),
    }
    if detailed:
        payload["billing_address"] = normalize_billing(record.get("billing"))
        payload["payment_records"] = normalize_payment_records(
            record.get("payment_records")
        )
        payload["all_entitlements"] = normalize_entitlements(
            record.get("entitlements"), plan_monthly_ai_budget_usd
        )
    return payload


def add_plan_coupon_hours(record, plan_id, hours, source="coupon"):
    ent = add_plan_entitlement(
        record,
        plan_id,
        hours=hours,
        source=source,
        plan_budget_fn=plan_monthly_ai_budget_usd,
        normalize_plan_fn=normalize_plan,
        plan_tier_rank_fn=plan_tier_rank,
    )
    return ent


def build_session_user(username, record):
    plan = effective_plan_for_features(record)
    plan_info = get_plan_info(plan)
    plan_feat = get_plan_features(plan)
    billing = normalize_billing(record.get("billing"))
    lang = (record.get("language") or "ja").strip().lower()
    if lang not in ("ja", "en", "ko"):
        lang = "ja"
    usage_info = usage_summary_for_record(record, lang)
    return {
        "username": username,
        "display_name": record.get("display_name", username),
        "role": record.get("role", "user"),
        "theme": record.get("theme", "dark"),
        "chat_background_pattern": normalize_chat_background_pattern(
            record.get("chat_background_pattern")
        ),
        "language": record.get("language", "ja"),
        "email": normalize_email(record.get("email")),
        "phone": normalize_phone(record.get("phone")),
        "billing": billing,
        "web_search_enabled": user_web_search_enabled(record),
        "geolocation_enabled": user_geolocation_enabled(record),
        "user_questions_enabled": user_user_questions_enabled(record),
        "tasks_enabled": user_tasks_enabled(record),
        "memory_enabled": user_memory_enabled(record),
        "projects_enabled": user_projects_enabled(record),
        "deep_research_enabled": user_deep_research_enabled(record),
        "deep_research_prefs": get_user_deep_research_prefs(record),
        "plan_deep_research_enabled": plan_deep_research_enabled(plan),
        "intelligent_search_override_enabled": user_intelligent_search_override_enabled(record),
        "info_expert_enabled": user_info_expert_enabled(record),
        "image_generation_enabled": user_image_generation_enabled(record),
        "image_generation_prefs": get_user_image_generation_prefs(record),
        "file_upload_enabled": user_file_upload_enabled(record),
        "ocr_enabled": user_ocr_enabled(record),
        "reasoning_cards_enabled": user_reasoning_cards_enabled(record),
        "tool_trace_enabled": user_tool_trace_enabled(record),
        "full_info_display_enabled": user_full_info_display_enabled(record),
        "expression_extension_enabled": user_expression_extension_enabled(record),
        "plan_full_info_display_enabled": plan_full_info_display_enabled(plan),
        "reasoning_disabled": user_reasoning_disabled(record),
        "cost_performance_maximized": user_cost_performance_maximized(record),
        "reasoning_in_english": user_reasoning_in_english(record),
        "plan": plan,
        "plan_chat_enabled": bool(plan_feat.get("chat_enabled", True)),
        "plan_name": plan_info["name"],
        "plan_price_label": plan_info["price_label"],
        "balance": user_balance(record),
        "usage_percent": usage_info["usage_percent"],
        "usage_unlimited": usage_info["usage_unlimited"],
        "usage_display_label": usage_info["usage_display_label"],
        "usage_status": usage_info["usage_status"],
        "usage_is_over_limit": usage_info["usage_is_over_limit"],
        "usage_warning": usage_info["usage_warning"],
        "google_connected": user_google_connected(username),
        "google_calendar_enabled": user_google_calendar_enabled(record, username),
        "google_gmail_enabled": user_google_gmail_enabled(record, username),
        "google_oauth_configured": google_oauth_configured(),
        "plan_google_calendar": user_google_plan_calendar_allowed(record),
        "plan_google_gmail": user_google_plan_gmail_allowed(record),
        "google_login_enabled": user_google_login_enabled(record),
        "google_login_linked": user_google_login_linked(record),
        "google_email": normalize_email(record.get("google_email")),
        "system_google_login_allowed": system_google_login_allowed(),
        "discord_login_enabled": user_discord_login_enabled(record),
        "discord_login_linked": user_discord_login_linked(record),
        "discord_username": (record.get("discord_username") or "").strip(),
        "discord_oauth_configured": discord_oauth_configured(),
        "system_discord_login_allowed": system_discord_login_allowed(),
        "computelab_connected": user_computelab_connected(username),
        "computelab_tools_enabled": user_computelab_tools_enabled(record, username),
        "computelab_key_prefix": get_computelab_key_prefix(username),
        "api_enabled": bool(record.get("api_enabled")),
        "on_demand_billing_enabled": user_on_demand_billing_enabled(record),
        "billing_currency": normalize_billing_currency(record.get("billing_currency")),
        "last_name": normalize_real_name_field(record.get("last_name")),
        "first_name": normalize_real_name_field(record.get("first_name")),
        "plan_api_access_enabled": plan_api_access_enabled(
            effective_plan_for_features(record)
        ),
        "api_access_active": user_api_access_enabled(record),
        "custom_agents_enabled": user_custom_agents_enabled(record),
    }


def normalize_session_user(user):
    if not user:
        return None
    patched = dict(user)
    patched["billing"] = normalize_billing(patched.get("billing"))
    patched["email"] = normalize_email(patched.get("email"))
    patched["phone"] = normalize_phone(patched.get("phone"))
    if "balance" not in patched:
        patched["balance"] = 0.0
    plan = normalize_plan(patched.get("plan"))
    patched["plan"] = plan
    patched.setdefault("usage_percent", 0)
    patched.setdefault("usage_unlimited", False)
    patched.setdefault("usage_display_label", "")
    patched.setdefault("usage_status", "normal")
    patched.setdefault("usage_is_over_limit", False)
    if "web_search_enabled" not in patched:
        patched["web_search_enabled"] = True
    if "geolocation_enabled" not in patched:
        patched["geolocation_enabled"] = False
    if "user_questions_enabled" not in patched:
        patched["user_questions_enabled"] = False
    if "tasks_enabled" not in patched:
        patched["tasks_enabled"] = False
    if "memory_enabled" not in patched:
        patched["memory_enabled"] = False
    if "projects_enabled" not in patched:
        patched["projects_enabled"] = False
    if "deep_research_enabled" not in patched:
        patched["deep_research_enabled"] = False
    if "intelligent_search_override_enabled" not in patched:
        patched["intelligent_search_override_enabled"] = False
    if "info_expert_enabled" not in patched:
        patched["info_expert_enabled"] = False
    if "deep_research_prefs" not in patched:
        patched["deep_research_prefs"] = get_user_deep_research_prefs(None)
    if "image_generation_enabled" not in patched:
        patched["image_generation_enabled"] = False
    if "image_generation_prefs" not in patched:
        patched["image_generation_prefs"] = {}
    if "file_upload_enabled" not in patched:
        patched["file_upload_enabled"] = True
    if "ocr_enabled" not in patched:
        patched["ocr_enabled"] = False
    if "reasoning_cards_enabled" not in patched:
        patched["reasoning_cards_enabled"] = False
    if "tool_trace_enabled" not in patched:
        patched["tool_trace_enabled"] = False
    if "full_info_display_enabled" not in patched:
        patched["full_info_display_enabled"] = False
    if "expression_extension_enabled" not in patched:
        patched["expression_extension_enabled"] = False
    if "reasoning_disabled" not in patched:
        patched["reasoning_disabled"] = False
    if "cost_performance_maximized" not in patched:
        patched["cost_performance_maximized"] = False
    if "reasoning_in_english" not in patched:
        patched["reasoning_in_english"] = False
    username = (patched.get("username") or "").strip().lower()
    if username:
        users = load_users()
        record = users.get(username, {})
        patched["ocr_enabled"] = user_ocr_enabled(record)
        patched["google_connected"] = user_google_connected(username)
        patched["google_calendar_enabled"] = user_google_calendar_enabled(
            record, username
        )
        patched["google_gmail_enabled"] = user_google_gmail_enabled(record, username)
        patched["google_oauth_configured"] = google_oauth_configured()
        patched["plan_google_calendar"] = user_google_plan_calendar_allowed(record)
        patched["plan_google_gmail"] = user_google_plan_gmail_allowed(record)
        patched["google_login_enabled"] = user_google_login_enabled(record)
        patched["google_login_linked"] = user_google_login_linked(record)
        patched["google_email"] = normalize_email(record.get("google_email"))
        patched["system_google_login_allowed"] = system_google_login_allowed()
        patched["discord_login_enabled"] = user_discord_login_enabled(record)
        patched["discord_login_linked"] = user_discord_login_linked(record)
        patched["discord_username"] = (record.get("discord_username") or "").strip()
        patched["discord_oauth_configured"] = discord_oauth_configured()
        patched["system_discord_login_allowed"] = system_discord_login_allowed()
        patched["computelab_connected"] = user_computelab_connected(username)
        patched["computelab_tools_enabled"] = user_computelab_tools_enabled(
            record, username
        )
        patched["computelab_key_prefix"] = get_computelab_key_prefix(username)
        patched["image_generation_enabled"] = user_image_generation_enabled(record)
        patched["image_generation_prefs"] = get_user_image_generation_prefs(record)
        lang = (patched.get("language") or "ja").strip().lower()
        if lang not in ("ja", "en", "ko"):
            lang = "ja"
        usage_info = usage_summary_for_record(record, lang)
        patched["usage_percent"] = usage_info["usage_percent"]
        patched["usage_unlimited"] = usage_info["usage_unlimited"]
        patched["usage_display_label"] = usage_info["usage_display_label"]
        patched["usage_status"] = usage_info["usage_status"]
        patched["usage_is_over_limit"] = usage_info["usage_is_over_limit"]
        patched["usage_warning"] = usage_info["usage_warning"]
        patched["api_enabled"] = bool(record.get("api_enabled"))
        patched["plan_api_access_enabled"] = plan_api_access_enabled(
            effective_plan_for_features(record)
        )
        patched["plan_full_info_display_enabled"] = plan_full_info_display_enabled(
            effective_plan_for_features(record)
        )
        patched["full_info_display_enabled"] = user_full_info_display_enabled(record)
        patched["api_access_active"] = user_api_access_enabled(record)
        patched["custom_agents_enabled"] = user_custom_agents_enabled(record)
    return patched


def refresh_session_user():
    user = session.get("user")
    if not user:
        return None
    users = load_users()
    username = (user.get("username") or "").strip().lower()
    record = users.get(username) if username else None
    if record:
        session["user"] = build_session_user(username, record)
    else:
        session["user"] = normalize_session_user(user)
    return session["user"]


def init_users():
    users = load_users()
    changed = False
    for username, spec in DEFAULT_USERS.items():
        if username not in users:
            users[username] = {
                "password_hash": generate_password_hash(spec["password"]),
                "display_name": spec["display_name"],
                "role": spec["role"],
                "theme": spec.get("theme", "dark"),
                "language": spec.get("language", "ja"),
                "plan": spec.get("plan", "plus"),
                "email": spec.get("email", ""),
                "phone": spec.get("phone", ""),
                "billing": normalize_billing(spec.get("billing")),
            }
            changed = True
    for username in users:
        if "theme" not in users[username]:
            users[username]["theme"] = "dark"
            changed = True
        if "chat_background_pattern" not in users[username]:
            users[username]["chat_background_pattern"] = "simple"
            changed = True
        if "language" not in users[username]:
            users[username]["language"] = "ja"
            changed = True
        if "web_search_enabled" not in users[username]:
            users[username]["web_search_enabled"] = True
            changed = True
        if "geolocation_enabled" not in users[username]:
            users[username]["geolocation_enabled"] = False
            changed = True
        if "user_questions_enabled" not in users[username]:
            users[username]["user_questions_enabled"] = False
            changed = True
        if "tasks_enabled" not in users[username]:
            users[username]["tasks_enabled"] = False
            changed = True
        if "memory_enabled" not in users[username]:
            users[username]["memory_enabled"] = False
            changed = True
        if "projects_enabled" not in users[username]:
            users[username]["projects_enabled"] = False
            changed = True
        if "deep_research_enabled" not in users[username]:
            users[username]["deep_research_enabled"] = False
            changed = True
        if "intelligent_search_override_enabled" not in users[username]:
            users[username]["intelligent_search_override_enabled"] = False
            changed = True
        if "info_expert_enabled" not in users[username]:
            users[username]["info_expert_enabled"] = False
            changed = True
        if "deep_research_prefs" not in users[username]:
            users[username]["deep_research_prefs"] = {}
            changed = True
        if "image_generation_enabled" not in users[username]:
            users[username]["image_generation_enabled"] = False
            changed = True
        if "image_generation_prefs" not in users[username]:
            users[username]["image_generation_prefs"] = {}
            changed = True
        if "reasoning_cards_enabled" not in users[username]:
            users[username]["reasoning_cards_enabled"] = False
            changed = True
        if "full_info_display_enabled" not in users[username]:
            users[username]["full_info_display_enabled"] = False
            changed = True
        if "expression_extension_enabled" not in users[username]:
            users[username]["expression_extension_enabled"] = False
            changed = True
        if "reasoning_disabled" not in users[username]:
            users[username]["reasoning_disabled"] = False
            changed = True
        if "cost_performance_maximized" not in users[username]:
            users[username]["cost_performance_maximized"] = False
            changed = True
        if "reasoning_in_english" not in users[username]:
            users[username]["reasoning_in_english"] = False
            changed = True
        if "google_calendar_enabled" not in users[username]:
            users[username]["google_calendar_enabled"] = False
            changed = True
        if "google_gmail_enabled" not in users[username]:
            users[username]["google_gmail_enabled"] = False
            changed = True
        if "google_login_enabled" not in users[username]:
            users[username]["google_login_enabled"] = False
            changed = True
        if "google_sub" not in users[username]:
            users[username]["google_sub"] = ""
            changed = True
        if "google_email" not in users[username]:
            users[username]["google_email"] = ""
            changed = True
        if "discord_login_enabled" not in users[username]:
            users[username]["discord_login_enabled"] = False
            changed = True
        if "discord_id" not in users[username]:
            users[username]["discord_id"] = ""
            changed = True
        if "discord_username" not in users[username]:
            users[username]["discord_username"] = ""
            changed = True
        if "computelab_tools_enabled" not in users[username]:
            users[username]["computelab_tools_enabled"] = False
            changed = True
        if "plan" not in users[username]:
            default_plan = "enterprise" if users[username].get("role") == "admin" else "free"
            users[username]["plan"] = default_plan
            changed = True
        else:
            normalized = normalize_plan(users[username]["plan"])
            if users[username]["plan"] != normalized:
                users[username]["plan"] = normalized
                changed = True
        if "usage" not in users[username]:
            users[username]["usage"] = normalize_user_usage({})
            changed = True
        else:
            normalized_usage = normalize_user_usage(users[username]["usage"])
            if users[username]["usage"] != normalized_usage:
                users[username]["usage"] = normalized_usage
                changed = True
        if "email" not in users[username]:
            users[username]["email"] = ""
            changed = True
        if "phone" not in users[username]:
            users[username]["phone"] = ""
            changed = True
        if "billing" not in users[username]:
            users[username]["billing"] = default_billing()
            changed = True
        else:
            normalized_billing = normalize_billing(users[username]["billing"])
            if users[username]["billing"] != normalized_billing:
                users[username]["billing"] = normalized_billing
                changed = True
        if "balance" not in users[username]:
            users[username]["balance"] = 0.0
            changed = True
        if "created_at" not in users[username]:
            users[username]["created_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
        if "last_name" not in users[username]:
            users[username]["last_name"] = ""
            changed = True
        if "first_name" not in users[username]:
            users[username]["first_name"] = ""
            changed = True
        if "plan_expires_at" not in users[username]:
            users[username]["plan_expires_at"] = ""
            changed = True
        if "blocked" not in users[username]:
            users[username]["blocked"] = False
            changed = True
        if "payment_records" not in users[username]:
            users[username]["payment_records"] = []
            changed = True
        else:
            normalized_payments = normalize_payment_records(users[username]["payment_records"])
            if users[username]["payment_records"] != normalized_payments:
                users[username]["payment_records"] = normalized_payments
                changed = True
    if changed:
        save_users(users)


def get_chat_api_key():
    return OPENAI_API_KEY or ""


def get_available_models(username=None):
    config = load_system_config()
    return models_for_chat_list(config["models"])


def portal_login_redirect_url():
    next_path = quote("/api/auth/go-portal", safe="")
    return f"{public_base_url()}/login?next={next_path}"


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "ログインが必要です"}), 401
            if get_server_mode() == SERVER_MODE_API_PORTAL:
                return redirect(portal_login_redirect_url())
            return redirect(url_for("login"))
        if not request.path.startswith("/api/"):
            refresh_session_user()
        return f(*args, **kwargs)

    return wrapped


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        user = refresh_session_user()
        if user.get("role") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "管理者権限が必要です"}), 403
            return redirect(url_for("chat_page"))
        return f(*args, **kwargs)

    return wrapped


def strip_thinking(text):
    return THINK_BLOCK_RE.sub("", text).strip()


def make_openai_client(api_key):
    from openai import OpenAI

    from model_registry import _provider_timeout

    client_kwargs = {"api_key": api_key, "timeout": _provider_timeout()}
    if OPENAI_BASE_URL:
        client_kwargs["base_url"] = OPENAI_BASE_URL
    return OpenAI(**client_kwargs)


_SSE_FLUSH_PAD = ":" + (" " * 128) + "\n\n"
_SSE_FLUSH_BYTE_THRESHOLD = 1800
_STREAM_SSE_KEYS = frozenset(
    {
        "content",
        "reasoning",
        "search",
        "fetch",
        "image_generation",
        "tool_trace",
        "expert_crawl",
        "expert_knowledge_updated",
        "segment_start",
        "segment_end",
        "content_replace",
        "expert_tool_used",
        "done",
        "error",
        "usage",
    }
)

SSE_STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def sse_event(payload):
    body = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    if isinstance(payload, dict) and _STREAM_SSE_KEYS.intersection(payload):
        if len(body.encode("utf-8")) < _SSE_FLUSH_BYTE_THRESHOLD:
            return body + _SSE_FLUSH_PAD
    return body


def filter_chat_messages(messages, provider_id=None):
    from model_registry import provider_supports_reasoning_content

    cleaned = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            cleaned.append({"role": "system", "content": m.get("content", "")})
        elif role == "user":
            content = m.get("content", "")
            cleaned.append({"role": "user", "content": content})
        elif role == "assistant":
            entry = {
                "role": "assistant",
                "content": strip_generated_image_markdown(m.get("content") or ""),
            }
            if m.get("tool_calls"):
                entry["tool_calls"] = m["tool_calls"]
                if provider_supports_reasoning_content(provider_id) and "reasoning_content" in m:
                    entry["reasoning_content"] = m["reasoning_content"] or ""
            cleaned.append(entry)
        elif role == "tool":
            content = m.get("content") or ""
            # Truncate large tool results to avoid blowing up context
            if isinstance(content, str) and len(content) > 8000:
                content = content[:8000] + "\n…(truncated)"
            cleaned.append({
                "role": "tool",
                "tool_call_id": m.get("tool_call_id") or "",
                "content": content,
            })
    return cleaned


@app.route("/login")
def login():
    if session.get("user"):
        if get_server_mode() == SERVER_MODE_API_PORTAL:
            return redirect("/dash")
        next_path = (request.args.get("next") or "").strip()
        if next_path.startswith("/") and not next_path.startswith("//"):
            return redirect(next_path)
        return redirect(url_for("chat_page"))
    features = dict(get_feature_flags())
    features["google_login_available"] = system_google_login_allowed()
    features["discord_login_available"] = system_discord_login_allowed()
    return render_template("login.html", system_features=features)


USERNAME_RE = re.compile(r"^[a-z0-9_-]{3,32}$")


def normalize_username(raw):
    return (raw or "").strip().lower()


def validate_new_username(username):
    if not username:
        return "ユーザー名を入力してください"
    if len(username) < 3:
        return "ユーザー名は3文字以上で入力してください"
    if len(username) > 32:
        return "ユーザー名は32文字以内で入力してください"
    if not USERNAME_RE.match(username):
        return "ユーザー名は英小文字・数字・アンダースコア・ハイフンのみ使用できます"
    return None


def normalize_user_role(raw):
    role = (raw or "user").strip().lower()
    return "admin" if role == "admin" else "user"


def create_user_record(
    password,
    *,
    display_name=None,
    role="user",
    plan=None,
    email="",
    phone="",
    last_name="",
    first_name="",
):
    role = normalize_user_role(role)
    if plan is None:
        plan = "enterprise" if role == "admin" else "free"
    plan = normalize_plan(plan)
    name = (display_name or "").strip()
    return {
        "password_hash": generate_password_hash(password),
        "display_name": name or "",
        "role": role,
        "theme": "dark",
        "chat_background_pattern": "simple",
        "language": "ja",
        "email": normalize_email(email),
        "phone": normalize_phone(phone),
        "billing": default_billing(),
        "plan": plan,
        "balance": 0.0,
        "last_name": normalize_real_name_field(last_name),
        "first_name": normalize_real_name_field(first_name),
        "plan_expires_at": "",
        "blocked": False,
        "payment_records": [],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "usage": normalize_user_usage({}),
        "web_search_enabled": True,
        "geolocation_enabled": False,
        "user_questions_enabled": False,
        "tasks_enabled": False,
        "memory_enabled": False,
        "projects_enabled": False,
        "info_expert_enabled": False,
        "image_generation_enabled": False,
        "image_generation_prefs": {},
        "reasoning_cards_enabled": False,
        "reasoning_disabled": False,
        "cost_performance_maximized": False,
        "reasoning_in_english": False,
        "google_calendar_enabled": False,
        "google_gmail_enabled": False,
        "google_login_enabled": False,
        "google_sub": "",
        "google_email": "",
        "discord_login_enabled": False,
        "discord_id": "",
        "discord_username": "",
        "computelab_tools_enabled": False,
        "on_demand_billing_enabled": False,
        "billing_currency": "JPY",
    }


def resolve_login_username(identifier, users):
    raw = (identifier or "").strip()
    if not raw:
        return None
    if "@" in raw:
        email_key = raw.lower()
        matches = [
            uname
            for uname, rec in users.items()
            if (rec.get("email") or "").strip().lower() == email_key
        ]
        if len(matches) != 1:
            return None
        return matches[0]
    username = raw.lower()
    return username if username in users else None


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json() or {}
    identifier = (data.get("username") or data.get("login") or "").strip()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify({"error": "ユーザー名またはメールアドレスとパスワードを入力してください"}), 400

    users = load_users()
    username = resolve_login_username(identifier, users)
    user = users.get(username) if username else None
    if (
        not user
        or not user.get("password_hash")
        or not check_password_hash(user["password_hash"], password)
    ):
        return jsonify({"error": "ユーザー名・メールアドレスまたはパスワードが正しくありません"}), 401
    if is_user_blocked(user) and user.get("role") != "admin":
        return jsonify({"error": "このアカウントは利用停止中です。管理者にお問い合わせください"}), 403

    session["user"] = build_session_user(username, user)
    return jsonify({"user": session["user"]})


@app.route("/api/auth/check-username")
def auth_check_username():
    if feature_blocked("registration_disabled"):
        return jsonify({"available": False, "error": "現在、新規登録は停止されています"}), 403
    username = normalize_username(request.args.get("username"))
    username_error = validate_new_username(username)
    if username_error:
        return jsonify({"available": False, "error": username_error})
    users = load_users()
    if username in users:
        return jsonify({"available": False, "error": "このユーザー名は登録できません"})
    return jsonify({"available": True})


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json() or {}
    username = normalize_username(data.get("username"))
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip()
    email = normalize_email(data.get("email"))
    phone = normalize_phone(data.get("phone"))

    username_error = validate_new_username(username)
    if username_error:
        return jsonify({"error": username_error}), 400
    if not display_name:
        return jsonify({"error": "表示名を入力してください"}), 400
    if not email:
        return jsonify({"error": "メールアドレスを入力してください"}), 400
    if not is_valid_email(email):
        return jsonify({"error": "メールアドレスの形式が正しくありません"}), 400
    if len(phone) > 32:
        return jsonify({"error": "電話番号が長すぎます"}), 400
    if len(password) < 4:
        return jsonify({"error": "パスワードは4文字以上で入力してください"}), 400

    users = load_users()
    if username in users:
        return jsonify({"error": "このユーザー名は登録できません"}), 409
    if feature_blocked("registration_disabled"):
        return jsonify({"error": "現在、新規登録は停止されています"}), 403

    existing_email_user, _ = find_user_by_email(users, email)
    if existing_email_user:
        return jsonify({"error": "このメールアドレスは既に登録されています"}), 409

    config = load_system_config()
    mail_cfg = config.get("mail_server") or {}
    if email_verification_required(mail_cfg):
        token = create_pending_email_registration(
            username=username,
            password=password,
            display_name=display_name,
            email=email,
            phone=phone,
            billing=normalize_billing(data.get("billing")),
        )
        verify_url = f"{public_base_url()}/verify-email?token={quote(token, safe='')}"
        ok, err = send_verification_email(
            cfg=mail_cfg,
            to_email=email,
            verify_url=verify_url,
            display_name=display_name,
        )
        if not ok:
            return jsonify({"error": err or "確認メールの送信に失敗しました"}), 503
        return jsonify(
            {
                "verification_required": True,
                "message": "確認メールを送信しました。メール内のリンクから登録を完了してください。",
                "email": email,
            }
        ), 202

    users[username] = create_user_record(
        password,
        display_name=display_name,
        email=email,
        phone=phone,
    )
    users[username]["billing"] = normalize_billing(data.get("billing"))
    users[username]["email_verified"] = True
    save_users(users)

    session["user"] = build_session_user(username, users[username])
    return jsonify({"user": session["user"]}), 201


@app.route("/verify-email")
def verify_email_page():
    token = (request.args.get("token") or "").strip()
    if not token:
        return redirect("/login?verify=missing")
    pending, err = consume_pending_email_registration(token)
    if err:
        return redirect(f"/login?verify=error&message={quote(err, safe='')}")
    username = (pending.get("username") or "").strip().lower()
    users = load_users()
    if username in users:
        return redirect("/login?verify=already")
    existing_email_user, _ = find_user_by_email(users, pending.get("email"))
    if existing_email_user:
        return redirect("/login?verify=email_used")
    users[username] = create_user_from_pending_registration(pending)
    save_users(users)
    return redirect("/login?verify=success")


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/go-portal")
@login_required
def auth_go_portal():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username, {})
    if not user_api_access_enabled(record):
        return redirect("/settings#general")
    token = create_portal_sso_token(username)
    next_path = (request.args.get("next") or "/dash").strip() or "/dash"
    if not next_path.startswith("/"):
        next_path = "/dash"
    portal_base = api_portal_base_url().rstrip("/")
    return redirect(
        f"{portal_base}/auth/sso?token={quote(token, safe='')}&next={quote(next_path, safe='')}"
    )


@app.route("/auth/sso")
def auth_portal_sso():
    if get_server_mode() == SERVER_MODE_API:
        return jsonify({"error": "Not found"}), 404
    token = (request.args.get("token") or "").strip()
    next_path = (request.args.get("next") or "/dash").strip() or "/dash"
    if not next_path.startswith("/"):
        next_path = "/dash"
    username = consume_portal_sso_token(token)
    if not username:
        return redirect(portal_login_redirect_url())
    users = load_users()
    record = users.get(username)
    if not record:
        return redirect(portal_login_redirect_url())
    if not user_api_access_enabled(record):
        return redirect(f"{public_base_url()}/settings#general")
    session["user"] = build_session_user(username, record)
    return redirect(next_path)


@app.route("/api/auth/me")
def auth_me():
    user = session.get("user")
    if not user:
        return jsonify({"error": "未ログイン"}), 401
    return jsonify({"user": user})


@app.route("/")
def home():
    if get_server_mode() == SERVER_MODE_API_PORTAL:
        if session.get("user"):
            return redirect("/dash")
        return redirect(portal_login_redirect_url())
    if session.get("user"):
        return redirect(url_for("chat_page"))
    return redirect(url_for("login"))


def _collab_live_url(collab_id):
    return public_page_url(f"/chat/live/{collab_id}")


def get_static_asset_version():
    root = Path(__file__).resolve().parent
    tracked = (
        "static/js/markdown.js",
        "static/js/diagram-extension.js",
        "static/js/app.js",
        "static/css/style.css",
        "static/js/vendor/diagram/mermaid.min.js",
        "static/js/image-lightbox.js",
        "static/js/vendor/marked.min.js",
        "static/dist/js/app.js",
        "static/dist/js/auth.js",
        "static/dist/js/router.js",
    )
    mtimes = [
        int((root / rel).stat().st_mtime)
        for rel in tracked
        if (root / rel).is_file()
    ]
    return str(max(mtimes)) if mtimes else "1"


def vite_js_available():
    """Check if Vite-built TypeScript bundles exist and are explicitly enabled.

    The TypeScript migration is still incomplete (auth/router are placeholders),
    so the legacy JS bundle must keep serving until the migration is finished.
    Set NEXGATE_VITE_ENABLED=1 to opt in to the Vite bundle.
    """
    root = Path(__file__).resolve().parent
    if not (root / "static" / "dist" / "js" / "app.js").is_file():
        return False
    return os.getenv("NEXGATE_VITE_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def render_app(user, initial_view="chat", session_id=None, shared_chat=None):
    user = normalize_session_user(user)
    username = user["username"] if user else ""
    config = load_system_config()
    return render_template(
        "app.html",
        user=user,
        initial_view=initial_view,
        session_id=session_id,
        shared_chat=shared_chat,
        models=get_available_models(username),
        default_model=get_default_model_public_id(config),
        system_features=get_feature_flags(),
        api_portal_base=api_portal_base_url(),
        asset_version=get_static_asset_version(),
        vite_enabled=vite_js_available(),
    )


@app.route("/chat")
@login_required
def chat_page():
    user = refresh_session_user()
    return render_app(user, initial_view="chat", session_id=None)


@app.route("/chat/session/<session_id>")
@login_required
def chat_session(session_id):
    user = refresh_session_user()
    return render_app(user, initial_view="chat", session_id=session_id)


@app.route("/chat/live/<collab_id>")
@login_required
def chat_live_collab(collab_id):
    user = refresh_session_user()
    username = user.get("username")
    record = find_collab_by_id((collab_id or "").strip())
    if not record:
        return render_template("share_not_found.html"), 404
    owner = (record.get("owner") or "").strip().lower()
    session_id = (record.get("session_id") or "").strip()
    access = resolve_session_access(username, owner, session_id)
    if not access:
        return render_template("share_not_found.html"), 404
    shared_chat = {
        "owner": owner,
        "session_id": session_id,
        "role": access.get("role"),
        "permissions": access.get("permissions") or [],
        "collab_mode": record.get("mode") or COLLAB_PRIVATE,
        "collab_id": record.get("id"),
    }
    return render_app(
        user,
        initial_view="chat",
        session_id=session_id,
        shared_chat=shared_chat,
    )


@app.route("/share/<share_id>")
def share_page(share_id):
    share = load_share(share_id)
    if not share:
        return render_template("share_not_found.html"), 404
    visibility = share.get("visibility") or VISIBILITY_PUBLIC
    if visibility == VISIBILITY_LOGIN_REQUIRED and not session.get("user"):
        return render_template("share_login_required.html", share_id=share_id), 403
    created = share.get("created_at") or ""
    created_label = created[:10] if len(created) >= 10 else created
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        created_label = dt.strftime("%Y/%m/%d %H:%M")
    except ValueError:
        pass
    return render_template(
        "share.html",
        share={
            "title": share.get("title") or "共有された会話",
            "messages": share.get("messages") or [],
            "created_label": created_label,
        },
        asset_version=get_static_asset_version(),
    )


def _share_api_payload(record):
    share_id = record.get("id")
    visibility = record.get("visibility") or VISIBILITY_PRIVATE
    if not share_id or visibility == VISIBILITY_PRIVATE:
        return {
            "ok": True,
            "share_id": None,
            "url": None,
            "visibility": VISIBILITY_PRIVATE,
        }
    share_url = public_page_url(f"/share/{share_id}")
    return {
        "ok": True,
        "share_id": share_id,
        "url": share_url,
        "visibility": visibility,
    }


@app.route("/api/chat/sessions", methods=["GET"])
@login_required
def api_chat_sessions_list():
    username = session["user"]["username"]
    rows = list_chat_sessions(username)
    return jsonify({"sessions": rows})


@app.route("/api/chat/sessions/sync", methods=["POST"])
@login_required
def api_chat_sessions_sync():
    username = session["user"]["username"]
    data = request.get_json() or {}
    try:
        result = sync_chat_sessions_from_client(username, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.route("/api/chat/sessions/<session_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_chat_session(session_id):
    username = session["user"]["username"]
    session_id = (session_id or "").strip()

    if request.method == "GET":
        try:
            meta = get_chat_session_meta(username, session_id)
            if not meta:
                return jsonify({"error": "セッションが見つかりません"}), 404
            messages = get_chat_session_messages(username, session_id) or []
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"session": meta, "messages": messages})

    if request.method == "DELETE":
        try:
            delete_chat_session(username, session_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        from chat_session_index_realtime import notify_session_deleted

        notify_session_deleted(username, session_id)
        return jsonify({"ok": True})

    data = request.get_json() or {}
    title = data.get("title")
    messages = data.get("messages")
    favorite = data.get("favorite")
    if favorite is not None:
        favorite = bool(favorite)
    from chat_session_index_realtime import notify_after_upsert, notify_session_deleted

    existing = get_chat_session_meta(username, session_id)
    was_new = existing is None
    try:
        if messages is not None:
            result = upsert_chat_session(
                username,
                session_id,
                title=title,
                messages=messages,
                favorite=favorite,
                updated_at=data.get("updated_at"),
            )
            if result is None:
                notify_session_deleted(username, session_id)
                return jsonify({"ok": True, "deleted": True})
            notify_after_upsert(username, result, was_new=was_new)
            return jsonify({"ok": True, "session": result})
        result = upsert_chat_session(
            username,
            session_id,
            title=title,
            favorite=favorite,
            updated_at=data.get("updated_at"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not result:
        return jsonify({"error": "セッションが見つかりません"}), 404
    notify_after_upsert(username, result, was_new=False)
    return jsonify({"ok": True, "session": result})


@app.route("/api/chat/share", methods=["GET", "POST"])
@login_required
def api_chat_share():
    user = session.get("user") or {}
    username = user.get("username")
    if not username:
        return jsonify({"error": "未ログイン"}), 401

    users = load_users()
    record = users.get(username, {})
    if not user_chat_share_enabled(record):
        return jsonify({"error": "現在のプランではチャット共有は利用できません"}), 403

    if request.method == "GET":
        session_id = (request.args.get("session_id") or "").strip()
        if not session_id:
            return jsonify({"error": "session_id が必要です"}), 400
        record = get_session_share(username, session_id)
        if not record:
            return jsonify(_share_api_payload({"visibility": VISIBILITY_PRIVATE}))
        return jsonify(_share_api_payload(record))

    data = request.get_json() or {}
    if data.get("private"):
        return jsonify({"error": "プライベートチャットは共有できません"}), 400
    session_id = (data.get("session_id") or "").strip()
    visibility = (data.get("visibility") or VISIBILITY_PUBLIC).strip().lower()
    if visibility not in (VISIBILITY_PRIVATE, VISIBILITY_LOGIN_REQUIRED, VISIBILITY_PUBLIC):
        return jsonify({"error": "無効な共有設定です"}), 400
    messages = data.get("messages")
    if visibility != VISIBILITY_PRIVATE:
        if not isinstance(messages, list) or not messages:
            return jsonify({"error": "共有できるメッセージがありません"}), 400
    try:
        record = upsert_share(
            username,
            session_id,
            (data.get("title") or "").strip(),
            messages if isinstance(messages, list) else [],
            visibility,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_share_api_payload(record))


def _collab_api_payload(record):
    payload = collab_public_payload(record, url_builder=_collab_live_url)
    return {"ok": True, **payload}


@app.route("/api/chat/collab", methods=["GET", "POST"])
@login_required
def api_chat_collab():
    user = session.get("user") or {}
    username = user.get("username")
    if not username:
        return jsonify({"error": "未ログイン"}), 401

    users = load_users()
    record_user = users.get(username, {})
    if not user_chat_share_enabled(record_user):
        return jsonify({"error": "現在のプランではチャット共有は利用できません"}), 403

    if request.method == "GET":
        session_id = (request.args.get("session_id") or "").strip()
        if not session_id:
            return jsonify({"error": "session_id が必要です"}), 400
        collab = get_collab_record(username, session_id)
        return jsonify(_collab_api_payload(collab))

    data = request.get_json() or {}
    if data.get("private"):
        return jsonify({"error": "プライベートチャットは共有できません"}), 400
    session_id = (data.get("session_id") or "").strip()
    collab_mode = (data.get("collab_mode") or COLLAB_PRIVATE).strip().lower()
    if collab_mode not in (COLLAB_PRIVATE, COLLAB_VIEW_ONLY, COLLAB_PARTICIPATE):
        return jsonify({"error": "無効な共有設定です"}), 400
    try:
        saved = set_collab_mode(username, session_id, collab_mode)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_collab_api_payload(saved))


@app.route("/api/chat/collab/session", methods=["GET"])
@login_required
def api_chat_collab_session():
    user = session.get("user") or {}
    username = user.get("username")
    if not username:
        return jsonify({"error": "未ログイン"}), 401

    owner = (request.args.get("owner") or "").strip().lower()
    session_id = (request.args.get("session_id") or "").strip()
    if not owner or not session_id:
        return jsonify({"error": "owner と session_id が必要です"}), 400

    access = resolve_session_access(username, owner, session_id)
    if not access:
        return jsonify({"error": "セッションにアクセスできません"}), 403

    meta = get_chat_session_meta(owner, session_id)
    if not meta:
        return jsonify({"error": "セッションが見つかりません"}), 404
    messages = get_chat_session_messages(owner, session_id) or []
    collab = get_collab_record(owner, session_id) or {}
    return jsonify(
        {
            "session": meta,
            "messages": messages,
            "access": access,
            "settings": collab.get("settings") or {},
            "collab_mode": collab.get("mode") or COLLAB_PRIVATE,
        }
    )


@app.route("/settings")
@login_required
def settings_page():
    user = refresh_session_user()
    return render_app(user, initial_view="settings", session_id=None)


@app.route("/billing")
@login_required
def billing_page():
    user = refresh_session_user()
    return render_app(user, initial_view="billing", session_id=None)


@app.route("/announcements")
@login_required
def announcements_page():
    user = refresh_session_user()
    return render_app(user, initial_view="announcements", session_id=None)


@app.route("/api/announcements")
@login_required
def api_announcements():
    return jsonify({"announcements": list_announcements()})


@app.route("/tasks")
@login_required
def tasks_page():
    user = refresh_session_user()
    if not user.get("tasks_enabled"):
        return redirect(url_for("chat_page"))
    return render_app(user, initial_view="tasks", session_id=None)


@app.route("/ask-expert")
@login_required
def ask_expert_page():
    user = refresh_session_user()
    if not user.get("info_expert_enabled"):
        return redirect(url_for("chat_page"))
    return render_app(user, initial_view="ask-expert", session_id=None)


@app.route("/ask-expert/session/<session_id>")
@login_required
def ask_expert_session_page(session_id):
    user = refresh_session_user()
    if not user.get("info_expert_enabled"):
        return redirect(url_for("chat_page"))
    return render_app(
        user,
        initial_view="ask-expert",
        session_id=(session_id or "").strip() or None,
    )


@app.route("/ask-expert/<expert_id>")
@login_required
def ask_expert_detail_page(expert_id):
    user = refresh_session_user()
    if not user.get("info_expert_enabled"):
        return redirect(url_for("chat_page"))
    return render_app(user, initial_view="ask-expert", session_id=None)


def _info_expert_access_guard():
    username = session["user"]["username"]
    record = load_users().get(username, {})
    if not user_info_expert_enabled(record):
        return None, (jsonify({"error": "InfoExpert が有効になっていません"}), 403)
    return username, None


@app.route("/api/info-experts", methods=["GET", "POST"])
@login_required
def api_info_experts():
    username, err = _info_expert_access_guard()
    if err:
        return err
    if request.method == "GET":
        return jsonify(
            {"experts": [serialize_expert(e) for e in load_user_info_experts(username)]}
        )
    data = request.get_json() or {}
    entry, create_err = create_info_expert(
        username,
        name=data.get("name"),
        description=data.get("description"),
        instructions=data.get("instructions"),
    )
    if create_err:
        return jsonify({"error": create_err}), 400
    return jsonify(serialize_expert(entry)), 201


@app.route("/api/info-experts/<expert_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_info_expert_item(expert_id):
    username, err = _info_expert_access_guard()
    if err:
        return err
    expert_id = (expert_id or "").strip()
    if request.method == "GET":
        entry = find_info_expert(username, expert_id)
        if not entry:
            return jsonify({"error": "専門家が見つかりません"}), 404
        return jsonify(serialize_expert(entry))
    if request.method == "DELETE":
        ok, delete_err = delete_info_expert(username, expert_id)
        if not ok:
            return jsonify({"error": delete_err or "削除に失敗しました"}), 404
        delete_expert_sessions_for_expert(username, expert_id)
        delete_all_knowledge(username, expert_id)
        return jsonify({"ok": True})
    data = request.get_json() or {}
    patch = {}
    if "name" in data:
        patch["name"] = data.get("name")
    if "description" in data:
        patch["description"] = data.get("description")
    if "instructions" in data:
        patch["instructions"] = data.get("instructions")
    entry, update_err = update_info_expert(username, expert_id, **patch)
    if update_err:
        return jsonify({"error": update_err}), 404
    return jsonify(serialize_expert(entry))


@app.route("/api/info-experts/<expert_id>/knowledge", methods=["GET"])
@login_required
def api_info_expert_knowledge(expert_id):
    username, err = _info_expert_access_guard()
    if err:
        return err
    expert_id = (expert_id or "").strip()
    if not find_info_expert(username, expert_id):
        return jsonify({"error": "専門家が見つかりません"}), 404
    return jsonify({"items": list_knowledge_items(username, expert_id)})


@app.route("/api/expert-sessions", methods=["GET", "POST"])
@login_required
def api_expert_sessions():
    username, err = _info_expert_access_guard()
    if err:
        return err
    if request.method == "GET":
        return jsonify({"sessions": list_expert_sessions(username)})
    data = request.get_json() or {}
    creation_mode = (data.get("creation_mode") or "chat").strip().lower()
    if creation_mode not in ("chat", "crawl"):
        return jsonify({"error": "creation_mode は chat または crawl です"}), 400
    entry, create_err = create_info_expert(username)
    if create_err:
        return jsonify({"error": create_err}), 400
    session_id = new_expert_session_id()
    session_row = upsert_expert_session(
        username,
        session_id,
        expert_id=entry["id"],
        creation_mode=creation_mode,
        title=entry.get("name") or "専門家を作成中",
    )
    return jsonify({"session": session_row, "expert": serialize_expert(entry)}), 201


@app.route("/api/expert-sessions/<session_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_expert_session_item(session_id):
    username, err = _info_expert_access_guard()
    if err:
        return err
    session_id = (session_id or "").strip()
    if request.method == "GET":
        try:
            meta = get_expert_session_meta(username, session_id)
            if not meta:
                return jsonify({"error": "セッションが見つかりません"}), 404
            messages = get_expert_session_messages(username, session_id) or []
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        expert = None
        if meta.get("expert_id"):
            expert = serialize_expert(find_info_expert(username, meta["expert_id"]))
        return jsonify({"session": meta, "messages": messages, "expert": expert})
    if request.method == "DELETE":
        try:
            delete_expert_session(username, session_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True})
    data = request.get_json() or {}
    title = data.get("title")
    messages = data.get("messages")
    try:
        if messages is not None:
            result = upsert_expert_session(
                username,
                session_id,
                title=title,
                messages=messages,
                updated_at=data.get("updated_at"),
            )
            if result is None:
                return jsonify({"ok": True, "deleted": True})
            return jsonify({"ok": True, "session": result})
        result = upsert_expert_session(
            username,
            session_id,
            title=title,
            updated_at=data.get("updated_at"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not result:
        return jsonify({"error": "セッションが見つかりません"}), 404
    return jsonify({"ok": True, "session": result})


@app.route("/api/expert-chat", methods=["POST"])
@login_required
def api_expert_chat():
    username, guard_err = _info_expert_access_guard()
    if guard_err:
        return guard_err

    data = request.get_json() or {}
    messages = data.get("messages") or []
    if not messages:
        return jsonify({"error": "メッセージがありません"}), 400

    session_id = (data.get("session_id") or "").strip()
    if not session_id:
        return jsonify({"error": "session_id が必要です"}), 400

    session_meta = get_expert_session_meta(username, session_id)
    if not session_meta:
        return jsonify({"error": "セッションが見つかりません"}), 404

    expert_id = (session_meta.get("expert_id") or "").strip()
    expert = find_info_expert(username, expert_id)
    if not expert:
        return jsonify({"error": "専門家が見つかりません"}), 404

    if feature_blocked("chat_disabled"):
        return jsonify({"error": "現在、チャット機能は一時的に制限されています"}), 403

    users = load_users()
    chat_user = users.get(username, {})
    if is_user_blocked(chat_user):
        return jsonify({"error": "アカウントが利用停止中のため、チャットを利用できません"}), 403

    allowed, plan_err = plan_allows_chat(username)
    if not allowed:
        return jsonify({"error": plan_err}), 403

    plan_key = effective_plan_for_features(chat_user)
    emit_reasoning_cards = user_reasoning_cards_enabled(chat_user)
    emit_tool_trace = user_tool_trace_enabled(chat_user)
    emit_full_info = user_full_info_display_enabled(chat_user)
    disable_reasoning = user_reasoning_disabled(chat_user)
    search_allowed = user_web_search_enabled(chat_user) and not feature_blocked(
        "search_disabled"
    )
    search_engines = (
        resolve_engines_for_plan(plan_key, get_plan_features(plan_key))
        if search_allowed
        else {"tavily": False, "serper": False, "ddg": False}
    )

    config = load_system_config()
    requested_model = (data.get("model") or "").strip()
    try:
        resolved = resolve_chat_model(requested_model, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    api_model = resolved["api_model"]
    provider_id = resolved["provider"]
    reasoning_in_english = effective_reasoning_in_english(
        chat_user,
        provider_id=provider_id,
        disable_reasoning=disable_reasoning,
    )

    client, api_key = make_openai_client_for_provider(
        provider_id, config.get("providers")
    )
    if not api_key:
        return jsonify(
            {"error": f"{provider_id} の API キーが設定されていません（管理画面または環境変数）"}
        ), 503

    _, api_base_url = get_provider_credentials(provider_id, config.get("providers"))

    def make_client(_key):
        return client

    creation_mode = session_meta.get("creation_mode") or "chat"
    traced_sse = make_traced_sse_event(sse_event, emit_full_info)

    def generate():
        yield ": connected\n\n"
        turn_usage = empty_usage()
        prepared = None
        try:
            prepared = filter_chat_messages(messages, provider_id=provider_id)
            llm_config = {
                "api_key": api_key,
                "api_base_url": api_base_url or "",
                "model": api_model,
                "search_engines": search_engines,
            }
            yield from stream_expert_creation_chat(
                prepared,
                expert,
                username=username,
                expert_id=expert_id,
                creation_mode=creation_mode,
                api_key=api_key,
                model=api_model,
                make_client=make_client,
                sse_event=traced_sse,
                usage_out=turn_usage,
                allow_web_search=search_allowed,
                search_engines=search_engines,
                emit_reasoning_cards=emit_reasoning_cards,
                disable_reasoning=disable_reasoning,
                provider_id=provider_id,
                reasoning_in_english=reasoning_in_english,
                emit_tool_trace=emit_tool_trace,
                emit_full_info=emit_full_info,
                llm_config=llm_config,
                agent_profile=resolved.get("agent_profile") or "deepseek",
            )
        except Exception as e:
            logger.warning(
                "expert chat stream error user=%s session=%s: %s",
                username,
                session_id,
                e,
            )
            yield sse_event(
                {"error": format_chat_provider_error(e, provider_id=provider_id)}
            )
        finally:
            if prepared is not None and not int(turn_usage.get("total_tokens") or 0):
                merge_usage(
                    turn_usage,
                    estimate_turn_tokens(prepared, "", "", api_model),
                )
            record_chat_usage(
                username,
                turn_usage,
                model=resolved["model_id"],
            )

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers=SSE_STREAM_HEADERS,
    )


@app.route("/projects")
@login_required
def projects_page():
    user = refresh_session_user()
    if not user.get("projects_enabled"):
        return redirect(url_for("chat_page"))
    return render_app(user, initial_view="projects", session_id=None)


@app.route("/projects/<project_id>")
@login_required
def projects_detail_page(project_id):
    user = refresh_session_user()
    if not user.get("projects_enabled"):
        return redirect(url_for("chat_page"))
    return render_app(user, initial_view="projects", session_id=None)


@app.route("/api/tasks", methods=["GET", "PUT"])
@login_required
def api_tasks():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username) or {}
    if not user_tasks_enabled(record):
        return jsonify({"error": "TASKS が有効ではありません"}), 403

    if request.method == "GET":
        return jsonify(load_user_tasks(username))

    data = request.get_json()
    if data is None:
        return jsonify({"error": "JSON body が必要です"}), 400
    saved = save_user_tasks(username, data)
    return jsonify(saved)


def _emit_project_saved(project, event_type="project.updated"):
    project_id = (project.get("id") or "").strip()
    owner = (project.get("owner") or "").strip().lower()
    if not project_id or not owner:
        return
    publish_project_patch(project_id, owner, project, event_type=event_type)
    notify_project_participants(project, event_type, project_id=project_id)


def _emit_project_deleted(project):
    project_id = (project.get("id") or "").strip()
    owner = (project.get("owner") or "").strip().lower()
    if not project_id or not owner:
        return
    publish_project_deleted(project_id, owner)
    notify_project_participants(project, "project.deleted", project_id=project_id)


def _projects_access_guard(username):
    users = load_users()
    record = users.get(username) or {}
    if not user_projects_enabled(record):
        return None, (jsonify({"error": "プロジェクトスペースが有効ではありません"}), 403)
    return users, None


@app.route("/api/projects", methods=["GET", "PUT"])
@login_required
def api_projects():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username) or {}
    if not user_projects_enabled(record):
        return jsonify({"error": "プロジェクトスペースが有効ではありません"}), 403

    if request.method == "GET":
        return jsonify(load_user_projects_bundle(username))

    data = request.get_json()
    if data is None:
        return jsonify({"error": "JSON body が必要です"}), 400
    existing = load_user_projects(username)
    saved = save_user_projects(username, data)
    existing_ids = {item.get("id") for item in existing.get("projects", []) if item.get("id")}
    saved_ids = {item.get("id") for item in saved.get("projects", []) if item.get("id")}
    for deleted_id in existing_ids - saved_ids:
        deleted = next((item for item in existing.get("projects", []) if item.get("id") == deleted_id), None)
        if deleted:
            _emit_project_deleted(deleted)
    for project in saved.get("projects", []):
        _emit_project_saved(project)
    bundle = load_user_projects_bundle(username)
    bundle["projects"] = [
        attach_project_access(project, username) for project in saved.get("projects", [])
    ]
    return jsonify(bundle)


def _resolve_owned_project(username, project_id):
    project, source = find_accessible_project(username, project_id)
    if not project:
        return None, None, (jsonify({"error": "プロジェクトが見つかりません"}), 404)
    if source != "owned":
        return project, source, (jsonify({"error": "この操作はプロジェクト所有者のみ可能です"}), 403)
    return project, source, None


@app.route("/api/projects/<project_id>/members", methods=["GET"])
@login_required
def api_project_members(project_id):
    username = session["user"]["username"]
    users, denied = _projects_access_guard(username)
    if denied:
        return denied
    project, _source = find_accessible_project(username, project_id)
    if not project:
        return jsonify({"error": "プロジェクトが見つかりません"}), 404
    if not has_permission(project, username, "view"):
        return jsonify({"error": "このプロジェクトを表示する権限がありません"}), 403
    members = [
        serialize_member_public(member, users)
        for member in normalize_members(project.get("members"), project.get("owner"))
    ]
    invites = []
    if has_permission(project, username, "manage_members"):
        invites = [
            serialize_invite_public(invite, users)
            for invite in normalize_invites(project.get("invites"))
        ]
    return jsonify(
        {
            "members": members,
            "invites": invites,
            "my_role": get_member_role(project, username),
            "permissions": sorted(
                perm
                for perm, roles in PERMISSIONS.items()
                if get_member_role(project, username) in roles
            ),
        }
    )


@app.route("/api/projects/<project_id>/members/invite", methods=["POST"])
@login_required
def api_project_invite_member(project_id):
    username = session["user"]["username"]
    users, denied = _projects_access_guard(username)
    if denied:
        return denied
    project, _source, denied = _resolve_owned_project(username, project_id)
    if denied:
        return denied
    if not has_permission(project, username, "manage_members"):
        return jsonify({"error": "メンバーを招待する権限がありません"}), 403
    data = request.get_json() or {}
    invitee = normalize_username(data.get("username"))
    invitee_error = validate_new_username(invitee)
    if invitee_error:
        return jsonify({"error": invitee_error}), 400
    if invitee not in users:
        return jsonify({"error": "指定されたユーザーが見つかりません"}), 404
    if not user_projects_enabled(users.get(invitee) or {}):
        return jsonify({"error": "招待先ユーザーはプロジェクト機能が有効ではありません"}), 400
    if invitee == username:
        return jsonify({"error": "自分自身は招待できません"}), 400
    role = normalize_role(data.get("role"))
    if role == "owner":
        role = "editor"
    members = normalize_members(project.get("members"), username)
    if any(m.get("username") == invitee for m in members):
        return jsonify({"error": "このユーザーは既にメンバーです"}), 400
    invites = normalize_invites(project.get("invites"))
    invites = [item for item in invites if item.get("username") != invitee]
    invite = {
        "id": str(uuid.uuid4()),
        "username": invitee,
        "role": role,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "invited_by": username,
    }
    invites.append(invite)
    project["invites"] = invites
    project["members"] = members
    project["updatedAt"] = int(time.time() * 1000)
    save_owner_project(username, project)
    add_incoming_invite(invitee, invite, username, project)
    publish_members_updated(project_id)
    publish_user_sync(invitee, "invites.updated", project_id=project_id)
    _emit_project_saved(project)
    return jsonify(
        {
            "invite": serialize_invite_public(invite, users),
            "members": [serialize_member_public(member, users) for member in members],
            "invites": [serialize_invite_public(item, users) for item in invites],
        }
    )


@app.route("/api/projects/<project_id>/members/<member_username>", methods=["PATCH", "DELETE"])
@login_required
def api_project_member_update(project_id, member_username):
    username = session["user"]["username"]
    users, denied = _projects_access_guard(username)
    if denied:
        return denied
    project, _source, denied = _resolve_owned_project(username, project_id)
    if denied:
        return denied
    if not has_permission(project, username, "manage_members"):
        return jsonify({"error": "メンバーを管理する権限がありません"}), 403
    target = normalize_username(member_username)
    if not target:
        return jsonify({"error": "ユーザー名が不正です"}), 400
    members = normalize_members(project.get("members"), username)
    if target == username:
        return jsonify({"error": "オーナー自身は変更できません"}), 400
    if not any(m.get("username") == target for m in members):
        invites = normalize_invites(project.get("invites"))
        if request.method == "DELETE" and any(i.get("username") == target for i in invites):
            project["invites"] = [i for i in invites if i.get("username") != target]
            remove_incoming_invite(target, None, owner=username, project_id=project_id)
            project["updatedAt"] = int(time.time() * 1000)
            save_owner_project(username, project)
            publish_members_updated(project_id)
            publish_user_sync(target, "invites.updated", project_id=project_id)
            _emit_project_saved(project)
            return jsonify({"ok": True})
        return jsonify({"error": "メンバーが見つかりません"}), 404
    if request.method == "DELETE":
        project["members"] = [m for m in members if m.get("username") != target]
        project["updatedAt"] = int(time.time() * 1000)
        save_owner_project(username, project)
        sync_member_indexes(username, project)
        publish_members_updated(project_id)
        publish_user_sync(target, "projects.updated", project_id=project_id)
        _emit_project_saved(project)
        return jsonify({"ok": True})
    data = request.get_json() or {}
    role = normalize_role(data.get("role"))
    if role == "owner":
        return jsonify({"error": "オーナー権限は付与できません"}), 400
    updated_members = []
    for member in members:
        if member.get("username") == target:
            member = dict(member)
            member["role"] = role
        updated_members.append(member)
    project["members"] = updated_members
    project["updatedAt"] = int(time.time() * 1000)
    save_owner_project(username, project)
    sync_member_indexes(username, project)
    publish_members_updated(project_id)
    publish_user_sync(target, "projects.updated", project_id=project_id)
    _emit_project_saved(project)
    return jsonify(
        {
            "members": [serialize_member_public(member, users) for member in updated_members],
        }
    )


@app.route("/api/projects/invites/<invite_id>/accept", methods=["POST"])
@login_required
def api_project_invite_accept(invite_id):
    username = session["user"]["username"]
    users, denied = _projects_access_guard(username)
    if denied:
        return denied
    incoming = load_incoming_invites(username).get("invites", [])
    invite_ref = next((item for item in incoming if item.get("id") == invite_id), None)
    if not invite_ref:
        return jsonify({"error": "招待が見つかりません"}), 404
    owner = invite_ref.get("owner")
    project_id = invite_ref.get("project_id")
    owner_state = load_user_projects(owner)
    project = next(
        (item for item in owner_state.get("projects", []) if item.get("id") == project_id),
        None,
    )
    if not project:
        remove_incoming_invite(username, invite_id)
        return jsonify({"error": "プロジェクトが見つかりません"}), 404
    pending = next(
        (item for item in normalize_invites(project.get("invites")) if item.get("id") == invite_id),
        None,
    )
    if not pending:
        remove_incoming_invite(username, invite_id)
        return jsonify({"error": "招待は無効です"}), 404
    members = normalize_members(project.get("members"), owner)
    if not any(m.get("username") == username for m in members):
        members.append(
            {
                "username": username,
                "role": pending.get("role") or "viewer",
                "joined_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "invited_by": pending.get("invited_by") or owner,
            }
        )
    project["members"] = members
    project["invites"] = [
        item for item in normalize_invites(project.get("invites")) if item.get("id") != invite_id
    ]
    project["updatedAt"] = int(time.time() * 1000)
    save_owner_project(owner, project)
    sync_member_indexes(owner, project)
    remove_incoming_invite(username, invite_id)
    publish_members_updated(project_id)
    publish_user_sync(username, "projects.updated", project_id=project_id)
    _emit_project_saved(project)
    enriched = attach_project_access(dict(project), username)
    return jsonify({"project": enriched})


@app.route("/api/projects/invites/<invite_id>/decline", methods=["POST"])
@login_required
def api_project_invite_decline(invite_id):
    username = session["user"]["username"]
    _users, denied = _projects_access_guard(username)
    if denied:
        return denied
    incoming = load_incoming_invites(username).get("invites", [])
    invite_ref = next((item for item in incoming if item.get("id") == invite_id), None)
    if not invite_ref:
        return jsonify({"error": "招待が見つかりません"}), 404
    owner = invite_ref.get("owner")
    project_id = invite_ref.get("project_id")
    owner_state = load_user_projects(owner)
    project = next(
        (item for item in owner_state.get("projects", []) if item.get("id") == project_id),
        None,
    )
    if project:
        project["invites"] = [
            item
            for item in normalize_invites(project.get("invites"))
            if item.get("id") != invite_id
        ]
        project["updatedAt"] = int(time.time() * 1000)
        save_owner_project(owner, project)
        publish_members_updated(project_id)
        _emit_project_saved(project)
    remove_incoming_invite(username, invite_id)
    return jsonify({"ok": True})


@app.route("/api/projects/<project_id>", methods=["PUT"])
@login_required
def api_project_update(project_id):
    username = session["user"]["username"]
    users, denied = _projects_access_guard(username)
    if denied:
        return denied
    project, source = find_accessible_project(username, project_id)
    if not project:
        return jsonify({"error": "プロジェクトが見つかりません"}), 404
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body が必要です"}), 400
    owner = (project.get("owner") or username).strip().lower()
    if source == "owned":
        owner = username
    if not has_permission(project, username, "edit_settings"):
        return jsonify({"error": "プロジェクトを編集する権限がありません"}), 403
    updated = dict(project)
    if "name" in data:
        updated["name"] = str(data.get("name") or "")
    if "description" in data:
        updated["description"] = str(data.get("description") or "")
    if "messages" in data and has_permission(project, username, "chat"):
        updated["messages"] = data.get("messages") or []
    if "settings" in data and isinstance(data.get("settings"), dict):
        updated["settings"] = data.get("settings")
    if "workers" in data:
        updated["workers"] = data.get("workers") or []
    if "archive" in data:
        updated["archive"] = data.get("archive") or []
    updated["members"] = normalize_members(project.get("members"), owner)
    updated["invites"] = normalize_invites(project.get("invites"))
    updated["owner"] = owner
    updated["updatedAt"] = int(time.time() * 1000)
    saved_state = save_owner_project(owner, updated)
    saved = next(
        (item for item in saved_state.get("projects", []) if item.get("id") == project_id),
        updated,
    )
    _emit_project_saved(saved)
    return jsonify({"project": attach_project_access(saved, username)})


@app.route("/api/projects/chat", methods=["POST"])
@login_required
def api_projects_chat():
    data = request.get_json() or {}
    project_id = (data.get("project_id") or "").strip()
    if not project_id:
        return jsonify({"error": "project_id が必要です"}), 400

    if feature_blocked("chat_disabled"):
        return jsonify({"error": "現在、チャット機能は一時的に制限されています"}), 403

    username = session["user"]["username"]
    users = load_users()
    record = users.get(username) or {}
    if not user_projects_enabled(record):
        return jsonify({"error": "プロジェクトスペースが有効ではありません"}), 403
    if is_user_blocked(record):
        return jsonify({"error": "アカウントが利用停止中のため、チャットを利用できません"}), 403

    allowed, plan_err = plan_allows_chat(username)
    if not allowed:
        return jsonify({"error": plan_err}), 403

    project, _source = find_accessible_project(username, project_id)
    if not project:
        return jsonify({"error": "プロジェクトが見つかりません"}), 404
    if not has_permission(project, username, "chat"):
        return jsonify({"error": "このプロジェクトでチャットする権限がありません"}), 403
    if not project.get("messages"):
        return jsonify({"error": "メッセージがありません"}), 400

    mode = normalize_project_mode(data.get("mode"))
    emit_reasoning_cards = user_reasoning_cards_enabled(record)
    disable_reasoning = user_reasoning_disabled(record)

    config = load_system_config()
    requested_model = (data.get("model") or "").strip()
    try:
        resolved = resolve_chat_model(requested_model, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    catalog_model_id = resolved["model_id"]
    api_model = resolved["api_model"]
    provider_id = resolved["provider"]
    reasoning_in_english = effective_reasoning_in_english(
        record,
        provider_id=provider_id,
        disable_reasoning=disable_reasoning,
    )

    client, api_key = make_openai_client_for_provider(
        provider_id, config.get("providers")
    )
    if not api_key:
        label = provider_id
        return jsonify(
            {"error": f"{label} の API キーが設定されていません（管理画面または環境変数）"}
        ), 503

    def make_client(_key):
        return client

    def generate():
        yield ": connected\n\n"
        turn_usage = empty_usage()
        prepared = None
        try:
            prepared = filter_chat_messages(
                prepare_project_chat_messages(project, mode),
                provider_id=provider_id,
            )
            yield from stream_project_chat(
                project,
                mode,
                api_key=api_key,
                model=api_model,
                make_client=make_client,
                sse_event=sse_event,
                usage_out=turn_usage,
                emit_reasoning_cards=emit_reasoning_cards,
                disable_reasoning=disable_reasoning,
                provider_id=provider_id,
                reasoning_in_english=reasoning_in_english,
                filter_messages_fn=filter_chat_messages,
            )
        except Exception as e:
            logger.warning(
                "project chat stream error user=%s project=%s provider=%s model=%s: %s",
                username,
                project_id,
                provider_id,
                api_model,
                e,
            )
            yield sse_event(
                {"error": format_chat_provider_error(e, provider_id=provider_id)}
            )
        finally:
            if prepared is not None and not int(turn_usage.get("total_tokens") or 0):
                merge_usage(
                    turn_usage,
                    estimate_turn_tokens(prepared, "", "", api_model),
                )
            record_chat_usage(username, turn_usage, model=catalog_model_id)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers=SSE_STREAM_HEADERS,
    )


def _memory_api_guard(record):
    if not user_memory_enabled(record):
        return jsonify({"error": "メモリが有効ではありません"}), 403
    return None


@app.route("/api/memory", methods=["GET", "POST"])
@login_required
def api_memory_list_create():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username) or {}
    denied = _memory_api_guard(record)
    if denied:
        return denied

    if request.method == "GET":
        memories = load_user_memories(username)
        return jsonify(
            {
                "memories": memories,
                "summary": build_memory_summary(memories),
            }
        )

    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content が必要です"}), 400
    entry, err = add_memory(
        username,
        title=title,
        content=content,
        category=data.get("category"),
        source="manual",
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify(entry), 201


@app.route("/api/memory/<entry_id>", methods=["PUT", "DELETE"])
@login_required
def api_memory_item(entry_id):
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username) or {}
    denied = _memory_api_guard(record)
    if denied:
        return denied

    entry_id = (entry_id or "").strip()
    if not entry_id:
        return jsonify({"error": "id が必要です"}), 400

    if request.method == "DELETE":
        ok, err = delete_memory(username, entry_id)
        if err:
            return jsonify({"error": err}), 404
        return jsonify({"deleted": ok})

    data = request.get_json() or {}
    entry, err = update_memory(
        username,
        entry_id,
        title=data.get("title"),
        content=data.get("content"),
        category=data.get("category"),
    )
    if err:
        return jsonify({"error": err}), 404
    return jsonify(entry)


@app.route("/api/admin/sessions/active")
@admin_required
def admin_sessions_active():
    return jsonify({"active": list_active_sessions()})


@app.route("/api/admin/sessions/logs")
@admin_required
def admin_sessions_logs():
    try:
        limit = min(200, max(1, int(request.args.get("limit", 80))))
    except (TypeError, ValueError):
        limit = 80
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    rows, total = list_session_logs(limit=limit, offset=offset)
    return jsonify({"sessions": rows, "total": total})


@app.route("/api/admin/sessions/<request_id>/detail")
@admin_required
def admin_session_detail(request_id):
    request_id = (request_id or "").strip()
    if not request_id:
        return jsonify({"error": "request_id が必要です"}), 400
    detail = load_request_detail(request_id)
    if not detail:
        return jsonify({"error": "リクエスト詳細が見つかりません"}), 404
    return jsonify({"detail": serialize_request_detail_for_api(detail)})


@app.route("/api/admin/sessions/<request_id>/stop", methods=["POST"])
@admin_required
def admin_session_stop(request_id):
    request_id = (request_id or "").strip()
    if not request_id:
        return jsonify({"error": "request_id が必要です"}), 400
    ok = request_chat_abort(request_id)
    if ok:
        update_billing_event(request_id, status="cancelled")
    return jsonify({"ok": ok, "request_id": request_id})


@app.route("/admin")
@admin_required
def admin_page():
    user = refresh_session_user()
    return render_app(user, initial_view="admin", session_id=None)


@app.route("/api/billing/usage")
@login_required
def billing_usage():
    username = session["user"]["username"]
    return jsonify(build_billing_summary(username))


@app.route("/api/billing/request-logs")
@login_required
def billing_request_logs():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username) or {}
    lang = (record.get("language") or "ja").strip().lower()
    if lang not in ("ja", "en", "ko"):
        lang = "ja"
    try:
        limit = min(200, max(1, int(request.args.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    rows, total = list_billing_events_for_user(username, limit=limit, offset=offset)
    return jsonify(
        {
            "events": [serialize_billing_event(row, lang) for row in rows],
            "total": total,
            "billing_model_note": billing_model_note(lang),
        }
    )


@app.route("/api/billing/paypal/create-order", methods=["POST"])
@login_required
def billing_paypal_create_order():
    if feature_blocked("billing_disabled"):
        return jsonify({"error": "現在、課金・残高チャージは一時的に停止されています"}), 403

    username = session["user"]["username"]
    users = load_users()
    record = users.get(username)
    if not record:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    if is_user_blocked(record):
        return jsonify({"error": "アカウントが利用停止中です"}), 403

    data = request.get_json() or {}
    result, err = create_checkout_order(username, data.get("amount_jpy"))
    if err:
        status = 503 if "設定されていません" in err else 400
        return jsonify({"error": err}), status
    return jsonify(result)


@app.route("/api/billing/paypal/capture-order", methods=["POST"])
@login_required
def billing_paypal_capture_order():
    if feature_blocked("billing_disabled"):
        return jsonify({"error": "現在、課金・残高チャージは一時的に停止されています"}), 403

    username = session["user"]["username"]
    users = load_users()
    record = users.get(username)
    if not record:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    if is_user_blocked(record):
        return jsonify({"error": "アカウントが利用停止中です"}), 403

    data = request.get_json() or {}
    order_id = data.get("order_id") or ""
    payment, err = capture_checkout_order(username, order_id)
    if err:
        return jsonify({"error": err}), 400

    credited, new_balance = append_balance_topup(
        record,
        payment["amount_jpy"],
        payment["order_id"],
        payment.get("capture_id"),
    )
    if not credited:
        summary = build_billing_summary(username)
        return jsonify(
            {
                "message": "この決済は既に残高に反映済みです",
                "balance": new_balance,
                "balance_label": format_balance_jpy(new_balance),
                "billing": summary,
                "user": build_session_user(username, record),
            }
        )

    save_users(users)
    session["user"] = build_session_user(username, record)
    summary = build_billing_summary(username)
    return jsonify(
        {
            "message": f"¥{payment['amount_jpy']:,} を残高に追加しました（PayPal）",
            "balance": new_balance,
            "balance_label": format_balance_jpy(new_balance),
            "billing": summary,
            "user": session["user"],
        }
    )


@app.route("/api/billing/paypal/create-subscription", methods=["POST"])
@login_required
def billing_paypal_create_subscription():
    if feature_blocked("billing_disabled"):
        return jsonify({"error": "現在、課金は一時的に停止されています"}), 403

    username = session["user"]["username"]
    users = load_users()
    record = users.get(username)
    if not record:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    if is_user_blocked(record):
        return jsonify({"error": "アカウントが利用停止中です"}), 403

    data = request.get_json() or {}
    plan_id = (data.get("plan_id") or data.get("plan") or "").strip().lower()
    if plan_id not in SUBSCRIPTION_PLAN_IDS:
        return jsonify({"error": "プランが不正です"}), 400

    return_url = public_page_url("/billing") + "?subscription=success"
    cancel_url = public_page_url("/billing") + "?subscription=cancelled"
    email = normalize_email(record.get("email"))
    result, err = create_billing_subscription(
        username,
        email,
        plan_id,
        return_url,
        cancel_url,
    )
    if err:
        status = 503 if "設定されていません" in err or "未設定" in err else 400
        return jsonify({"error": err}), status
    return jsonify(result)


@app.route("/api/billing/preview-purchase-coupon", methods=["POST"])
@login_required
def billing_preview_purchase_coupon():
    if feature_blocked("coupon_disabled"):
        return jsonify({"error": "現在、クーポンコードの利用は停止されています"}), 403

    username = session["user"]["username"]
    data = request.get_json() or {}
    plan_id = (data.get("plan_id") or data.get("plan") or "").strip().lower()
    code = data.get("code") or data.get("coupon_code") or ""
    if not code.strip():
        return jsonify({"error": "クーポンコードを入力してください"}), 400
    if plan_id not in SUBSCRIPTION_PLAN_IDS:
        return jsonify({"error": "プランが不正です"}), 400

    base_charge = plan_charge_jpy(plan_id)
    if base_charge is None or base_charge <= 0:
        return jsonify({"error": "プラン料金が設定されていません"}), 400

    preview, err = preview_purchase_coupon(
        username,
        code,
        plan_id,
        base_charge,
        set(SUBSCRIPTION_PLAN_IDS),
    )
    if err:
        return jsonify({"error": err}), 400

    return jsonify(
        {
            "ok": True,
            "code": preview.get("code"),
            "plan_id": plan_id,
            "original_charge_jpy": preview.get("original_charge_jpy"),
            "discount_jpy": preview.get("discount_jpy"),
            "final_charge_jpy": preview.get("final_charge_jpy"),
            "original_charge_label": format_balance_jpy(preview.get("original_charge_jpy")),
            "discount_label": format_balance_jpy(preview.get("discount_jpy")),
            "final_charge_label": format_balance_jpy(preview.get("final_charge_jpy")),
            "benefit_label": preview.get("benefit_label"),
        }
    )


@app.route("/api/billing/subscribe-with-balance", methods=["POST"])
@login_required
def billing_subscribe_with_balance():
    if feature_blocked("billing_disabled"):
        return jsonify({"error": "現在、課金は一時的に停止されています"}), 403

    username = session["user"]["username"]
    users = load_users()
    record = users.get(username)
    if not record:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    if is_user_blocked(record):
        return jsonify({"error": "アカウントが利用停止中です"}), 403

    data = request.get_json() or {}
    plan_id = (data.get("plan_id") or data.get("plan") or "").strip().lower()
    if plan_id not in SUBSCRIPTION_PLAN_IDS:
        return jsonify({"error": "プランが不正です"}), 400

    current_plan = normalize_plan(record.get("plan"))
    if plan_id == current_plan:
        return jsonify({"error": "現在と同じプランです"}), 400
    if plan_tier_rank(plan_id) <= plan_tier_rank(current_plan):
        return jsonify({"error": "下位プランへの変更はできません"}), 400

    coupon_code = (data.get("coupon_code") or data.get("code") or "").strip()
    result, err = apply_balance_plan_subscription(
        record,
        plan_id,
        username=username,
        coupon_code=coupon_code or None,
    )
    if err:
        status = 400
        if "残高が不足" in err:
            status = 402
        return jsonify({"error": err}), status

    save_users(users)
    session["user"] = build_session_user(username, record)
    summary = build_billing_summary(username)
    plan_name = result["plan_name"]
    charge_label = format_balance_jpy(result["charge_jpy"])
    message = f"{plan_name} プランを申し込みました（{charge_label} / 1ヶ月）"
    if result.get("discount_jpy"):
        message = (
            f"{plan_name} プランを申し込みました（{charge_label} / 1ヶ月"
            f" · クーポン割引 {format_balance_jpy(result['discount_jpy'])}）"
        )
    return jsonify(
        {
            "message": message,
            "plan": result["plan"],
            "plan_name": plan_name,
            "charge_jpy": result["charge_jpy"],
            "original_charge_jpy": result.get("original_charge_jpy"),
            "discount_jpy": result.get("discount_jpy", 0),
            "coupon_code": result.get("coupon_code", ""),
            "balance": result["balance"],
            "balance_label": format_balance_jpy(result["balance"]),
            "billing": summary,
            "user": session["user"],
        }
    )


@app.route("/api/webhooks/paypal", methods=["POST"])
def paypal_webhook():
    raw = request.get_data(as_text=True)
    try:
        event = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return jsonify({"error": "invalid_json"}), 400

    if not isinstance(event, dict):
        return jsonify({"error": "invalid_payload"}), 400

    if not get_paypal_webhook_id():
        return jsonify({"error": "webhook_not_configured"}), 503

    ok, err = verify_webhook_signature(request.headers, event)
    if not ok:
        return jsonify({"error": err or "verification_failed"}), 400

    try:
        success, detail = process_paypal_subscription_webhook_event(event)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    if not success and detail == "user_not_found":
        return jsonify({"ok": True, "detail": detail}), 200
    if not success:
        return jsonify({"error": detail}), 422
    return jsonify({"ok": True, "detail": detail}), 200


@app.route("/api/system/status")
def system_status():
    return jsonify({"features": get_feature_flags()})


@app.route("/api/system/health")
def system_health():
    return jsonify(local_health_payload())


# ============================================================
# OpenAPI ドキュメント
# ============================================================
_OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "info": {
        "title": "NEXGATE AI API",
        "version": "1.0.0",
        "description": (
            "NEXGATE AI プラットフォームの API。"
            "OpenAI互換の /v1/chat/completions と、開発者向けの /api/developer/* を提供します。"
        ),
    },
    "servers": [{"url": "/", "description": "NEXGATE AI API"}],
    "paths": {
        "/v1/models": {
            "get": {
                "summary": "利用可能なモデル一覧",
                "operationId": "listModels",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": {"description": "モデル一覧"},
                    "401": {"description": "無効なAPIキー"},
                    "403": {"description": "権限なし"},
                    "429": {"description": "レートリミット超過"},
                },
            }
        },
        "/v1/chat/completions": {
            "post": {
                "summary": "チャット補完（OpenAI互換）",
                "operationId": "createChatCompletion",
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ChatCompletionRequest"}
                        }
                    },
                },
                "responses": {
                    "200": {"description": "補完結果"},
                    "400": {"description": "リクエスト不正"},
                    "401": {"description": "無効なAPIキー"},
                    "403": {"description": "権限なし"},
                    "429": {"description": "レートリミット超過"},
                    "502": {"description": "プロバイダーエラー"},
                },
            }
        },
        "/api/developer/profile": {
            "get": {
                "summary": "開発者プロフィール",
                "operationId": "developerProfile",
                "security": [{"cookieAuth": []}],
                "responses": {"200": {"description": "プロフィール"}},
            }
        },
        "/api/developer/usage": {
            "get": {
                "summary": "API使用量",
                "operationId": "developerUsage",
                "security": [{"cookieAuth": []}],
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 50},
                    }
                ],
                "responses": {"200": {"description": "使用量"}},
            }
        },
        "/api/developer/tokens": {
            "get": {
                "summary": "APIトークン一覧",
                "operationId": "listTokens",
                "security": [{"cookieAuth": []}],
                "responses": {"200": {"description": "トークン一覧"}},
            },
            "post": {
                "summary": "APIトークン作成",
                "operationId": "createToken",
                "security": [{"cookieAuth": []}],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}},
                            }
                        }
                    }
                },
                "responses": {
                    "201": {"description": "作成成功"},
                    "400": {"description": "リクエスト不正"},
                },
            },
        },
        "/api/developer/tokens/{token_id}": {
            "delete": {
                "summary": "APIトークン失効",
                "operationId": "revokeToken",
                "security": [{"cookieAuth": []}],
                "parameters": [
                    {
                        "name": "token_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {"description": "失効成功"},
                    "404": {"description": "トークンなし"},
                },
            }
        },
        "/api/admin/system-keys": {
            "get": {
                "summary": "システムキー概要（上流/下流を分離表示）",
                "operationId": "getSystemKeysOverview",
                "security": [{"cookieAuth": []}],
                "responses": {"200": {"description": "上流・下流キー状態"}},
            }
        },
        "/api/admin/system-api-keys": {
            "get": {
                "summary": "NEXGATE AI API 用システムAPIキー一覧",
                "operationId": "listSystemApiKeys",
                "security": [{"cookieAuth": []}],
                "responses": {"200": {"description": "システムAPIキー一覧"}},
            },
            "post": {
                "summary": "NEXGATE AI API 用システムAPIキー作成",
                "operationId": "createSystemApiKey",
                "security": [{"cookieAuth": []}],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["owner_username"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "owner_username": {
                                        "type": "string",
                                        "description": "課金・レートリミットの帰属先ユーザー",
                                    },
                                    "scopes": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "enum": ["models", "chat_completions"],
                                        },
                                    },
                                },
                            }
                        }
                    }
                },
                "responses": {
                    "201": {"description": "作成成功"},
                    "400": {"description": "リクエスト不正"},
                },
            },
        },
        "/api/admin/system-api-keys/{key_id}": {
            "delete": {
                "summary": "NEXGATE AI API 用システムAPIキー失効",
                "operationId": "revokeSystemApiKey",
                "security": [{"cookieAuth": []}],
                "parameters": [
                    {
                        "name": "key_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {"description": "失効成功"},
                    "404": {"description": "キーなし"},
                },
            }
        },
    },
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer"},
            "cookieAuth": {"type": "apiKey", "in": "cookie", "name": "session"},
        },
        "schemas": {
            "ChatCompletionRequest": {
                "type": "object",
                "required": ["model", "messages"],
                "properties": {
                    "model": {"type": "string", "example": "nexgate-base"},
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string", "enum": ["system", "user", "assistant", "tool"]},
                                "content": {"type": "string"},
                                "tool_calls": {"type": "array"},
                                "tool_call_id": {"type": "string"},
                            },
                        },
                    },
                    "stream": {"type": "boolean", "default": False},
                    "tools": {"type": "array", "description": "ツール定義（function calling）"},
                    "tool_choice": {
                        "oneOf": [
                            {"type": "string", "enum": ["none", "auto", "required"]},
                            {"type": "object"},
                        ]
                    },
                    "temperature": {"type": "number", "default": 1.0},
                    "top_p": {"type": "number", "default": 1.0},
                    "max_tokens": {"type": "integer"},
                    "max_completion_tokens": {"type": "integer"},
                    "presence_penalty": {"type": "number"},
                    "frequency_penalty": {"type": "number"},
                    "seed": {"type": "integer"},
                    "stop": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                    "n": {"type": "integer", "default": 1, "description": "1のみ対応"},
                    "user": {"type": "string"},
                    "response_format": {"type": "object"},
                },
            }
        },
    },
}


@app.route("/openapi.json")
def openapi_spec():
    return jsonify(_OPENAPI_SPEC)


@app.route("/api/docs")
def api_docs_redirect():
    return redirect("/openapi.json")


def _nexgate_process_stats(psutil_module):
    """Get aggregated resource usage of NEXGATE Python processes."""
    import os as _os

    root_dir = Path(__file__).resolve().parent
    nexgate_cpu = 0.0
    nexgate_mem_mb = 0.0
    nexgate_count = 0
    try:
        for proc in psutil_module.process_iter(["pid", "name", "cmdline", "cpu_percent", "memory_info"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                if not any("python" in (p or "").lower() for p in cmdline):
                    continue
                cwd = ""
                try:
                    cwd = _os.readlink(f"/proc/{proc.info['pid']}/cwd")
                except Exception:
                    cwd = proc.cwd() if hasattr(proc, "cwd") else ""
                if str(root_dir) not in (cwd or ""):
                    continue
                nexgate_cpu += proc.info.get("cpu_percent") or 0.0
                mem = proc.info.get("memory_info")
                nexgate_mem_mb += (mem.rss if mem else 0) / (1024 * 1024)
                nexgate_count += 1
            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied, Exception):
                continue
    except Exception:
        pass
    return {
        "cpu_percent": round(nexgate_cpu, 1),
        "memory_mb": round(nexgate_mem_mb, 1),
        "process_count": nexgate_count,
    }


@app.route("/api/admin/system-stats")
@admin_required
def admin_system_stats():
    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=0.3)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        disk = psutil.disk_usage("/")

        net = psutil.net_io_counters()

        boot = psutil.boot_time()

        return jsonify(
            {
                "cpu": {
                    "percent": round(cpu_percent, 1),
                    "count": cpu_count,
                    "freq_current": cpu_freq.current if cpu_freq else None,
                    "freq_max": cpu_freq.max if cpu_freq else None,
                },
                "memory": {
                    "total_mb": round(mem.total / (1024 * 1024), 1),
                    "used_mb": round(mem.used / (1024 * 1024), 1),
                    "available_mb": round(mem.available / (1024 * 1024), 1),
                    "percent": round(mem.percent, 1),
                },
                "swap": {
                    "total_mb": round(swap.total / (1024 * 1024), 1),
                    "used_mb": round(swap.used / (1024 * 1024), 1),
                    "percent": round(swap.percent, 1) if swap.total > 0 else 0,
                },
                "disk": {
                    "total_gb": round(disk.total / (1024 * 1024 * 1024), 1),
                    "used_gb": round(disk.used / (1024 * 1024 * 1024), 1),
                    "free_gb": round(disk.free / (1024 * 1024 * 1024), 1),
                    "percent": round(disk.percent, 1),
                },
                "network": {
                    "sent_mb": round(net.bytes_sent / (1024 * 1024), 1),
                    "recv_mb": round(net.bytes_recv / (1024 * 1024), 1),
                    "packets_sent": net.packets_sent,
                    "packets_recv": net.packets_recv,
                },
                "uptime_seconds": int(time.time() - boot),
                "nexgate": _nexgate_process_stats(psutil),
            }
        )
    except ImportError:
        return jsonify({"error": "psutil がインストールされていません。pip install psutil を実行してください"}), 500
    except Exception as e:
        logger.exception("admin_system_stats failed")
        return jsonify({"error": str(e)}), 500


# ── Chat Report ────────────────────────────────────────────

REPORTS_DIR = Path(__file__).resolve().parent / "data" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DISCORD_REPORT_WEBHOOK = (
    "https://discord.com/api/webhooks/1526424730939166841/"
    "jtPRPdl_5nIUjEwl3E5qvLXCK5G41WPG3_XeYioA9Xiu3nd5YwzzEqC5oeyOQWKuLkPb"
)


REPORT_STATUSES = ["unconfirmed", "confirmed", "unresolved", "cancelled", "resolved"]
REPORT_STATUS_DEFAULT = "unconfirmed"


def _report_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _report_path(report_id):
    report_id = str(report_id or "").strip()
    if not report_id or "/" in report_id or "\\" in report_id:
        raise ValueError("invalid report_id")
    return REPORTS_DIR / f"{report_id}.json"


def _read_report(report_id):
    path = _report_path(report_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_report(report_id, data):
    path = _report_path(report_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _save_report(report_data):
    report_id = str(uuid.uuid4())
    report_data["id"] = report_id
    report_data["status"] = REPORT_STATUS_DEFAULT
    report_data["created_at"] = _report_now_iso()
    report_data["client_ip"] = request_client_ip()
    report_data["user_agent"] = request.headers.get("User-Agent", "")[:500]
    _write_report(report_id, report_data)
    return report_data


def _send_discord_report(report_data):
    try:
        desc = report_data.get("description", "").strip()
        username = report_data.get("username", "unknown")
        session_id = report_data.get("session_id", "")
        created = report_data.get("created_at", "")
        ip = report_data.get("client_ip", "")

        content_lines = [
            f"📢 **新規報告**",
            f"",
            f"**送信者**: `{username}`",
            f"**IP**: `{ip}`",
            f"**セッションID**: `{session_id}`",
            f"**日時**: {created}",
            f"",
            f"**問題の内容**:",
            f"{desc if desc else '(詳細なし)'}",
        ]
        content = "\n".join(content_lines)

        payload = {"content": content[:2000]}

        # Attach full chat as file
        messages = report_data.get("messages")
        if messages:
            chat_text = json.dumps(messages, ensure_ascii=False, indent=2)
            import io as _io_module

            chat_file = ("chat.json", _io_module.BytesIO(chat_text.encode("utf-8")), "application/json")
            import requests as _requests

            _requests.post(
                DISCORD_REPORT_WEBHOOK,
                data={"payload_json": json.dumps(payload)},
                files={"file": chat_file},
                timeout=15,
            )
        else:
            import requests as _requests

            _requests.post(DISCORD_REPORT_WEBHOOK, json=payload, timeout=15)
        logger.info(f"Discord report sent: {report_data.get('id')}")
    except Exception as e:
        logger.exception("Failed to send Discord report")


def _list_reports():
    reports = []
    if REPORTS_DIR.is_dir():
        for f in sorted(REPORTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.suffix != ".json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                reports.append(data)
            except Exception:
                pass
    return reports


@app.route("/api/chat/report", methods=["POST"])
@login_required
def chat_report():
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "無効なリクエストです"}), 400

    description = (data.get("description") or "").strip()[:2000]
    session_id = (data.get("session_id") or "").strip()[:200]

    if not description:
        return jsonify({"error": "問題の内容を入力してください"}), 400

    username = session.get("user", {}).get("username", "unknown")

    # Gather full session messages
    messages = None
    if session_id:
        try:
            msgs = get_chat_session_messages(username, session_id)
            if msgs:
                messages = msgs
        except Exception:
            pass

    report_data = _save_report({
        "username": username,
        "session_id": session_id,
        "description": description,
        "messages": messages,
    })

    # Send to Discord (fire and forget)
    import threading as _threading
    _threading.Thread(target=_send_discord_report, args=(report_data,), daemon=True).start()

    return jsonify({"ok": True, "report_id": report_data["id"]})


@app.route("/api/admin/reports")
@admin_required
def admin_reports():
    return jsonify({"reports": _list_reports()})


@app.route("/api/admin/reports/<report_id>", methods=["PATCH"])
@admin_required
def admin_report_update(report_id):
    report = _read_report(report_id)
    if report is None:
        return jsonify({"error": "報告が見つかりません"}), 404

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "無効なリクエストです"}), 400

    status = (data.get("status") or "").strip().lower()
    if status and status not in REPORT_STATUSES:
        return jsonify({"error": f"無効なステータスです: {status}"}), 400

    if status:
        report["status"] = status
    report["updated_at"] = _report_now_iso()
    _write_report(report_id, report)

    return jsonify({"ok": True, "report": report})


@app.route("/api/admin/reports/<report_id>", methods=["DELETE"])
@admin_required
def admin_report_delete(report_id):
    report = _read_report(report_id)
    if report is None:
        return jsonify({"error": "報告が見つかりません"}), 404

    try:
        _report_path(report_id).unlink()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True})


@app.route("/api/admin/state")
@admin_required
def admin_state():
    users = load_users()
    user_list = [
        serialize_admin_user(name, record)
        for name, record in sorted(users.items(), key=lambda item: item[0])
    ]
    plans = [serialize_admin_plan(key) for key in PLAN_ORDER]
    config = load_system_config()
    return jsonify(
        {
            "users": user_list,
            "plans": plans,
            "features": get_feature_flags(),
            "paypal": serialize_paypal_admin(),
            "models": admin_models_payload(config),
            "extended_models": _extended_models_admin_response(config),
            "image_generation": _image_generation_admin_response(config),
        }
    )


@app.route("/api/admin/models")
@admin_required
def admin_get_models():
    config = load_system_config()
    chart_range = request.args.get("range", DEFAULT_CHART_RANGE)
    return jsonify({"models": admin_models_payload(config, chart_range=chart_range)})


# ============================================================
# メトリクス・フィードバック・A/Bテスト API
# ============================================================
@app.route("/api/admin/metrics")
@admin_required
def admin_metrics():
    """パフォーマンスメトリクスのスナップショット"""
    try:
        from metrics import get_metrics
        return jsonify(get_metrics().snapshot())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/admin/metrics/save", methods=["POST"])
@admin_required
def admin_metrics_save():
    """メトリクスをファイルに保存"""
    try:
        from metrics import get_metrics
        get_metrics().save_to_file()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/feedback", methods=["POST"])
@login_required
def api_feedback():
    """ユーザーフィードバック（👍/👎）を記録"""
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "無効なリクエストです"}), 400

    username = session.get("user", {}).get("username", "unknown")
    rating = data.get("rating")
    try:
        rating = int(rating or 0)
    except (TypeError, ValueError):
        rating = 0
    if rating not in (-1, 0, 1):
        return jsonify({"error": "rating は -1, 0, 1 のいずれかです"}), 400

    try:
        from feedback import add_user_feedback
        fid = add_user_feedback(
            username=username,
            session_id=(data.get("session_id") or "").strip(),
            message_index=data.get("message_index") or 0,
            rating=rating,
            comment=(data.get("comment") or "").strip(),
            variant=data.get("variant"),
        )
        return jsonify({"ok": True, "feedback_id": fid})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/admin/feedback")
@admin_required
def admin_feedback_summary():
    """フィードバック集計"""
    try:
        from feedback import get_feedback_summary
        return jsonify(get_feedback_summary())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/ab/assign", methods=["POST"])
@login_required
def api_ab_assign():
    """A/Bテストのバリアント割り当て"""
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "無効なリクエストです"}), 400

    username = session.get("user", {}).get("username", "unknown")
    experiment = (data.get("experiment") or "").strip()
    if not experiment:
        return jsonify({"error": "experiment が必要です"}), 400

    try:
        from feedback import assign_variant
        variant = assign_variant(username, experiment)
        return jsonify({"ok": True, "experiment": experiment, "variant": variant})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/admin/ab")
@admin_required
def admin_ab_overview():
    """A/Bテスト割り当ての概要"""
    try:
        from feedback import get_ab_manager, get_feedback_summary
        return jsonify({
            "assignments": get_ab_manager().get_all_assignments(),
            "feedback": get_feedback_summary(),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/admin/models/chart")
@admin_required
def admin_models_chart():
    config = load_system_config()
    chart_range = request.args.get("range", DEFAULT_CHART_RANGE)
    model_filter = request.args.get("model", "all")
    chart = build_usage_chart(
        config["models"],
        load_usage_series(),
        range_key=chart_range,
        model_filter=model_filter,
    )
    return jsonify({"chart": chart})


def _parse_pricing_field(entry, field_name):
    if field_name not in entry:
        return None
    try:
        return max(0.0, float(entry[field_name]))
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} が不正です")


@app.route("/api/admin/models", methods=["POST"])
@admin_required
def admin_create_model():
    data = request.get_json() or {}
    mid = validate_model_id(data.get("id"))
    if not mid:
        return jsonify({"error": "モデルIDが不正です（英数字・._-、2〜64文字）"}), 400

    config = load_system_config()
    if mid in config["models"]:
        return jsonify({"error": "同じIDのモデルが既に存在します"}), 409

    entry = dict(data)
    if "api_id" in entry:
        api_id = validate_model_id(entry.get("api_id"))
        if not api_id:
            return jsonify({"error": "APIモデルIDが不正です（英数字・._-、2〜64文字）"}), 400
        entry["api_id"] = api_id
    config["models"][mid] = normalize_model_entry(mid, entry)
    dup_err = validate_unique_api_ids(config["models"])
    if dup_err:
        del config["models"][mid]
        return jsonify({"error": dup_err}), 400

    if not config.get("default_model"):
        config["default_model"] = mid
    save_system_config(config)
    return jsonify({"models": admin_models_payload(config)}), 201


@app.route("/api/admin/models/<model_id>/test", methods=["POST"])
@admin_required
def admin_test_model(model_id):
    mid = validate_model_id(model_id)
    if not mid:
        return jsonify({"ok": False, "message": "モデルIDが不正です"}), 400

    config = load_system_config()
    if mid not in config["models"]:
        return jsonify({"ok": False, "message": "モデルが見つかりません"}), 404

    result = test_model_api(mid, config)
    if result.get("ok"):
        return jsonify(result)
    if result.get("missing_api_key"):
        return jsonify(result), 503
    return jsonify(result), 502


@app.route("/api/admin/models/<model_id>", methods=["DELETE"])
@admin_required
def admin_delete_model(model_id):
    mid = validate_model_id(model_id)
    if not mid:
        return jsonify({"error": "モデルIDが不正です"}), 400

    config = load_system_config()
    if mid not in config["models"]:
        return jsonify({"error": "モデルが見つかりません"}), 404
    if len(config["models"]) <= 1:
        return jsonify({"error": "最後の1件は削除できません"}), 400

    del config["models"][mid]
    if config.get("default_model") == mid:
        config["default_model"] = get_default_model_id(config)
    save_system_config(config)
    return jsonify({"models": admin_models_payload(config)})


@app.route("/api/admin/models", methods=["PUT"])
@admin_required
def admin_update_models():
    data = request.get_json() or {}
    incoming = data.get("models")
    if incoming is None and isinstance(data, dict) and "models" not in data:
        incoming = data
    if incoming is None:
        incoming = {}
    if not isinstance(incoming, dict):
        return jsonify({"error": "models が不正です"}), 400
    if (
        not incoming
        and "providers" not in data
        and "default_model" not in data
    ):
        return jsonify({"error": "更新内容がありません"}), 400

    config = load_system_config()
    merged = dict(config["models"])
    for model_id, entry in incoming.items():
        if not isinstance(entry, dict):
            continue
        mid = str(model_id).strip()
        if not mid or mid not in merged:
            continue
        base = dict(merged[mid])
        patch = dict(entry)
        preserved_public_id = (base.get("public_id") or "").strip()
        if "api_id" in patch:
            api_id = validate_model_id(patch.get("api_id"))
            if not api_id:
                return jsonify({"error": f"APIモデルIDが不正です（{mid}）"}), 400
            base["api_id"] = api_id
        for key in (
            "display_name",
            "provider",
            "api_model",
            "tier",
            "agent_profile",
            "enabled",
            "cost_input_usd_per_1m",
            "cost_output_usd_per_1m",
            "price_input_usd_per_1m",
            "price_output_usd_per_1m",
            "cost_input_cache_hit_usd_per_1m",
            "price_input_cache_hit_usd_per_1m",
        ):
            if key in patch:
                base[key] = patch[key]
        try:
            if "cost_input_usd_per_1m" in patch:
                base["cost_input_usd_per_1m"] = _parse_pricing_field(patch, "cost_input_usd_per_1m")
            if "cost_output_usd_per_1m" in patch:
                base["cost_output_usd_per_1m"] = _parse_pricing_field(
                    patch, "cost_output_usd_per_1m"
                )
            if "price_input_usd_per_1m" in patch:
                base["price_input_usd_per_1m"] = _parse_pricing_field(
                    patch, "price_input_usd_per_1m"
                )
            if "price_output_usd_per_1m" in patch:
                base["price_output_usd_per_1m"] = _parse_pricing_field(
                    patch, "price_output_usd_per_1m"
                )
            if "cost_input_cache_hit_usd_per_1m" in patch:
                base["cost_input_cache_hit_usd_per_1m"] = _parse_pricing_field(
                    patch, "cost_input_cache_hit_usd_per_1m"
                )
            if "price_input_cache_hit_usd_per_1m" in patch:
                base["price_input_cache_hit_usd_per_1m"] = _parse_pricing_field(
                    patch, "price_input_cache_hit_usd_per_1m"
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        provider = (patch.get("provider") or base.get("provider") or "deepseek").strip().lower()
        base["provider"] = provider
        if preserved_public_id:
            base["public_id"] = preserved_public_id
        merged[mid] = normalize_model_entry(mid, base)

    dup_err = validate_unique_api_ids(merged)
    if dup_err:
        return jsonify({"error": dup_err}), 400

    config["models"] = merged

    if "default_model" in data:
        dm = validate_model_id(data.get("default_model"))
        if dm and dm in config["models"]:
            config["default_model"] = dm

    if isinstance(data.get("providers"), dict):
        providers = normalize_providers_config(config.get("providers"))
        for pid, pent in data["providers"].items():
            if pid not in providers or not isinstance(pent, dict):
                continue
            env_key = PROVIDERS.get(pid, {}).get("api_key_env", "")
            if pent.get("clear_api_key"):
                providers[pid]["api_key"] = ""
            elif (pent.get("api_key") or "").strip():
                if not (os.getenv(env_key) or "").strip():
                    providers[pid]["api_key"] = (pent.get("api_key") or "").strip()
            if (pent.get("base_url") or "").strip():
                providers[pid]["base_url"] = (pent.get("base_url") or "").strip()
        config["providers"] = providers

    save_system_config(config)
    return jsonify({"models": admin_models_payload(config)})


def _extended_models_admin_response(config):
    return serialize_ocr_admin(
        config.get("extended_models"),
        config.get("providers"),
        system_config=config,
    )


@app.route("/api/admin/extended-models", methods=["GET", "PUT"])
@admin_required
def admin_extended_models():
    config = load_system_config()
    if request.method == "GET":
        return jsonify({"extended_models": _extended_models_admin_response(config)})

    data = request.get_json() or {}
    ocr_in = data.get("ocr") or data.get("extended_models", {}).get("ocr") or data
    if not isinstance(ocr_in, dict):
        return jsonify({"error": "OCR設定の形式が不正です"}), 400

    extended = normalize_extended_models_config(config.get("extended_models"))
    ocr = extended["ocr"]
    if "enabled" in ocr_in:
        ocr["enabled"] = bool(ocr_in["enabled"])
    if "engine" in ocr_in:
        ocr["engine"] = normalize_ocr_engine(ocr_in["engine"])
    if "structure_model_id" in ocr_in:
        ocr["structure_model_id"] = str(ocr_in.get("structure_model_id") or "").strip()
    default_id = (ocr_in.get("default_model_id") or "").strip()
    if default_id and default_id in ocr["models"]:
        ocr["default_model_id"] = default_id

    models_in = ocr_in.get("models")
    if isinstance(models_in, list):
        merged = {}
        for row in models_in:
            if not isinstance(row, dict):
                continue
            mid = validate_ocr_model_id(row.get("id"))
            if not mid:
                continue
            merged[mid] = normalize_ocr_model_entry(mid, row)
        if merged:
            ocr["models"] = merged
    elif isinstance(models_in, dict):
        merged = dict(ocr["models"])
        for model_id, entry in models_in.items():
            mid = validate_ocr_model_id(model_id) or str(model_id).strip()
            if not mid:
                continue
            base = merged.get(mid) or {}
            if isinstance(entry, dict):
                merged[mid] = normalize_ocr_model_entry(mid, {**base, **entry})
        ocr["models"] = merged

    if isinstance(data.get("providers"), dict):
        providers = normalize_providers_config(config.get("providers"))
        pent = data["providers"].get("anthropic")
        if isinstance(pent, dict):
            if pent.get("clear_api_key"):
                providers["anthropic"]["api_key"] = ""
            elif (pent.get("api_key") or "").strip():
                if not (os.getenv("ANTHROPIC_API_KEY") or "").strip():
                    providers["anthropic"]["api_key"] = (
                        pent.get("api_key") or ""
                    ).strip()
        config["providers"] = providers

    config["extended_models"] = extended
    save_system_config(config)
    return jsonify({"extended_models": _extended_models_admin_response(config)})


@app.route("/api/admin/extended-models/ocr", methods=["POST"])
@admin_required
def admin_create_ocr_model():
    data = request.get_json() or {}
    mid = validate_ocr_model_id(data.get("id"))
    if not mid:
        return jsonify({"error": "OCRモデルIDが不正です"}), 400

    config = load_system_config()
    extended = normalize_extended_models_config(config.get("extended_models"))
    if mid in extended["ocr"]["models"]:
        return jsonify({"error": "同じIDのOCRモデルが既に存在します"}), 409

    extended["ocr"]["models"][mid] = normalize_ocr_model_entry(mid, data)
    config["extended_models"] = extended
    save_system_config(config)
    return jsonify({"extended_models": _extended_models_admin_response(config)}), 201


@app.route("/api/admin/extended-models/ocr/<model_id>", methods=["DELETE"])
@admin_required
def admin_delete_ocr_model(model_id):
    mid = validate_ocr_model_id(model_id)
    if not mid:
        return jsonify({"error": "OCRモデルIDが不正です"}), 400

    config = load_system_config()
    extended = normalize_extended_models_config(config.get("extended_models"))
    models = extended["ocr"]["models"]
    if mid not in models:
        return jsonify({"error": "OCRモデルが見つかりません"}), 404
    if len(models) <= 1:
        return jsonify({"error": "最後の1件は削除できません"}), 400

    del models[mid]
    if extended["ocr"].get("default_model_id") == mid:
        extended["ocr"]["default_model_id"] = next(iter(models.keys()))
    config["extended_models"] = extended
    save_system_config(config)
    return jsonify({"extended_models": _extended_models_admin_response(config)})


def _image_generation_admin_response(config):
    return serialize_image_generation_admin(
        config.get("image_generation"),
        config.get("providers"),
    )


def _parse_image_pricing_field(entry, field_name):
    if field_name not in entry:
        return None
    try:
        return max(0.0, float(entry[field_name]))
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} が不正です")


def _merge_image_generation_providers(providers, data):
    if not isinstance(data.get("providers"), dict):
        return providers
    provider_in = data["providers"]
    flux_in = provider_in.get("flux_bfl")
    if not isinstance(flux_in, dict) and isinstance(provider_in.get("openai_images"), dict):
        flux_in = provider_in.get("openai_images")
    if isinstance(flux_in, dict):
        provider_in = {**provider_in, "flux_bfl": flux_in}
    for pid in IMAGE_PROVIDERS:
        pent = provider_in.get(pid)
        if not isinstance(pent, dict):
            continue
        if pid not in providers:
            providers[pid] = {"api_key": "", "base_url": ""}
        env_key = IMAGE_PROVIDERS[pid].get("api_key_env", "")
        if pent.get("clear_api_key"):
            providers[pid]["api_key"] = ""
        elif (pent.get("api_key") or "").strip():
            if not (os.getenv(env_key) or "").strip():
                providers[pid]["api_key"] = (pent.get("api_key") or "").strip()
        if (pent.get("base_url") or "").strip():
            providers[pid]["base_url"] = (pent.get("base_url") or "").strip()
    return providers


@app.route("/api/admin/image-generation", methods=["GET", "PUT"])
@admin_required
def admin_image_generation():
    config = load_system_config()
    if request.method == "GET":
        return jsonify({"image_generation": _image_generation_admin_response(config)})

    data = request.get_json() or {}
    gen_in = data.get("image_generation") or data
    if not isinstance(gen_in, dict):
        return jsonify({"error": "画像生成設定の形式が不正です"}), 400

    image_gen = normalize_image_generation_config(config.get("image_generation"))
    if "enabled" in gen_in:
        image_gen["enabled"] = bool(gen_in["enabled"])
    default_id = (gen_in.get("default_model_id") or "").strip()
    if default_id and default_id in image_gen["models"]:
        image_gen["default_model_id"] = default_id

    models_in = gen_in.get("models")
    try:
        if isinstance(models_in, list):
            merged = {}
            for row in models_in:
                if not isinstance(row, dict):
                    continue
                mid = validate_image_model_id(row.get("id"))
                if not mid:
                    continue
                for field in ("cost_usd_per_image", "price_usd_per_image"):
                    if field in row:
                        row[field] = _parse_image_pricing_field(row, field)
                merged[mid] = normalize_image_model_entry(mid, row)
            if merged:
                image_gen["models"] = merged
        elif isinstance(models_in, dict):
            merged = dict(image_gen["models"])
            for model_id, entry in models_in.items():
                mid = validate_image_model_id(model_id) or str(model_id).strip()
                if not mid:
                    continue
                base = merged.get(mid) or {}
                if isinstance(entry, dict):
                    patch = dict(entry)
                    for field in ("cost_usd_per_image", "price_usd_per_image"):
                        if field in patch:
                            patch[field] = _parse_image_pricing_field(patch, field)
                    merged[mid] = normalize_image_model_entry(mid, {**base, **patch})
            image_gen["models"] = merged
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    config["image_generation"] = image_gen
    providers = normalize_providers_config(config.get("providers"))
    config["providers"] = _merge_image_generation_providers(providers, data)
    save_system_config(config)
    return jsonify({"image_generation": _image_generation_admin_response(config)})


@app.route("/api/admin/image-generation/models", methods=["POST"])
@admin_required
def admin_create_image_model():
    data = request.get_json() or {}
    mid = validate_image_model_id(data.get("id"))
    if not mid:
        return jsonify({"error": "画像生成モデルIDが不正です"}), 400

    config = load_system_config()
    image_gen = normalize_image_generation_config(config.get("image_generation"))
    if mid in image_gen["models"]:
        return jsonify({"error": "同じIDの画像生成モデルが既に存在します"}), 409

    try:
        patch = dict(data)
        for field in ("cost_usd_per_image", "price_usd_per_image"):
            if field in patch:
                patch[field] = _parse_image_pricing_field(patch, field)
        image_gen["models"][mid] = normalize_image_model_entry(mid, patch)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    config["image_generation"] = image_gen
    save_system_config(config)
    return jsonify({"image_generation": _image_generation_admin_response(config)}), 201


@app.route("/api/admin/image-generation/models/<model_id>", methods=["DELETE"])
@admin_required
def admin_delete_image_model(model_id):
    mid = validate_image_model_id(model_id)
    if not mid:
        return jsonify({"error": "画像生成モデルIDが不正です"}), 400

    config = load_system_config()
    image_gen = normalize_image_generation_config(config.get("image_generation"))
    models = image_gen["models"]
    if mid not in models:
        return jsonify({"error": "画像生成モデルが見つかりません"}), 404
    if len(models) <= 1:
        return jsonify({"error": "最後の1件は削除できません"}), 400

    del models[mid]
    if image_gen.get("default_model_id") == mid:
        image_gen["default_model_id"] = next(iter(models.keys()))
    config["image_generation"] = image_gen
    save_system_config(config)
    return jsonify({"image_generation": _image_generation_admin_response(config)})


def serialize_search_engines_admin_panel():
    return {
        "search_engines": serialize_search_engines_admin(),
        "plans": [
            {
                "id": key,
                "name": get_plan_catalog()[key]["name"],
                "flags": extract_search_plan_flags(get_plan_features(key)),
            }
            for key in PLAN_ORDER
        ],
        "feature_keys": search_plan_flag_catalog(),
    }


@app.route("/api/admin/system-prompts")
@admin_required
def admin_system_prompts():
    from system_prompts_registry import list_system_prompts

    return jsonify(list_system_prompts())


@app.route("/api/admin/search-engines", methods=["GET", "PUT"])
@admin_required
def admin_search_engines():
    if request.method == "GET":
        return jsonify(serialize_search_engines_admin_panel())

    data = request.get_json() or {}
    config = load_system_config()

    if "search_engines" in data and isinstance(data.get("search_engines"), dict):
        incoming = data["search_engines"]
        current = dict(config.get("search_engines") or get_search_engines_config())
        config["search_engines"] = merge_search_engines_config(incoming, current)

    incoming_plans = data.get("plans")
    if isinstance(incoming_plans, dict):
        plans_cfg = dict(config.get("plans") or {})
        for key in PLAN_ORDER:
            raw = incoming_plans.get(key)
            if not isinstance(raw, dict):
                continue
            flags = normalize_search_plan_flags_payload(raw.get("flags") or raw)
            if not flags:
                continue
            entry = (
                normalize_plan_config_entry(plans_cfg.get(key))
                if isinstance(plans_cfg.get(key), dict)
                else {}
            )
            merged_feat = dict(entry.get("features") or {})
            merged_feat.update(flags)
            entry["features"] = merged_feat
            plans_cfg[key] = entry
        config["plans"] = plans_cfg

    save_system_config(config)
    return jsonify(serialize_search_engines_admin_panel())


@app.route("/api/admin/paypal")
@admin_required
def admin_get_paypal():
    return jsonify({"paypal": serialize_paypal_admin()})


def serialize_service_urls_admin():
    cfg = load_system_config().get("service_urls") or {}
    effective = {
        "frontend_base_url": public_base_url(),
        "api_portal_base_url": api_portal_base_url(),
        "api_base_url": public_api_base_url(),
    }

    def env_fallback(key, env_names):
        if cfg.get(key):
            return False
        return any((os.getenv(name) or "").strip() for name in env_names)

    return {
        **normalize_service_urls(cfg),
        "effective": effective,
        "env_fallback": {
            "frontend_base_url": env_fallback(
                "frontend_base_url", ("PUBLIC_BASE_URL", "FRONTEND_BASE_URL")
            ),
            "api_portal_base_url": env_fallback("api_portal_base_url", ("API_PORTAL_BASE_URL",)),
            "api_base_url": env_fallback("api_base_url", ("PUBLIC_API_BASE_URL",)),
        },
    }


def validate_service_url(value, label):
    from urllib.parse import urlparse

    url = (value or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{label} は http:// または https:// で始まる有効な URL を入力してください")
    return url


def _deployment_admin_payload():
    config = load_system_config()
    service_urls = serialize_service_urls_admin()
    return serialize_deployment_admin(
        deployment=config.get("deployment"),
        service_urls=service_urls,
        effective_urls=service_urls.get("effective") or {},
    )


@app.route("/api/admin/deployment")
@admin_required
def admin_get_deployment():
    payload = _deployment_admin_payload()
    return jsonify(
        {
            "deployment": payload["deployment"],
            "services": payload["services"],
            "overall_status": payload["overall_status"],
            "overall_status_label": payload["overall_status_label"],
            "chart": payload["chart"],
            "updated_at": payload["updated_at"],
        }
    )


@app.route("/api/admin/deployment/services/<service_id>/restart", methods=["POST"])
@admin_required
def admin_restart_deployment_service(service_id):
    config = load_system_config()
    deployment = normalize_deployment(config.get("deployment"))
    service_urls = serialize_service_urls_admin()
    entry, err = request_service_restart(
        service_id,
        operation_mode=deployment["operation_mode"],
    )
    if err:
        return jsonify({"error": err}), 400
    if not entry:
        return jsonify({"error": "再起動要求の作成に失敗しました"}), 500
    return jsonify(
        {
            "ok": True,
            "request_id": entry.get("id"),
            "service_id": service_id,
            "service_label": service_label(service_id),
            "status": entry.get("status") or "pending",
        }
    )


@app.route("/api/admin/deployment/restart/<request_id>")
@admin_required
def admin_deployment_restart_status(request_id):
    entry = get_restart_request(request_id)
    if not entry:
        return jsonify({"error": "再起動要求が見つかりません"}), 404

    config = load_system_config()
    deployment = normalize_deployment(config.get("deployment"))
    service_urls = serialize_service_urls_admin()
    effective = service_urls.get("effective") or {}
    service_id = entry.get("service_id")
    probe = probe_service(
        service_id,
        service_urls=service_urls,
        effective_urls=effective,
        operation_mode=deployment["operation_mode"],
    )
    entry = sync_restart_status(request_id, probe) or entry
    return jsonify(
        {
            "request": entry,
            "service": probe,
        }
    )


@app.route("/api/admin/deployment", methods=["PUT"])
@admin_required
def admin_update_deployment():
    data = request.get_json() or {}
    mode = (data.get("operation_mode") or "").strip().lower()
    if mode not in OPERATION_MODES:
        return jsonify({"error": "稼働タイプが不正です"}), 400

    config = load_system_config()
    config["deployment"] = normalize_deployment({"operation_mode": mode})
    save_system_config(config)
    payload = _deployment_admin_payload()
    return jsonify(
        {
            "deployment": payload["deployment"],
            "services": payload["services"],
            "overall_status": payload["overall_status"],
            "overall_status_label": payload["overall_status_label"],
            "chart": payload["chart"],
            "updated_at": payload["updated_at"],
        }
    )


@app.route("/api/admin/service-urls")
@admin_required
def admin_get_service_urls():
    return jsonify({"service_urls": serialize_service_urls_admin()})


@app.route("/api/admin/service-urls", methods=["PUT"])
@admin_required
def admin_update_service_urls():
    data = request.get_json() or {}
    config = load_system_config()
    service_urls = dict(config.get("service_urls") or DEFAULT_SERVICE_URLS)

    try:
        if "frontend_base_url" in data:
            service_urls["frontend_base_url"] = validate_service_url(
                data.get("frontend_base_url"), "フロントアドレス"
            )
        if "api_portal_base_url" in data:
            service_urls["api_portal_base_url"] = validate_service_url(
                data.get("api_portal_base_url"), "APIフロントアドレス"
            )
        if "api_base_url" in data:
            service_urls["api_base_url"] = validate_service_url(
                data.get("api_base_url"), "APIアドレス"
            )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    config["service_urls"] = normalize_service_urls(service_urls)
    save_system_config(config)
    return jsonify({"service_urls": serialize_service_urls_admin()})


@app.route("/api/admin/google-oauth")
@admin_required
def admin_get_google_oauth():
    return jsonify({"google_oauth": serialize_google_oauth_admin()})


@app.route("/api/admin/google-oauth", methods=["PUT"])
@admin_required
def admin_update_google_oauth():
    data = request.get_json() or {}
    config = load_system_config()
    google_oauth = dict(config["google_oauth"])

    if "client_id" in data:
        client_id = (data.get("client_id") or "").strip()
        if client_id:
            google_oauth["client_id"] = client_id

    if "client_secret" in data:
        new_secret = str(data.get("client_secret") or "").strip()
        if new_secret and not (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip():
            google_oauth["client_secret"] = new_secret

    if "redirect_uri" in data:
        redirect_uri = (data.get("redirect_uri") or "").strip()
        if redirect_uri:
            google_oauth["redirect_uri"] = redirect_uri

    if "calendar_scopes_enabled" in data:
        google_oauth["calendar_scopes_enabled"] = bool(
            data.get("calendar_scopes_enabled")
        )
    if "gmail_scopes_enabled" in data:
        google_oauth["gmail_scopes_enabled"] = bool(data.get("gmail_scopes_enabled"))

    client_id = (google_oauth.get("client_id") or "").strip()
    client_secret = (google_oauth.get("client_secret") or "").strip()
    redirect_uri = (google_oauth.get("redirect_uri") or "").strip()
    if not client_id:
        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_secret:
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not redirect_uri:
        redirect_uri = get_redirect_uri()

    if not client_id or not client_secret:
        return (
            jsonify({"error": "Client ID と Client Secret の両方を設定してください"}),
            400,
        )
    if not redirect_uri:
        return jsonify({"error": "Redirect URI を設定してください"}), 400
    if not google_oauth.get("calendar_scopes_enabled") and not google_oauth.get(
        "gmail_scopes_enabled"
    ):
        return (
            jsonify(
                {
                    "error": "カレンダーまたは Gmail のいずれかのスコープを有効にしてください"
                }
            ),
            400,
        )

    config["google_oauth"] = google_oauth
    save_system_config(config)
    return jsonify({"google_oauth": serialize_google_oauth_admin()})


@app.route("/api/admin/discord-oauth")
@admin_required
def admin_get_discord_oauth():
    return jsonify({"discord_oauth": serialize_discord_oauth_admin()})


@app.route("/api/admin/discord-oauth", methods=["PUT"])
@admin_required
def admin_update_discord_oauth():
    data = request.get_json() or {}
    config = load_system_config()
    discord_oauth = dict(config["discord_oauth"])

    if "client_id" in data:
        client_id = (data.get("client_id") or "").strip()
        if client_id:
            discord_oauth["client_id"] = client_id

    if "client_secret" in data:
        new_secret = str(data.get("client_secret") or "").strip()
        if new_secret and not (os.getenv("DISCORD_CLIENT_SECRET") or "").strip():
            discord_oauth["client_secret"] = new_secret

    if "redirect_uri" in data:
        redirect_uri = (data.get("redirect_uri") or "").strip()
        if redirect_uri:
            discord_oauth["redirect_uri"] = redirect_uri

    if "discord_login_disabled" in data:
        features = dict(config["features"])
        features["discord_login_disabled"] = bool(data.get("discord_login_disabled"))
        config["features"] = features

    client_id = (discord_oauth.get("client_id") or "").strip()
    client_secret = (discord_oauth.get("client_secret") or "").strip()
    redirect_uri = (discord_oauth.get("redirect_uri") or "").strip()
    if not client_id:
        client_id = os.getenv("DISCORD_CLIENT_ID", "").strip()
    if not client_secret:
        client_secret = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
    if not redirect_uri:
        redirect_uri = get_discord_redirect_uri()

    if not client_id or not client_secret:
        return (
            jsonify({"error": "Client ID と Client Secret の両方を設定してください"}),
            400,
        )
    if not redirect_uri:
        return jsonify({"error": "Redirect URI を設定してください"}), 400

    config["discord_oauth"] = discord_oauth
    save_system_config(config)
    payload = serialize_discord_oauth_admin()
    return jsonify(
        {
            "discord_oauth": payload,
            "features": get_feature_flags(),
        }
    )


@app.route("/api/admin/mail-server")
@admin_required
def admin_get_mail_server():
    config = load_system_config()
    return jsonify({"mail_server": serialize_mail_server_admin(config.get("mail_server"))})


@app.route("/api/admin/mail-server", methods=["PUT"])
@admin_required
def admin_update_mail_server():
    data = request.get_json() or {}
    config = load_system_config()
    mail_server = dict(config.get("mail_server") or {})

    for key in (
        "enabled",
        "verification_required",
        "use_tls",
        "use_ssl",
    ):
        if key in data:
            mail_server[key] = bool(data.get(key))

    for key in ("host", "username", "from_email", "from_name"):
        if key in data:
            mail_server[key] = str(data.get(key) or "").strip()

    if "port" in data:
        try:
            mail_server["port"] = int(data.get("port"))
        except (TypeError, ValueError):
            return jsonify({"error": "ポート番号が不正です"}), 400

    if "password" in data:
        new_password = str(data.get("password") or "").strip()
        if new_password:
            mail_server["password"] = new_password

    if mail_server.get("use_ssl"):
        mail_server["use_tls"] = False

    if mail_server.get("enabled"):
        resolved = resolve_mail_server_config(mail_server)
        if not resolved.get("host"):
            return jsonify({"error": "SMTPホストを入力してください"}), 400
        if not resolved.get("from_email"):
            return jsonify({"error": "送信元メールアドレスを入力してください"}), 400
        if resolved.get("username") and not resolved.get("password"):
            return jsonify({"error": "SMTPパスワードを入力してください"}), 400

    config["mail_server"] = normalize_mail_server(mail_server)
    save_system_config(config)
    return jsonify({"mail_server": serialize_mail_server_admin(config["mail_server"])})


@app.route("/api/admin/mail-server/test", methods=["POST"])
@admin_required
def admin_test_mail_server():
    data = request.get_json() or {}
    to_email = normalize_email(data.get("to_email"))
    if not to_email or not is_valid_email(to_email):
        return jsonify({"error": "テスト送信先のメールアドレスを入力してください"}), 400

    config = load_system_config()
    mail_cfg = config.get("mail_server") or {}
    if not mail_server_configured(mail_cfg):
        return jsonify({"error": "メールサーバーが設定されていません"}), 400

    ok, err = send_email(
        cfg=mail_cfg,
        to_email=to_email,
        subject="NEXGATE AI — メールサーバーテスト",
        body_text="これは NEXGATE AI 管理画面からのテストメールです。",
    )
    if not ok:
        return jsonify({"error": err or "テストメールの送信に失敗しました"}), 502
    return jsonify({"ok": True, "message": "テストメールを送信しました"})


@app.route("/api/admin/subscriptions")
@admin_required
def admin_get_subscriptions():
    return jsonify(serialize_subscriptions_admin())


@app.route("/api/admin/subscriptions", methods=["PUT"])
@admin_required
def admin_update_subscriptions():
    data = request.get_json() or {}
    incoming = data.get("plan_urls")
    if not isinstance(incoming, dict):
        return jsonify({"error": "plan_urls を指定してください"}), 400
    updates = {}
    for key in SUBSCRIPTION_PLAN_IDS:
        if key not in incoming:
            continue
        try:
            updates[key] = normalize_plan_subscription_url(incoming[key])
        except ValueError as e:
            return jsonify({"error": f"{key}: {e}"}), 400
    if not updates:
        return jsonify({"error": "更新するプラン URL がありません"}), 400
    try:
        save_plan_subscription_urls(updates)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(serialize_subscriptions_admin())


@app.route("/api/admin/subscriptions/create-paypal-plan", methods=["POST"])
@admin_required
def admin_create_paypal_plan():
    data = request.get_json() or {}
    plan_key = (data.get("plan_id") or "").strip()
    create_all = bool(data.get("all"))
    if create_all:
        target_keys = list(SUBSCRIPTION_PLAN_IDS)
    elif plan_key in SUBSCRIPTION_PLAN_IDS:
        target_keys = [plan_key]
    else:
        return (
            jsonify(
                {
                    "error": "plan_id（plus/pro/pro_plus/max）または all: true を指定してください"
                }
            ),
            400,
        )

    if not paypal_configured():
        return (
            jsonify(
                {
                    "error": "PayPal API 認証が未設定です（PayPal設定タブで Client ID / Secret を設定）"
                }
            ),
            400,
        )

    catalog = get_plan_catalog()
    created = []
    errors = []
    for key in target_keys:
        info = catalog[key]
        price_usd = info.get("price_usd")
        if price_usd is None or float(price_usd) <= 0:
            errors.append(
                {
                    "plan_id": key,
                    "error": "月額 USD が未設定のため PayPal プランを作成できません",
                }
            )
            continue
        paypal_name = info.get("paypal_name") or f"NEXGATE AI | {info['name']}"
        description = (
            info.get("description_en")
            or info.get("description_ja")
            or info.get("description")
            or paypal_name
        )
        try:
            result = create_paypal_subscription_plan(
                paypal_name=paypal_name,
                description=description,
                price_usd=price_usd,
            )
            save_plan_subscription_urls({key: result["subscribe_url"]})
            save_paypal_plan_api_ids(
                {
                    key: {
                        "product_id": result["product_id"],
                        "billing_plan_id": result["billing_plan_id"],
                    }
                }
            )
            created.append(
                {
                    "plan_id": key,
                    "product_id": result["product_id"],
                    "billing_plan_id": result["billing_plan_id"],
                    "subscribe_url": result["subscribe_url"],
                }
            )
        except (RuntimeError, ValueError) as e:
            errors.append({"plan_id": key, "error": str(e)})

    payload = serialize_subscriptions_admin()
    payload["created"] = created
    payload["errors"] = errors
    if not created:
        message = errors[0]["error"] if errors else "PayPal プランの作成に失敗しました"
        payload["error"] = message
        return jsonify(payload), 400
    return jsonify(payload)


@app.route("/api/admin/subscriptions/delete-paypal-plan", methods=["POST"])
@admin_required
def admin_delete_paypal_plan():
    data = request.get_json() or {}
    plan_key = (data.get("plan_id") or "").strip()
    delete_all = bool(data.get("all"))
    if delete_all:
        target_keys = list(SUBSCRIPTION_PLAN_IDS)
    elif plan_key in SUBSCRIPTION_PLAN_IDS:
        target_keys = [plan_key]
    else:
        return (
            jsonify(
                {
                    "error": "plan_id（plus/pro/pro_plus/max）または all: true を指定してください"
                }
            ),
            400,
        )

    plan_api_ids = get_paypal_plan_api_ids()
    deleted = []
    errors = []
    for key in target_keys:
        entry = plan_api_ids.get(key) or {}
        billing_plan_id = (entry.get("billing_plan_id") or "").strip()
        had_api_ids = bool(billing_plan_id)
        if had_api_ids:
            if not paypal_configured():
                errors.append(
                    {
                        "plan_id": key,
                        "error": "PayPal API 認証が未設定です（PayPal設定タブで Client ID / Secret を設定）",
                    }
                )
                continue
            try:
                deactivate_paypal_subscription_plan(billing_plan_id)
            except (RuntimeError, ValueError) as e:
                errors.append({"plan_id": key, "error": str(e)})
                continue
        try:
            clear_paypal_plan_local([key])
        except FileNotFoundError as e:
            errors.append({"plan_id": key, "error": str(e)})
            continue
        deleted.append(
            {
                "plan_id": key,
                "paypal_deactivated": had_api_ids,
                "billing_plan_id": billing_plan_id if had_api_ids else None,
            }
        )

    payload = serialize_subscriptions_admin()
    payload["deleted"] = deleted
    payload["errors"] = errors
    if not deleted:
        message = errors[0]["error"] if errors else "PayPal プランの削除に失敗しました"
        payload["error"] = message
        return jsonify(payload), 400
    return jsonify(payload)


@app.route("/api/admin/paypal", methods=["PUT"])
@admin_required
def admin_update_paypal():
    data = request.get_json() or {}
    config = load_system_config()
    paypal = dict(config["paypal"])

    if "client_id" in data:
        client_id = (data.get("client_id") or "").strip()
        if client_id and not (os.getenv("PAYPAL_CLIENT_ID") or "").strip():
            paypal["client_id"] = client_id

    if "client_secret" in data:
        new_secret = str(data.get("client_secret") or "").strip()
        if new_secret and not (os.getenv("PAYPAL_CLIENT_SECRET") or "").strip():
            paypal["client_secret"] = new_secret

    mode = (data.get("mode") or paypal.get("mode") or "sandbox").strip().lower()
    if mode not in ("sandbox", "live"):
        return jsonify({"error": "PayPalモードは sandbox または live を指定してください"}), 400
    paypal["mode"] = mode

    effective_client_id = (
        paypal.get("client_id") or os.getenv("PAYPAL_CLIENT_ID", "").strip()
    )
    effective_client_secret = (
        paypal.get("client_secret") or os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    )
    if not effective_client_id or not effective_client_secret:
        return jsonify({"error": "Client ID と Secret の両方を設定してください"}), 400

    if "webhook_id" in data:
        paypal["webhook_id"] = (data.get("webhook_id") or "").strip()

    config["paypal"] = paypal
    save_system_config(config)
    clear_token_cache()
    return jsonify({"paypal": serialize_paypal_admin()})


@app.route("/api/admin/features", methods=["PUT"])
@admin_required
def admin_update_features():
    data = request.get_json() or {}
    incoming = data.get("features") or data
    config = load_system_config()
    features = dict(DEFAULT_FEATURES)
    for key in DEFAULT_FEATURES:
        if key in incoming:
            features[key] = bool(incoming[key])
    config["features"] = features
    save_system_config(config)
    return jsonify({"features": get_feature_flags()})


def _merge_plan_config_entry(existing, raw):
    entry = normalize_plan_config_entry(existing) if isinstance(existing, dict) else {}
    if "description" in raw:
        entry["description_ja"] = normalize_plan_description(raw["description"])
    if "description_ja" in raw:
        entry["description_ja"] = normalize_plan_description(raw["description_ja"])
    if "description_en" in raw:
        entry["description_en"] = normalize_plan_description(raw["description_en"])
    if "price_usd" in raw:
        val = raw["price_usd"]
        entry["price_usd"] = None if val is None else float(val)
    if "price_label" in raw:
        entry["price_label"] = str(raw["price_label"] or "").strip()
    if "features" in raw:
        try:
            features = normalize_plan_features_payload(None, raw["features"])
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if features is not None:
            merged_feat = dict(entry.get("features") or {})
            merged_feat.update(features)
            entry["features"] = merged_feat
    return entry


@app.route("/api/admin/plans/<plan_id>", methods=["GET", "PUT"])
@admin_required
def admin_plan_detail(plan_id):
    key = (plan_id or "").strip().lower()
    if key not in PLANS:
        return jsonify({"error": "プランが見つかりません"}), 404
    if request.method == "GET":
        return jsonify({"plan": serialize_admin_plan(key)})

    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "プラン情報が不正です"}), 400
    try:
        config = load_system_config()
        plans_cfg = dict(config.get("plans") or {})
        entry = _merge_plan_config_entry(plans_cfg.get(key), data)
        if entry:
            plans_cfg[key] = entry
        config["plans"] = plans_cfg
        save_system_config(config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"plan": serialize_admin_plan(key)})


@app.route("/api/admin/plans", methods=["PUT"])
@admin_required
def admin_update_plans():
    data = request.get_json() or {}
    incoming = data.get("plans") or data
    if not isinstance(incoming, dict):
        return jsonify({"error": "プラン情報が不正です"}), 400

    try:
        config = load_system_config()
        plans_cfg = dict(config.get("plans") or {})
        for key in PLAN_ORDER:
            raw = incoming.get(key)
            if not isinstance(raw, dict):
                continue
            entry = _merge_plan_config_entry(plans_cfg.get(key), raw)
            if entry:
                plans_cfg[key] = entry
        config["plans"] = plans_cfg
        save_system_config(config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"plans": [serialize_admin_plan(key) for key in PLAN_ORDER]})


def serialize_plan_features_admin():
    catalog = get_plan_catalog()
    plans = []
    for key in PLAN_ORDER:
        info = catalog[key]
        feat = get_plan_features(key)
        plans.append(
            {
                "id": key,
                "name": info["name"],
                "flags": extract_plan_flags(feat),
            }
        )
    return {"plans": plans, "feature_keys": admin_flag_catalog(), "feature_groups": admin_flag_groups()}


@app.route("/api/admin/plan-features", methods=["GET", "PUT"])
@admin_required
def admin_plan_features():
    if request.method == "GET":
        return jsonify(serialize_plan_features_admin())

    data = request.get_json() or {}
    incoming = data.get("plans") or data
    if not isinstance(incoming, dict):
        return jsonify({"error": "プラン機能の形式が不正です"}), 400

    try:
        config = load_system_config()
        plans_cfg = dict(config.get("plans") or {})
        for key in PLAN_ORDER:
            raw = incoming.get(key)
            if not isinstance(raw, dict):
                continue
            flags = normalize_plan_flags_payload(raw.get("flags") or raw)
            if not flags:
                continue
            entry = normalize_plan_config_entry(plans_cfg.get(key)) if isinstance(
                plans_cfg.get(key), dict
            ) else {}
            merged_feat = dict(entry.get("features") or {})
            merged_feat.update(flags)
            entry["features"] = merged_feat
            plans_cfg[key] = entry
        config["plans"] = plans_cfg
        save_system_config(config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(serialize_plan_features_admin())


def admin_plan_names():
    catalog = get_plan_catalog()
    return {key: info["name"] for key, info in catalog.items()}


@app.route("/api/admin/coupons")
@admin_required
def admin_list_coupons():
    return jsonify({"coupons": list_coupons_serialized(admin_plan_names())})


@app.route("/api/admin/coupons", methods=["POST"])
@admin_required
def admin_create_coupon():
    coupon, err = create_coupon(request.get_json() or {})
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"coupon": serialize_coupon(coupon, admin_plan_names())}), 201


@app.route("/api/admin/coupons/<coupon_id>", methods=["PUT"])
@admin_required
def admin_update_coupon(coupon_id):
    data = request.get_json() or {}
    if "enabled" not in data:
        return jsonify({"error": "更新項目が指定されていません"}), 400
    coupon, err = set_coupon_enabled(coupon_id, data.get("enabled"))
    if err:
        return jsonify({"error": err}), 404
    return jsonify({"coupon": serialize_coupon(coupon, admin_plan_names())})


@app.route("/api/admin/coupons/<coupon_id>", methods=["DELETE"])
@admin_required
def admin_delete_coupon(coupon_id):
    _, err = delete_coupon(coupon_id)
    if err:
        return jsonify({"error": err}), 404
    return jsonify({"ok": True})


@app.route("/api/coupons/redeem", methods=["POST"])
@login_required
def redeem_coupon_api():
    if feature_blocked("coupon_disabled"):
        return jsonify({"error": "現在、クーポンコードの利用は停止されています"}), 403

    data = request.get_json() or {}
    code = data.get("code") or ""
    if not code.strip():
        return jsonify({"error": "クーポンコードを入力してください"}), 400

    username = session["user"]["username"]
    users = load_users()
    record = users.get(username)
    if not record:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    if is_user_blocked(record):
        return jsonify({"error": "アカウントが利用停止中です"}), 403

    def add_balance(user_record, amount):
        return round(user_balance(user_record) + amount, 2)

    result, err = redeem_coupon(
        username,
        code,
        record,
        set(PLANS.keys()),
        add_balance,
        add_plan_hours_fn=add_plan_coupon_hours,
    )
    if err:
        return jsonify({"error": err}), 400

    save_users(users)
    session["user"] = build_session_user(username, record)
    summary = build_billing_summary(username)
    return jsonify(
        {
            "message": result["message"],
            "user": session["user"],
            "billing": summary,
        }
    )


@app.route("/api/admin/users", methods=["POST"])
@admin_required
def admin_create_user():
    data = request.get_json() or {}
    username = normalize_username(data.get("username"))
    password = data.get("password") or ""

    username_error = validate_new_username(username)
    if username_error:
        return jsonify({"error": username_error}), 400
    if len(password) < 4:
        return jsonify({"error": "パスワードは4文字以上で入力してください"}), 400

    users = load_users()
    if username in users:
        return jsonify({"error": "このユーザー名は登録できません"}), 409

    display_name = (data.get("display_name") or username).strip()
    role = normalize_user_role(data.get("role"))
    plan = data.get("plan")
    if plan is not None:
        plan = normalize_plan(plan)

    record = create_user_record(
        password,
        display_name=display_name,
        role=role,
        plan=plan,
        email=data.get("email"),
        phone=data.get("phone"),
        last_name=data.get("last_name"),
        first_name=data.get("first_name"),
    )
    if not record["display_name"]:
        record["display_name"] = username

    if record["email"] and not is_valid_email(record["email"]):
        return jsonify({"error": "メールアドレスの形式が正しくありません"}), 400

    users[username] = record
    save_users(users)
    return jsonify({"user": serialize_admin_user(username, record, detailed=True)}), 201


@app.route("/api/admin/users/<username>", methods=["GET"])
@admin_required
def admin_get_user(username):
    username = username.strip().lower()
    users = load_users()
    record = users.get(username)
    if not record:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    return jsonify({"user": serialize_admin_user(username, record, detailed=True)})


@app.route("/api/admin/users/<username>", methods=["PUT"])
@admin_required
def admin_update_user(username):
    username = username.strip().lower()
    data = request.get_json() or {}
    users = load_users()
    record = users.get(username)
    if not record:
        return jsonify({"error": "ユーザーが見つかりません"}), 404

    if "display_name" in data:
        name = (data.get("display_name") or "").strip()
        if not name:
            return jsonify({"error": "表示名を入力してください"}), 400
        record["display_name"] = name

    if "last_name" in data:
        record["last_name"] = normalize_real_name_field(data.get("last_name"))
    if "first_name" in data:
        record["first_name"] = normalize_real_name_field(data.get("first_name"))

    if "email" in data:
        email = normalize_email(data.get("email"))
        if email and not is_valid_email(email):
            return jsonify({"error": "メールアドレスの形式が正しくありません"}), 400
        record["email"] = email

    if "phone" in data:
        record["phone"] = normalize_phone(data.get("phone"))

    if "plan" in data:
        record["plan"] = normalize_plan(data.get("plan"))

    if "plan_expires_at" in data:
        record["plan_expires_at"] = normalize_plan_expires_at(data.get("plan_expires_at"))

    if "balance" in data:
        try:
            record["balance"] = round(float(data.get("balance")), 2)
        except (TypeError, ValueError):
            return jsonify({"error": "残高が不正です"}), 400

    if "api_enabled" in data:
        record["api_enabled"] = bool(data.get("api_enabled"))
        plan = normalize_plan(record.get("plan"))
        if record["api_enabled"] and not plan_api_access_enabled(plan):
            record["api_access_bypass_plan"] = True
        elif not record["api_enabled"]:
            record.pop("api_access_bypass_plan", None)

    if "blocked" in data:
        blocked = bool(data.get("blocked"))
        if record.get("role") == "admin":
            if blocked:
                return jsonify({"error": "管理者アカウントの利用停止はできません"}), 400
        else:
            record["blocked"] = blocked

    if "payment_records" in data:
        record["payment_records"] = normalize_payment_records(data.get("payment_records"))

    if "usage_quota_override_usd" in data:
        raw = data.get("usage_quota_override_usd")
        if raw is None or raw == "":
            record.pop("usage_quota_override_usd", None)
        else:
            try:
                record["usage_quota_override_usd"] = round(float(raw), 6)
            except (TypeError, ValueError):
                return jsonify({"error": "利用枠の上書き値が不正です"}), 400

    if "usage_cost_usd" in data:
        try:
            cost = round(float(data.get("usage_cost_usd") or 0), 6)
        except (TypeError, ValueError):
            return jsonify({"error": "利用量が不正です"}), 400
        usage = get_user_usage(username)
        usage["usage_cost_usd"] = max(0.0, cost)
        record["usage"] = usage

    if data.get("usage_reset"):
        pool = usage_pool_for_record(record)
        record["usage"] = {
            "period": pool["pool_id"],
            "usage_cost_usd": 0.0,
            "tool_usage_cost_usd": 0.0,
        }

    if "entitlements" in data:
        record["entitlements"] = normalize_entitlements(
            data.get("entitlements"), plan_monthly_ai_budget_usd
        )
        ents = active_entitlements(record, plan_budget_fn=plan_monthly_ai_budget_usd)
        if ents:
            record["plan"] = highest_plan_from_entitlements(
                ents, normalize_plan, plan_tier_rank_fn=plan_tier_rank
            )

    if "add_entitlement" in data:
        ent = data.get("add_entitlement") or {}
        plan_id = ent.get("plan_id") or record.get("plan")
        try:
            quantity = max(1, int(ent.get("quantity") or 1))
        except (TypeError, ValueError):
            quantity = 1
        try:
            months = max(1, int(ent.get("months") or 1))
        except (TypeError, ValueError):
            months = 1
        add_plan_entitlement(
            record,
            plan_id,
            months=months,
            quantity=quantity,
            source="admin",
            plan_budget_fn=plan_monthly_ai_budget_usd,
            normalize_plan_fn=normalize_plan,
            add_one_month_fn=add_one_calendar_month,
            plan_tier_rank_fn=plan_tier_rank,
        )

    save_users(users)
    current = session["user"]["username"]
    if current == username:
        session["user"] = build_session_user(username, record)
    return jsonify({"user": serialize_admin_user(username, record, detailed=True)})


@app.route("/api/admin/users/<username>/balance-adjustment", methods=["POST"])
@admin_required
def admin_user_balance_adjustment(username):
    username = username.strip().lower()
    data = request.get_json() or {}
    try:
        amount = int(round(float(data.get("amount_jpy") or 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "調整金額が不正です"}), 400
    if amount == 0:
        return jsonify({"error": "0以外の金額を指定してください"}), 400

    note = (data.get("note") or "管理者調整").strip()[:240]
    users = load_users()
    record = users.get(username)
    if not record:
        return jsonify({"error": "ユーザーが見つかりません"}), 404

    records = normalize_payment_records(record.get("payment_records"))
    records.append(
        {
            "id": str(uuid.uuid4()),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": abs(amount),
            "method": "管理者",
            "note": f"{'付与' if amount > 0 else '減算'}: {note}",
            "status": "paid" if amount > 0 else "refunded",
        }
    )
    record["payment_records"] = records
    record["balance"] = round(max(0.0, user_balance(record) + float(amount)), 2)
    save_users(users)
    return jsonify({"user": serialize_admin_user(username, record, detailed=True)})


@app.route("/api/admin/users/<username>/billing-events")
@admin_required
def admin_user_billing_events(username):
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    try:
        limit = min(200, max(1, int(request.args.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    rows, total = list_billing_events_for_user(username, limit=limit, offset=offset)
    return jsonify(
        {
            "events": [serialize_billing_event(row, "ja") for row in rows],
            "total": total,
            "billing_model_note": billing_model_note("ja"),
        }
    )


@app.route("/api/admin/users/<username>", methods=["DELETE"])
@admin_required
def admin_delete_user(username):
    username = username.strip().lower()
    current = session["user"]["username"]
    if username == current:
        return jsonify({"error": "自分自身は削除できません"}), 400

    users = load_users()
    record = users.get(username)
    if not record:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    if record.get("role") == "admin":
        return jsonify({"error": "管理者アカウントは削除できません"}), 400
    if is_user_blocked(record):
        return jsonify(
            {"error": "利用停止中のユーザーは削除できません。ブロックを解除してから削除してください"}
        ), 400

    del users[username]
    save_users(users)
    return jsonify({"ok": True})


@app.route("/api/settings/general", methods=["PUT"])
@login_required
def update_general():
    data = request.get_json() or {}
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username, {})
    display_name = (data.get("display_name") or "").strip()
    theme = data.get("theme", "dark")
    language = data.get("language", "ja")
    chat_background_pattern = normalize_chat_background_pattern(
        data.get("chat_background_pattern", record.get("chat_background_pattern"))
    )

    if not display_name:
        return jsonify({"error": "表示名を入力してください"}), 400
    if theme not in ("dark", "light", "system", "midnight"):
        return jsonify({"error": "テーマが不正です"}), 400
    if language not in ("ja", "en", "ko"):
        return jsonify({"error": "言語が不正です"}), 400

    users[username]["display_name"] = display_name
    users[username]["theme"] = theme
    users[username]["language"] = language
    users[username]["chat_background_pattern"] = chat_background_pattern
    save_users(users)
    session["user"] = build_session_user(username, users[username])
    return jsonify({"user": session["user"]})


@app.route("/api/settings/contact", methods=["PUT"])
@login_required
def update_contact():
    data = request.get_json() or {}
    email = normalize_email(data.get("email"))
    phone = normalize_phone(data.get("phone"))
    billing = normalize_billing(data.get("billing"))

    if not is_valid_email(email):
        return jsonify({"error": "メールアドレスの形式が正しくありません"}), 400
    if len(phone) > 32:
        return jsonify({"error": "電話番号が長すぎます"}), 400
    if len(billing["name"]) > 120 or len(billing["address"]) > 240:
        return jsonify({"error": "請求先情報が長すぎます"}), 400

    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    record["email"] = email
    record["phone"] = phone
    record["billing"] = billing
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify({"user": session["user"]})


@app.route("/api/settings/api-access", methods=["PUT"])
@login_required
def update_api_access_settings():
    data = request.get_json() or {}
    if "api_enabled" not in data and "on_demand_billing_enabled" not in data:
        return jsonify({"error": "api_enabled または on_demand_billing_enabled が必要です"}), 400

    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})

    if "api_enabled" in data:
        enabled = bool(data.get("api_enabled"))
        if enabled and record.get("role") != "admin" and not user_plan_api_access_allowed(record):
            return jsonify({"error": "現在のプランでは API アクセスを利用できません"}), 403
        record["api_enabled"] = enabled

    if "on_demand_billing_enabled" in data:
        record["on_demand_billing_enabled"] = bool(
            data.get("on_demand_billing_enabled")
        )

    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify({"user": session["user"]})


@app.route("/api/settings/billing-info", methods=["PUT"])
@login_required
def update_billing_info_settings():
    data = request.get_json() or {}
    email = normalize_email(data.get("email"))
    phone = normalize_phone(data.get("phone"))
    billing = normalize_billing(data.get("billing"))
    last_name = normalize_real_name_field(data.get("last_name"))
    first_name = normalize_real_name_field(data.get("first_name"))
    billing_currency = normalize_billing_currency(data.get("billing_currency"))

    if not is_valid_email(email):
        return jsonify({"error": "メールアドレスの形式が正しくありません"}), 400
    if len(phone) > 32:
        return jsonify({"error": "電話番号が長すぎます"}), 400
    if len(billing["name"]) > 120 or len(billing["address"]) > 240:
        return jsonify({"error": "請求先情報が長すぎます"}), 400
    if len(last_name) > 64 or len(first_name) > 64:
        return jsonify({"error": "氏名が長すぎます"}), 400

    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    record["email"] = email
    record["phone"] = phone
    record["billing"] = billing
    record["last_name"] = last_name
    record["first_name"] = first_name
    record["billing_currency"] = billing_currency
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify({"user": session["user"]})


@app.route("/api/settings/embed", methods=["PUT"])
@login_required
def update_embed_settings():
    data = request.get_json() or {}
    if (
        "web_search_enabled" not in data
        and "geolocation_enabled" not in data
        and "image_generation_enabled" not in data
        and "user_questions_enabled" not in data
    ):
        return jsonify(
            {
                "error": "web_search_enabled、geolocation_enabled、image_generation_enabled、または user_questions_enabled が必要です"
            }
        ), 400

    if "web_search_enabled" in data and feature_blocked("search_disabled"):
        return jsonify({"error": "現在、Web検索は一時的に制限されています"}), 403

    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    plan = normalize_plan(record.get("plan"))
    if "web_search_enabled" in data:
        if bool(data.get("web_search_enabled")) and not plan_web_search_enabled(plan):
            return jsonify({"error": "現在のプランではWeb検索を有効にできません"}), 403
        record["web_search_enabled"] = bool(data.get("web_search_enabled"))
    if "geolocation_enabled" in data:
        if bool(data.get("geolocation_enabled")) and not plan_geolocation_enabled(plan):
            return jsonify({"error": "現在のプランでは位置情報を有効にできません"}), 403
        record["geolocation_enabled"] = bool(data.get("geolocation_enabled"))
    if "image_generation_enabled" in data:
        if bool(data.get("image_generation_enabled")) and not plan_image_generation_enabled(
            plan
        ):
            return jsonify({"error": "現在のプランでは画像生成を有効にできません"}), 403
        record["image_generation_enabled"] = bool(data.get("image_generation_enabled"))
    if "user_questions_enabled" in data:
        record["user_questions_enabled"] = bool(data.get("user_questions_enabled"))
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify({"user": session["user"]})


@app.route("/api/geolocation/city", methods=["POST"])
@login_required
def geolocation_city_api():
    username = session["user"]["username"]
    users = load_users()
    if not user_geolocation_enabled(users.get(username, {})):
        return jsonify({"error": "位置情報は無効です"}), 403

    data = request.get_json() or {}
    try:
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"error": "lat と lon が必要です"}), 400

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"error": "座標が不正です"}), 400

    city = reverse_geocode_city(lat, lon)
    if not city:
        return jsonify({"error": "位置の取得に失敗しました"}), 502
    return jsonify({"city": city})


@app.route("/api/settings/extensions", methods=["PUT"])
@login_required
def update_extensions_settings():
    data = request.get_json() or {}
    if (
        "tasks_enabled" not in data
        and "memory_enabled" not in data
        and "projects_enabled" not in data
        and "deep_research_enabled" not in data
        and "intelligent_search_override_enabled" not in data
        and "image_generation_enabled" not in data
        and "info_expert_enabled" not in data
    ):
        return jsonify(
            {
                "error": "tasks_enabled、memory_enabled、projects_enabled、deep_research_enabled、intelligent_search_override_enabled、image_generation_enabled、または info_expert_enabled が必要です"
            }
        ), 400

    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    plan = normalize_plan(record.get("plan"))
    if "tasks_enabled" in data:
        if bool(data.get("tasks_enabled")) and not plan_tasks_enabled(plan):
            return jsonify({"error": "現在のプランでは TASKS を有効にできません"}), 403
        record["tasks_enabled"] = bool(data.get("tasks_enabled"))
    if "memory_enabled" in data:
        if bool(data.get("memory_enabled")) and not plan_memory_enabled(plan):
            return jsonify({"error": "現在のプランではメモリを有効にできません"}), 403
        record["memory_enabled"] = bool(data.get("memory_enabled"))
    if "projects_enabled" in data:
        if bool(data.get("projects_enabled")) and not plan_projects_enabled(plan):
            return jsonify({"error": "現在のプランではプロジェクトスペースを有効にできません"}), 403
        record["projects_enabled"] = bool(data.get("projects_enabled"))
    if "deep_research_enabled" in data:
        if bool(data.get("deep_research_enabled")) and not plan_deep_research_enabled(plan):
            return jsonify({"error": "現在のプランでは DeepResearch を有効にできません"}), 403
        record["deep_research_enabled"] = bool(data.get("deep_research_enabled"))
    if "intelligent_search_override_enabled" in data:
        if bool(data.get("intelligent_search_override_enabled")) and not user_web_search_enabled(record):
            return jsonify({"error": "IntelligentSearch がオンのときのみ有効にできます"}), 403
        record["intelligent_search_override_enabled"] = bool(
            data.get("intelligent_search_override_enabled")
        )
    if "image_generation_enabled" in data:
        if bool(data.get("image_generation_enabled")) and not plan_image_generation_enabled(plan):
            return jsonify({"error": "現在のプランでは画像生成を有効にできません"}), 403
        record["image_generation_enabled"] = bool(data.get("image_generation_enabled"))
    if "info_expert_enabled" in data:
        record["info_expert_enabled"] = bool(data.get("info_expert_enabled"))
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify({"user": session["user"]})


@app.route("/api/settings/deep-research", methods=["PUT"])
@login_required
def update_deep_research_settings():
    data = request.get_json() or {}
    if "deep_research_prefs" not in data:
        return jsonify({"error": "deep_research_prefs が必要です"}), 400

    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    if not plan_deep_research_enabled(normalize_plan(record.get("plan"))):
        return jsonify({"error": "現在のプランでは DeepResearch 設定を変更できません"}), 403

    raw_prefs = data.get("deep_research_prefs")
    if not isinstance(raw_prefs, dict):
        return jsonify({"error": "deep_research_prefs はオブジェクトである必要があります"}), 400
    record["deep_research_prefs"] = normalize_deep_research_prefs(raw_prefs)
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify({"user": session["user"]})


def _custom_agent_share_url(share_id):
    return public_page_url(f"/share/agent/{share_id}")


def _custom_agent_api_payload(agent, viewer_username=None):
    return enrich_custom_agent(
        agent,
        viewer_username=viewer_username,
        share_url_builder=_custom_agent_share_url,
    )


@app.route("/share/agent/<share_id>")
def share_agent_page(share_id):
    agent = find_custom_agent_by_share_id(share_id)
    if not agent:
        return render_template("share_not_found.html"), 404
    vis = agent.get("visibility") or VISIBILITY_PRIVATE
    if vis == VISIBILITY_PRIVATE:
        return render_template("share_not_found.html"), 404
    increment_custom_agent_usage(share_id)
    return render_template(
        "share_agent.html",
        agent={
            "name": agent.get("name") or "エージェント",
            "description": (agent.get("description") or "").strip(),
            "created_label": agent.get("created_at", "")[:10],
            "visibility": vis,
            "usage_count": int(agent.get("usage_count") or 0),
        },
    )


@app.route("/api/custom-agents", methods=["GET", "POST"])
@login_required
def api_custom_agents_list_create():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username, {})
    if not user_custom_agents_enabled(record):
        return jsonify({"error": "現在のプランではカスタムエージェントは利用できません"}), 403

    if request.method == "GET":
        agents = [
            _custom_agent_api_payload(a, viewer_username=username)
            for a in load_user_custom_agents(username)
        ]
        return jsonify({"agents": agents})

    data = request.get_json() or {}
    entry, err = create_custom_agent(
        username,
        name=data.get("name"),
        description=data.get("description"),
        instructions=data.get("instructions"),
        knowledge_items=data.get("knowledge_items"),
        favorite=bool(data.get("favorite")),
        visibility=data.get("visibility"),
        model_id=data.get("model_id"),
    )
    if err:
        status = 400 if "最大" in err else 400
        return jsonify({"error": err}), status
    return jsonify(_custom_agent_api_payload(entry, viewer_username=username)), 201


@app.route("/api/custom-agents/<agent_id>", methods=["PUT", "DELETE"])
@login_required
def api_custom_agents_item(agent_id):
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username, {})
    if not user_custom_agents_enabled(record):
        return jsonify({"error": "現在のプランではカスタムエージェントは利用できません"}), 403

    agent_id = (agent_id or "").strip()
    if not agent_id:
        return jsonify({"error": "id が必要です"}), 400

    if request.method == "DELETE":
        ok, err = delete_custom_agent(username, agent_id)
        if err:
            return jsonify({"error": err}), 404
        return jsonify({"deleted": ok})

    data = request.get_json() or {}
    patch = {}
    if "name" in data:
        patch["name"] = data.get("name")
    if "description" in data:
        patch["description"] = data.get("description")
    if "instructions" in data:
        patch["instructions"] = data.get("instructions")
    if "knowledge_items" in data:
        patch["knowledge_items"] = data.get("knowledge_items")
    if "favorite" in data:
        patch["favorite"] = bool(data.get("favorite"))
    if "visibility" in data:
        vis = (data.get("visibility") or "").strip().lower()
        if vis not in (VISIBILITY_PRIVATE, VISIBILITY_UNLISTED, VISIBILITY_PUBLIC):
            return jsonify({"error": "無効な公開設定です"}), 400
        patch["visibility"] = vis
    if "model_id" in data:
        patch["model_id"] = data.get("model_id")
    if "force_reasoning" in data:
        patch["force_reasoning"] = bool(data.get("force_reasoning"))
    if "reasoning_display" in data:
        mode = (data.get("reasoning_display") or "").strip().lower()
        if mode not in (
            REASONING_DISPLAY_FORCE_SHOW,
            REASONING_DISPLAY_HIDE,
            REASONING_DISPLAY_USER,
        ):
            return jsonify({"error": "無効な推論表示設定です"}), 400
        patch["reasoning_display"] = mode
    if "show_knowledge" in data:
        patch["show_knowledge"] = bool(data.get("show_knowledge"))
    if "show_personality" in data:
        patch["show_personality"] = bool(data.get("show_personality"))
    if not patch:
        return jsonify({"error": "更新する項目がありません"}), 400
    entry, err = update_custom_agent(username, agent_id, **patch)
    if err:
        return jsonify({"error": err}), 404 if "見つかりません" in err else 400
    return jsonify(_custom_agent_api_payload(entry, viewer_username=username))


@app.route("/api/generated-images/<image_id>")
def serve_generated_image(image_id):
    sig = (request.args.get("sig") or "").strip()
    sess_user = session.get("user") or {}
    session_username = (
        sess_user.get("username") if isinstance(sess_user, dict) else str(sess_user or "")
    )
    record = can_access_image(image_id, sig=sig, session_user=session_username)
    if not record:
        return jsonify({"error": "画像が見つかりません"}), 404
    path = record.get("path")
    if not path or not Path(path).is_file():
        return jsonify({"error": "画像が見つかりません"}), 404
    return send_file(
        path,
        mimetype=record.get("content_type") or "image/jpeg",
        max_age=31536000,
        conditional=True,
    )


@app.route("/api/image-generation/options")
@login_required
def image_generation_options():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username, {})
    if not user_image_generation_enabled(record):
        return jsonify({"error": "画像生成が無効です"}), 403
    plan = normalize_plan(record.get("plan"))
    config = load_system_config()
    payload = serialize_image_generation_options(
        plan, config.get("image_generation"), record.get("image_generation_prefs")
    )
    return jsonify(payload)


@app.route("/api/settings/image-generation", methods=["PUT"])
@login_required
def update_image_generation_settings():
    data = request.get_json() or {}
    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    plan = normalize_plan(record.get("plan"))
    if not user_image_generation_enabled(record) and not (
        data.get("model_id") or data.get("width") or data.get("height") or data.get("size_preset")
    ):
        return jsonify({"error": "画像生成が無効です"}), 403

    prev = record.get("image_generation_prefs")
    if not isinstance(prev, dict):
        prev = {}
    patch = dict(prev)
    if "model_id" in data:
        patch["model_id"] = (data.get("model_id") or "").strip()
    if "size_preset" in data:
        patch["size_preset"] = (data.get("size_preset") or "").strip()
    if "width" in data or "height" in data:
        if "width" in data:
            patch["width"] = data.get("width")
        if "height" in data:
            patch["height"] = data.get("height")

    config = load_system_config()
    normalized = normalize_user_image_generation_prefs(
        patch, plan_key=plan, image_generation=config.get("image_generation")
    )
    models = list_image_models_for_plan(plan, config.get("image_generation"))
    allowed_ids = {m["id"] for m in models}
    if normalized["model_id"] not in allowed_ids:
        return jsonify({"error": "選択したエンジンは現在のプランでは利用できません"}), 403

    record["image_generation_prefs"] = {
        "model_id": normalized["model_id"],
        "width": normalized["width"],
        "height": normalized["height"],
        "size_preset": normalized.get("size_preset"),
    }
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify(
        {
            "user": session["user"],
            "options": serialize_image_generation_options(
                plan, config.get("image_generation"), record["image_generation_prefs"]
            ),
        }
    )


@app.route("/api/settings/performance", methods=["PUT"])
@login_required
def update_performance_settings():
    data = request.get_json() or {}
    if (
        "reasoning_disabled" not in data
        and "reasoning_in_english" not in data
        and "cost_performance_maximized" not in data
    ):
        return jsonify(
            {
                "error": "reasoning_disabled、reasoning_in_english、または cost_performance_maximized が必要です"
            }
        ), 400

    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    if "reasoning_disabled" in data:
        record["reasoning_disabled"] = bool(data.get("reasoning_disabled"))
        if record["reasoning_disabled"]:
            record["reasoning_in_english"] = False
    if "cost_performance_maximized" in data:
        record["cost_performance_maximized"] = bool(data.get("cost_performance_maximized"))
    if "reasoning_in_english" in data:
        wants_english = bool(data.get("reasoning_in_english"))
        if wants_english and user_reasoning_disabled(record):
            record["reasoning_in_english"] = False
        else:
            record["reasoning_in_english"] = wants_english
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify({"user": session["user"]})


def _start_google_oauth(mode, *, username=None):
    if not google_oauth_configured():
        return None, "not_configured"
    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state
    session["google_oauth_mode"] = mode
    if username:
        session["google_oauth_username"] = username
    elif "google_oauth_username" in session:
        session.pop("google_oauth_username", None)
    if mode == OAUTH_MODE_LOGIN:
        return build_login_authorization_url(state), None
    if mode == OAUTH_MODE_LINK:
        return build_login_authorization_url(state), None
    return build_authorization_url(state), None


def _google_oauth_userinfo_from_code(code):
    payload = exchange_code_for_tokens(code)
    access = (payload.get("access_token") or "").strip()
    if not access:
        raise RuntimeError("Google did not return an access token")
    info = fetch_google_userinfo(access)
    sub = (info.get("sub") or "").strip()
    email = normalize_email(info.get("email"))
    name = (info.get("name") or info.get("given_name") or "").strip()
    if not sub or not email:
        raise RuntimeError("Google profile is incomplete")
    return sub, email, name


def _complete_google_tools_callback(username, code):
    payload = exchange_code_for_tokens(code)
    store_tokens_for_user(username, payload)
    users = load_users()
    record = users.setdefault(username, {})
    record.setdefault("google_calendar_enabled", False)
    record.setdefault("google_gmail_enabled", False)
    save_users(users)
    session["user"] = build_session_user(username, record)
    return url_for("settings_page") + "#integrations/google?google_connected=1"


def _complete_google_link_callback(username, code):
    sub, email, _name = _google_oauth_userinfo_from_code(code)
    users = load_users()
    record = users.setdefault(username, {})
    if not user_google_login_enabled(record):
        raise RuntimeError("先に Google ログインを許可するトグルをオンにしてください")
    other_user, _ = find_user_by_google_sub(users, sub)
    if other_user and other_user != username:
        raise RuntimeError("この Google アカウントは別のユーザーに紐づいています")
    record["google_sub"] = sub
    record["google_email"] = email
    save_users(users)
    session["user"] = build_session_user(username, record)
    return url_for("settings_page") + "#integrations/google?google_login_linked=1"


def _oauth_redirect_with_param(base_url, param_name, param_value):
    from urllib.parse import urlencode, urlparse, urlunparse, parse_qs
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query[param_name] = [str(param_value)[:500]]
    new_query = urlencode(query, doseq=True)
    return redirect(urlunparse(parsed._replace(query=new_query)))


def _complete_google_login_callback(code):
    if not system_google_login_allowed():
        raise RuntimeError("Google ログインは現在利用できません")
    sub, email, name = _google_oauth_userinfo_from_code(code)
    users = load_users()
    username, record = find_user_by_google_sub(users, sub)
    if username and record:
        if not user_google_login_enabled(record):
            raise RuntimeError(
                "このアカウントでは Google ログインが無効です。設定の連携から有効にしてください"
            )
        if is_user_blocked(record) and record.get("role") != "admin":
            raise RuntimeError("このアカウントは利用停止中です")
        session["user"] = build_session_user(username, record)
        return url_for("chat_page")

    existing_user, existing_record = find_user_by_google_email(users, email)
    if existing_user and existing_record:
        if user_google_login_linked(existing_record) and user_google_login_enabled(
            existing_record
        ):
            if is_user_blocked(existing_record) and existing_record.get("role") != "admin":
                raise RuntimeError("このアカウントは利用停止中です")
            existing_record["google_sub"] = sub
            existing_record["google_email"] = email
            save_users(users)
            session["user"] = build_session_user(existing_user, existing_record)
            return url_for("chat_page")
        raise RuntimeError(
            "このメールは既に登録されています。ログイン後、設定の連携から Google ログインを有効にしてください"
        )

    if feature_blocked("registration_disabled"):
        raise RuntimeError("現在、新規登録は停止されています")

    username, record = create_google_user_record(
        display_name=name or email.split("@")[0],
        email=email,
        google_sub=sub,
        google_email=email,
    )
    users[username] = record
    save_users(users)
    session["user"] = build_session_user(username, record)
    return url_for("chat_page")


@app.route("/api/auth/google")
@login_required
def google_auth_start():
    url, err = _start_google_oauth(OAUTH_MODE_TOOLS, username=session["user"]["username"])
    if err:
        return jsonify({"error": "Google OAuth が設定されていません"}), 503
    return redirect(url)


@app.route("/api/auth/google/login")
def google_auth_login_start():
    if not system_google_login_allowed():
        return redirect(url_for("login") + "?google_login_error=disabled")
    url, err = _start_google_oauth(OAUTH_MODE_LOGIN)
    if err:
        return redirect(url_for("login") + "?google_login_error=not_configured")
    return redirect(url)


@app.route("/api/auth/google/link")
@login_required
def google_auth_link_start():
    if not google_oauth_configured():
        return jsonify({"error": "Google OAuth が設定されていません"}), 503
    users = load_users()
    record = users.get(session["user"]["username"], {})
    if not user_google_login_enabled(record):
        return jsonify({"error": "先に Google ログインを許可してください"}), 400
    url, _err = _start_google_oauth(
        OAUTH_MODE_LINK, username=session["user"]["username"]
    )
    return redirect(url)


@app.route("/api/auth/callback")
def google_auth_callback():
    settings_url = url_for("settings_page") + "#integrations/google"
    login_url = url_for("login")
    error = request.args.get("error")
    mode = session.pop("google_oauth_mode", OAUTH_MODE_TOOLS)
    if error:
        if mode == OAUTH_MODE_LOGIN:
            return _oauth_redirect_with_param(login_url, "google_login_error", error)
        return _oauth_redirect_with_param(settings_url, "google_error", error)
    state = request.args.get("state") or ""
    code = request.args.get("code") or ""
    expected = session.pop("google_oauth_state", None)
    username = (session.pop("google_oauth_username", None) or "").strip().lower()
    if not expected or state != expected:
        if mode == OAUTH_MODE_LOGIN:
            return _oauth_redirect_with_param(
                login_url, "google_login_error", "invalid_state"
            )
        return _oauth_redirect_with_param(settings_url, "google_error", "invalid_state")
    if not code:
        if mode == OAUTH_MODE_LOGIN:
            return _oauth_redirect_with_param(
                login_url, "google_login_error", "missing_code"
            )
        return _oauth_redirect_with_param(settings_url, "google_error", "missing_code")
    try:
        if mode == OAUTH_MODE_LOGIN:
            target = _complete_google_login_callback(code)
            return redirect(target)
        if mode == OAUTH_MODE_LINK:
            if not username:
                return redirect(f"{settings_url}?google_error=session_expired")
            target = _complete_google_link_callback(username, code)
            return redirect(target)
        if not username:
            user = session.get("user") or {}
            username = (user.get("username") or "").strip().lower()
        if not username:
            return redirect(f"{settings_url}?google_error=session_expired")
        target = _complete_google_tools_callback(username, code)
        return redirect(target)
    except Exception as exc:
        logger.exception("Google OAuth callback failed mode=%s", mode)
        message = _google_login_error_code(exc)
        if mode == OAUTH_MODE_LOGIN:
            return _oauth_redirect_with_param(
                login_url, "google_login_error", message
            )
        return _oauth_redirect_with_param(settings_url, "google_error", message)


def _start_discord_oauth(mode, *, username=None):
    if not discord_oauth_configured():
        return None, "not_configured"
    state = secrets.token_urlsafe(32)
    session["discord_oauth_state"] = state
    session["discord_oauth_mode"] = mode
    if username:
        session["discord_oauth_username"] = username
    elif "discord_oauth_username" in session:
        session.pop("discord_oauth_username", None)
    return build_discord_authorization_url(state), None


def _discord_oauth_profile_from_code(code):
    payload = exchange_discord_code_for_tokens(code)
    access = (payload.get("access_token") or "").strip()
    if not access:
        raise RuntimeError("Discord did not return an access token")
    info = fetch_discord_userinfo(access)
    discord_id = (info.get("id") or "").strip()
    email = normalize_email(info.get("email"))
    username = (info.get("username") or "").strip()
    global_name = (info.get("global_name") or "").strip()
    display = global_name or username
    if not discord_id:
        raise RuntimeError("Discord profile is incomplete")
    return discord_id, email, username, display


def _complete_discord_link_callback(username, code):
    discord_id, _email, discord_username, _display = _discord_oauth_profile_from_code(code)
    users = load_users()
    record = users.setdefault(username, {})
    if not user_discord_login_enabled(record):
        raise RuntimeError("先に Discord ログインを許可するトグルをオンにしてください")
    other_user, _ = find_user_by_discord_id(users, discord_id)
    if other_user and other_user != username:
        raise RuntimeError("この Discord アカウントは別のユーザーに紐づいています")
    record["discord_id"] = discord_id
    record["discord_username"] = discord_username
    save_users(users)
    session["user"] = build_session_user(username, record)
    return url_for("settings_page") + "#integrations/discord?discord_login_linked=1"


def _complete_discord_login_callback(code):
    if not system_discord_login_allowed():
        raise RuntimeError("Discord ログインは現在利用できません")
    discord_id, email, discord_username, display = _discord_oauth_profile_from_code(code)
    users = load_users()
    username, record = find_user_by_discord_id(users, discord_id)
    if username and record:
        if not user_discord_login_enabled(record):
            raise RuntimeError(
                "このアカウントでは Discord ログインが無効です。設定の連携から有効にしてください"
            )
        if is_user_blocked(record) and record.get("role") != "admin":
            raise RuntimeError("このアカウントは利用停止中です")
        record["discord_username"] = discord_username
        save_users(users)
        session["user"] = build_session_user(username, record)
        return url_for("chat_page")

    if email:
        existing_user, existing_record = find_user_by_discord_email(users, email)
        if existing_user and existing_record:
            if user_discord_login_linked(existing_record) and user_discord_login_enabled(
                existing_record
            ):
                if is_user_blocked(existing_record) and existing_record.get("role") != "admin":
                    raise RuntimeError("このアカウントは利用停止中です")
                existing_record["discord_id"] = discord_id
                existing_record["discord_username"] = discord_username
                save_users(users)
                session["user"] = build_session_user(existing_user, existing_record)
                return url_for("chat_page")
            raise RuntimeError(
                "このメールは既に登録されています。ログイン後、設定の連携から Discord ログインを有効にしてください"
            )

    if not email:
        raise RuntimeError("Discord からメールを取得できませんでした。スコープを確認してください")

    if feature_blocked("registration_disabled"):
        raise RuntimeError("現在、新規登録は停止されています")

    username, record = create_discord_user_record(
        display_name=display or discord_username or email.split("@")[0],
        email=email,
        discord_id=discord_id,
        discord_username=discord_username,
    )
    users[username] = record
    save_users(users)
    session["user"] = build_session_user(username, record)
    return url_for("chat_page")


@app.route("/api/auth/discord/login")
def discord_auth_login_start():
    if not system_discord_login_allowed():
        return redirect(url_for("login") + "?discord_login_error=disabled")
    url, err = _start_discord_oauth(DISCORD_OAUTH_MODE_LOGIN)
    if err:
        return redirect(url_for("login") + "?discord_login_error=not_configured")
    return redirect(url)


@app.route("/api/auth/discord/link")
@login_required
def discord_auth_link_start():
    if not discord_oauth_configured():
        return jsonify({"error": "Discord OAuth が設定されていません"}), 503
    users = load_users()
    record = users.get(session["user"]["username"], {})
    if not user_discord_login_enabled(record):
        return jsonify({"error": "先に Discord ログインを許可してください"}), 400
    url, _err = _start_discord_oauth(
        DISCORD_OAUTH_MODE_LINK, username=session["user"]["username"]
    )
    return redirect(url)


@app.route("/api/auth/discord/callback")
def discord_auth_callback():
    settings_url = url_for("settings_page") + "#integrations/discord"
    login_url = url_for("login")
    error = request.args.get("error")
    mode = session.pop("discord_oauth_mode", DISCORD_OAUTH_MODE_LOGIN)
    if error:
        if mode == DISCORD_OAUTH_MODE_LOGIN:
            return _oauth_redirect_with_param(
                login_url, "discord_login_error", error
            )
        return _oauth_redirect_with_param(settings_url, "discord_error", error)
    state = request.args.get("state") or ""
    code = request.args.get("code") or ""
    expected = session.pop("discord_oauth_state", None)
    username = (session.pop("discord_oauth_username", None) or "").strip().lower()
    if not expected or state != expected:
        if mode == DISCORD_OAUTH_MODE_LOGIN:
            return _oauth_redirect_with_param(
                login_url, "discord_login_error", "invalid_state"
            )
        return _oauth_redirect_with_param(
            settings_url, "discord_error", "invalid_state"
        )
    if not code:
        if mode == DISCORD_OAUTH_MODE_LOGIN:
            return _oauth_redirect_with_param(
                login_url, "discord_login_error", "missing_code"
            )
        return _oauth_redirect_with_param(
            settings_url, "discord_error", "missing_code"
        )
    try:
        if mode == DISCORD_OAUTH_MODE_LOGIN:
            target = _complete_discord_login_callback(code)
            return redirect(target)
        if not username:
            return redirect(f"{settings_url}?discord_error=session_expired")
        target = _complete_discord_link_callback(username, code)
        return redirect(target)
    except Exception as exc:
        logger.exception("Discord OAuth callback failed mode=%s", mode)
        message = str(exc).replace("\r", " ").replace("\n", " ").strip()[:200]
        if mode == DISCORD_OAUTH_MODE_LOGIN:
            return _oauth_redirect_with_param(
                login_url, "discord_login_error", message or "oauth_failed"
            )
        return _oauth_redirect_with_param(
            settings_url, "discord_error", message or "oauth_failed"
        )


@app.route("/api/settings/discord")
@login_required
def get_discord_settings():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username, {})
    return jsonify(serialize_discord_integration(record or {}))


@app.route("/api/settings/discord", methods=["PUT"])
@login_required
def update_discord_settings():
    data = request.get_json() or {}
    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})

    if "discord_login_enabled" not in data:
        return jsonify({"error": "discord_login_enabled が必要です"}), 400

    record["discord_login_enabled"] = bool(data.get("discord_login_enabled"))
    if not record["discord_login_enabled"]:
        record["discord_id"] = ""
        record["discord_username"] = ""

    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify(
        {
            "user": session["user"],
            "discord": serialize_discord_integration(record),
        }
    )


@app.route("/api/settings/computelab")
@login_required
def get_computelab_settings():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username, {})
    return jsonify(serialize_computelab_integration(username, record or {}))


@app.route("/api/settings/computelab", methods=["PUT"])
@login_required
def update_computelab_settings():
    data = request.get_json() or {}
    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    profile = None
    plan = normalize_plan(record.get("plan"))
    wants_connect = "api_key" in data or bool(data.get("computelab_tools_enabled"))
    if wants_connect and not plan_computelab_enabled(plan):
        return jsonify({"error": "現在のプランでは ComputeLab 連携は利用できません"}), 403

    if "api_key" in data:
        api_key = str(data.get("api_key") or "").strip()
        if not api_key:
            return jsonify({"error": "API キーを入力してください"}), 400
        profile, err = verify_computelab_api_key(api_key)
        if err:
            return jsonify({"error": err}), 400
        set_computelab_api_key(username, api_key)
        record.setdefault("computelab_tools_enabled", True)

    if "computelab_tools_enabled" in data:
        enabled = bool(data.get("computelab_tools_enabled"))
        if enabled and not user_computelab_connected(username):
            return jsonify({"error": "先に ComputeLab API キーを登録してください"}), 400
        record["computelab_tools_enabled"] = enabled

    if "api_key" not in data and "computelab_tools_enabled" not in data:
        return jsonify(
            {"error": "api_key または computelab_tools_enabled が必要です"}
        ), 400

    save_users(users)
    session["user"] = build_session_user(username, record)
    payload = serialize_computelab_integration(username, record)
    if "api_key" in data and isinstance(profile, dict):
        payload["account_id"] = profile.get("id", "")
    return jsonify({"user": session["user"], "computelab": payload})


@app.route("/api/settings/computelab/test")
@login_required
def test_computelab_settings():
    username = session["user"]["username"]
    if not user_computelab_connected(username):
        return jsonify({"error": "先に ComputeLab API キーを登録してください"}), 400
    result, err = test_computelab_connection(username)
    if err:
        return jsonify({"ok": False, "error": err}), 502
    profile = (result or {}).get("profile") or {}
    return jsonify(
        {
            "ok": True,
            "account_id": profile.get("id", ""),
            "catalog_ok": bool((result or {}).get("catalog_ok")),
        }
    )


@app.route("/api/settings/computelab/disconnect", methods=["POST"])
@login_required
def computelab_disconnect():
    username = session["user"]["username"]
    delete_computelab_api_key(username)
    users = load_users()
    record = users.setdefault(username, {})
    record["computelab_tools_enabled"] = False
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify(
        {
            "user": session["user"],
            "computelab": serialize_computelab_integration(username, record),
        }
    )


@app.route("/api/settings/google")
@login_required
def get_google_settings():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username, {})
    return jsonify(serialize_google_integration(username, record or {}))


@app.route("/api/settings/google", methods=["PUT"])
@login_required
def update_google_settings():
    data = request.get_json() or {}
    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    connected = user_google_connected(username)

    if "google_calendar_enabled" in data:
        enabled = bool(data.get("google_calendar_enabled"))
        if enabled:
            if not connected:
                return jsonify({"error": "先に Google アカウントを接続してください"}), 400
            if not user_google_plan_calendar_allowed(record):
                return jsonify({"error": "現在のプランでは Google カレンダーを利用できません"}), 403
        record["google_calendar_enabled"] = enabled

    if "google_gmail_enabled" in data:
        enabled = bool(data.get("google_gmail_enabled"))
        if enabled:
            if not connected:
                return jsonify({"error": "先に Google アカウントを接続してください"}), 400
            if not user_google_plan_gmail_allowed(record):
                return jsonify({"error": "現在のプランでは Gmail を利用できません"}), 403
        record["google_gmail_enabled"] = enabled

    if "google_login_enabled" in data:
        record["google_login_enabled"] = bool(data.get("google_login_enabled"))
        if not record["google_login_enabled"]:
            record["google_sub"] = ""
            record["google_email"] = ""

    if (
        "google_calendar_enabled" not in data
        and "google_gmail_enabled" not in data
        and "google_login_enabled" not in data
    ):
        return jsonify(
            {
                "error": "google_calendar_enabled、google_gmail_enabled、google_login_enabled のいずれかが必要です"
            }
        ), 400

    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify(
        {
            "user": session["user"],
            "google": serialize_google_integration(username, record),
        }
    )


@app.route("/api/settings/google/disconnect", methods=["POST"])
@login_required
def google_disconnect():
    username = session["user"]["username"]
    disconnect_user(username)
    users = load_users()
    record = users.setdefault(username, {})
    record["google_calendar_enabled"] = False
    record["google_gmail_enabled"] = False
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify(
        {
            "user": session["user"],
            "google": serialize_google_integration(username, record),
        }
    )


@app.route("/api/settings/display", methods=["PUT"])
@login_required
def update_display_settings():
    data = request.get_json() or {}
    if (
        "reasoning_cards_enabled" not in data
        and "tool_trace_enabled" not in data
        and "full_info_display_enabled" not in data
        and "expression_extension_enabled" not in data
    ):
        return jsonify(
            {
                "error": "reasoning_cards_enabled、tool_trace_enabled、full_info_display_enabled、または expression_extension_enabled が必要です"
            }
        ), 400

    username = session["user"]["username"]
    users = load_users()
    record = users.setdefault(username, {})
    plan = normalize_plan(record.get("plan"))
    if "reasoning_cards_enabled" in data and not plan_reasoning_cards_enabled(plan):
        return jsonify({"error": "現在のプランでは推論カード表示は利用できません"}), 403
    if "tool_trace_enabled" in data and not plan_tool_trace_enabled(plan):
        return jsonify({"error": "現在のプランではツールトレース表示は利用できません"}), 403
    if "full_info_display_enabled" in data and not plan_full_info_display_enabled(plan):
        return jsonify({"error": "現在のプランでは全情報の表示は利用できません"}), 403
    if "reasoning_cards_enabled" in data:
        record["reasoning_cards_enabled"] = bool(data.get("reasoning_cards_enabled"))
    if "tool_trace_enabled" in data:
        record["tool_trace_enabled"] = bool(data.get("tool_trace_enabled"))
    if "full_info_display_enabled" in data:
        record["full_info_display_enabled"] = bool(data.get("full_info_display_enabled"))
    if "expression_extension_enabled" in data:
        record["expression_extension_enabled"] = bool(
            data.get("expression_extension_enabled")
        )
    save_users(users)
    session["user"] = build_session_user(username, record)
    return jsonify({"user": session["user"]})


@app.route("/api/settings/password", methods=["PUT"])
@login_required
def update_password():
    data = request.get_json() or {}
    current = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    if len(new_password) < 4:
        return jsonify({"error": "新しいパスワードは4文字以上にしてください"}), 400

    username = session["user"]["username"]
    users = load_users()
    user = users.get(username)
    if (
        not user
        or not user.get("password_hash")
        or not check_password_hash(user["password_hash"], current)
    ):
        return jsonify({"error": "現在のパスワードが正しくありません"}), 401

    users[username]["password_hash"] = generate_password_hash(new_password)
    save_users(users)
    return jsonify({"ok": True})


CHAT_TOOL_OVERRIDE_KEYS = frozenset(
    {
        "web_search",
        "image_generation",
        "google_calendar",
        "google_gmail",
        "tasks",
        "memory",
        "computelab",
        "deep_research",
    }
)


def parse_chat_tool_overrides(data):
    raw = (data or {}).get("chat_tools")
    if not isinstance(raw, dict):
        return {}
    return {k: bool(raw[k]) for k in CHAT_TOOL_OVERRIDE_KEYS if k in raw}


def apply_chat_tool_override(overrides, key, enabled):
    if key not in overrides:
        return enabled
    return bool(enabled) and bool(overrides[key])


@app.route("/api/chat/session-title", methods=["POST"])
@login_required
def chat_session_title_api():
    if feature_blocked("chat_disabled"):
        return jsonify({"error": "現在、チャット機能は一時的に制限されています"}), 403

    data = request.get_json() or {}
    from session_title import (
        extract_plain_user_text,
        fallback_session_title,
        generate_session_title,
    )

    message = extract_plain_user_text(data.get("message") or data.get("content"))
    if not message:
        return jsonify({"error": "メッセージがありません"}), 400

    username = session["user"]["username"]
    users = load_users()
    chat_user = users.get(username, {})
    if is_user_blocked(chat_user):
        return jsonify({"error": "アカウントが利用停止中です"}), 403

    allowed, plan_err = plan_allows_chat(username)
    if not allowed:
        return jsonify({"error": plan_err}), 403

    config = load_system_config()
    requested_model = (data.get("model") or "").strip()
    try:
        resolved = resolve_chat_model(requested_model, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    provider_id = resolved["provider"]
    api_model = resolved["api_model"]
    catalog_model_id = resolved["model_id"]

    client, api_key = make_openai_client_for_provider(
        provider_id, config.get("providers")
    )
    if not api_key:
        return jsonify(
            {"error": f"{provider_id} の API キーが設定されていません（管理画面または環境変数）"}
        ), 503

    try:
        result = generate_session_title(
            client, api_model, message, provider_id=provider_id
        )
        title = (result.get("title") or "").strip() or fallback_session_title(message)
        usage = result.get("usage") or empty_usage()
        if int(usage.get("total_tokens") or 0):
            record_chat_usage(username, usage, model=catalog_model_id)
        return jsonify({"title": title})
    except Exception as exc:
        logger.warning(
            "session title failed user=%s provider=%s model=%s: %s",
            username,
            provider_id,
            api_model,
            exc,
        )
        return jsonify(
            {"title": fallback_session_title(message), "fallback": True}
        )


@app.route("/api/chat", methods=["POST"])
@login_required
def chat_api():
    return (
        jsonify(
            {
                "error": "チャットのストリームは WebSocket (/ws/chat) に移行しました。",
                "websocket_path": "/ws/chat",
                "action": "chat.send",
            }
        ),
        410,
    )


@app.route("/api/chat/resume-user-questions", methods=["POST"])
@login_required
def chat_resume_user_questions_api():
    return (
        jsonify(
            {
                "error": "ユーザー質問の再開は WebSocket (/ws/chat) を利用してください。",
                "websocket_path": "/ws/chat",
                "action": "chat.resume",
            }
        ),
        410,
    )



def _developer_profile_payload(username):
    users = load_users()
    record = users.get(username, {})
    plan_key = effective_plan_for_features(record)
    features = get_plan_features(plan_key)
    config = load_system_config()
    models = get_available_models(username)
    usage = usage_summary_for_record(record)
    return {
        "username": username,
        "plan": plan_key,
        "plan_tier_rank": plan_tier_rank(plan_key),
        "api_access_enabled": user_api_access_enabled(record),
        "features": features,
        "models": models,
        "usage": usage,
        "public_api_base_url": public_api_base_url(),
    }


def _developer_usage_payload(username, *, limit=50):
    rows, total = list_billing_events_for_user(username, limit=limit)
    api_events = [e for e in rows if e.get("api_source") == "api_token"]
    models_config = load_system_config().get("models") or {}

    def _public_api_event(event):
        payload = serialize_billing_event(event)
        catalog_id = (event.get("model_id") or "").strip()
        if catalog_id:
            entry = models_config.get(catalog_id) or {}
            payload["model_id"] = get_model_api_id(entry, catalog_id)
        return payload

    return {
        "total_events": total,
        "api_token_events": len(api_events),
        "recent_api_events": [_public_api_event(e) for e in api_events[:limit]],
    }


def _openai_chat_tool_flags(record, username, plan_key):
    search_allowed = user_web_search_enabled(record) and not feature_blocked("search_disabled")
    return {
        "search_allowed": search_allowed,
        "search_engines": resolve_engines_for_plan(plan_key, get_plan_features(plan_key))
        if search_allowed
        else {"tavily": False, "serper": False, "ddg": False},
        "emit_reasoning_cards": user_reasoning_cards_enabled(record),
        "disable_reasoning": user_reasoning_disabled(record),
        "google_calendar_on": user_google_calendar_enabled(record, username),
        "google_gmail_on": user_google_gmail_enabled(record, username),
        "tasks_on": resolve_user_tasks_enabled(record, plan_tasks_enabled),
        "memory_on": resolve_user_memory_enabled(record, plan_memory_enabled),
        "computelab_on": user_computelab_tools_enabled(record, username),
        "image_gen_on": user_image_generation_enabled(record),
        "deep_research_on": resolve_user_deep_research_enabled(
            record, plan_deep_research_enabled
        ),
    }


@app.route("/dash")
@app.route("/dash/")
@app.route("/dash/<path:dash_path>")
@login_required
def api_portal_spa(dash_path=None):
    if get_server_mode() == SERVER_MODE_API:
        return jsonify({"error": "Not found"}), 404
    user = refresh_session_user()
    username = session["user"]["username"]
    record = load_users().get(username, {})
    if not user_api_access_enabled(record):
        return redirect(f"{public_base_url()}/settings#general")
    return render_template(
        "api_portal.html",
        user=user,
        api_portal_base=api_portal_base_url(),
        public_api_base=public_api_base_url(),
        frontend_base=public_base_url(),
    )


@app.route("/portal")
@app.route("/portal/")
@app.route("/portal/<path:portal_path>")
def api_portal_legacy_redirect(portal_path=None):
    if get_server_mode() == SERVER_MODE_API:
        return jsonify({"error": "Not found"}), 404
    mapping = {
        None: "/dash",
        "": "/dash",
        "tokens": "/dash/tokens",
        "usage": "/dash/usage",
        "docs": "/dash/docs",
    }
    key = portal_path if portal_path is not None else ""
    target = mapping.get(key, f"/dash/{portal_path}")
    return redirect(target)


@app.route("/api/developer/profile")
@login_required
def api_developer_profile():
    username = session["user"]["username"]
    record = load_users().get(username, {})
    if not user_api_access_enabled(record):
        return jsonify({"error": "APIアクセスが有効になっていません"}), 403
    return jsonify(_developer_profile_payload(username))


@app.route("/api/developer/usage")
@login_required
def api_developer_usage():
    username = session["user"]["username"]
    record = load_users().get(username, {})
    if not user_api_access_enabled(record):
        return jsonify({"error": "APIアクセスが有効になっていません"}), 403
    limit = min(200, max(1, int(request.args.get("limit") or 50)))
    return jsonify(_developer_usage_payload(username, limit=limit))


@app.route("/api/developer/tokens", methods=["GET", "POST"])
@login_required
def api_developer_tokens():
    username = session["user"]["username"]
    users = load_users()
    record = users.get(username, {})
    if not user_api_access_enabled(record):
        return jsonify({"error": "APIトークンの利用が有効になっていません"}), 403
    if request.method == "GET":
        return jsonify({"tokens": list_user_tokens(username)})
    data = request.get_json() or {}
    created, err = create_user_token(username, data.get("name") or "")
    if err:
        return jsonify({"error": err}), 400
    return jsonify(created), 201


@app.route("/api/developer/tokens/<token_id>", methods=["DELETE"])
@login_required
def api_developer_token_revoke(token_id):
    username = session["user"]["username"]
    record = load_users().get(username, {})
    if not user_api_access_enabled(record):
        return jsonify({"error": "APIアクセスが有効になっていません"}), 403
    if not revoke_user_token(username, token_id):
        return jsonify({"error": "トークンが見つかりません"}), 404
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# NEXGATE API 用（下流）システムAPIキー — 管理者がシステムレベルで管理するキー
# ---------------------------------------------------------------------------
def _upstream_system_keys_status():
    """NEXGATE AI 用（上流）キーの設定状態（平文は返さない）。"""
    config = load_system_config()
    from model_registry import serialize_provider_admin
    from search_settings import get_resolved_api_keys, get_search_engines_config

    search_keys = get_resolved_api_keys()
    search_cfg = get_search_engines_config()
    return {
        "providers": serialize_provider_admin(config.get("providers")),
        "search": {
            "tavily_set": bool(search_keys.get("tavily")),
            "serper_set": bool(search_keys.get("serper")),
            "tavily_enabled": bool(search_cfg.get("tavily_enabled", True)),
            "serper_enabled": bool(search_cfg.get("serper_enabled", True)),
        },
        "internal_key_set": bool(
            (os.getenv("NEXGATE_INTERNAL_API_KEY") or "").strip()
        ),
    }


@app.route("/api/admin/system-keys", methods=["GET"])
@admin_required
def admin_system_keys_overview():
    """NEXGATE AI 用（上流）と NEXGATE AI API 用（下流）のキーを分けて返す。"""
    return jsonify(
        {
            "upstream": _upstream_system_keys_status(),
            "downstream": {
                "system_keys": list_system_api_keys(include_revoked=False),
                "max_keys": MAX_SYSTEM_API_KEYS,
            },
        }
    )


@app.route("/api/admin/system-api-keys", methods=["GET", "POST"])
@admin_required
def admin_system_api_keys():
    if request.method == "GET":
        return jsonify({"keys": list_system_api_keys()})
    data = request.get_json() or {}
    created, err = create_system_api_key(
        name=data.get("name") or "",
        owner_username=data.get("owner_username") or "",
        scopes=data.get("scopes"),
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify(created), 201


@app.route("/api/admin/system-api-keys/<key_id>", methods=["DELETE"])
@admin_required
def admin_system_api_key_revoke(key_id):
    if not revoke_system_api_key(key_id):
        return jsonify({"error": "システムAPIキーが見つかりません"}), 404
    return jsonify({"ok": True})


def _v1_scope_allowed(auth, required_scope):
    """システムAPIキーのスコープ制限を判定。通常トークンは常に許可。"""
    if auth is None:
        return True
    scopes = auth.scopes
    if not scopes:
        return True
    return (required_scope or "") in scopes


# /v1/ の同時実行数上限。超過時は「待たせず」即時 503 を返し、
# 並列リクエスト全体の遅延・不安定化を防ぐ（バックプレッシャー制御）。
_MAX_CONCURRENT_V1 = int(os.getenv("NEXGATE_MAX_CONCURRENT_V1", "30"))
_v1_concurrency_sem = threading.Semaphore(_MAX_CONCURRENT_V1)


def _resolve_v1_api_user(required_scope=None):
    auth = resolve_api_auth(
        allow_internal=False,
        allow_session=False,
        allow_bearer=True,
    )
    if auth.kind not in ("token", "system") or not auth.username:
        body, status = openai_error(
            "Invalid API key provided",
            error_type="invalid_request_error",
            code="invalid_api_key",
            status=401,
        )
        return None, (jsonify(body), status)

    if not _v1_scope_allowed(auth, required_scope):
        body, status = openai_error(
            "API key does not have the required scope",
            error_type="permission_error",
            code="insufficient_scope",
            status=403,
        )
        return None, (jsonify(body), status)

    username = auth.username
    users = load_users()
    record = users.get(username, {})
    if is_user_blocked(record):
        body, status = openai_error(
            "Account is suspended",
            error_type="permission_error",
            code="account_suspended",
            status=403,
        )
        return None, (jsonify(body), status)
    if not user_api_access_enabled(record):
        body, status = openai_error(
            "API access is not enabled for this account",
            error_type="permission_error",
            code="api_access_disabled",
            status=403,
        )
        return None, (jsonify(body), status)
    return (username, record, auth), None


@app.route("/v1/models", methods=["GET", "OPTIONS"])
def v1_models():
    if request.method == "OPTIONS":
        return Response("", status=204)

    resolved, err_response = _resolve_v1_api_user(required_scope="models")
    if err_response:
        return err_response
    username, _record, auth = resolved

    # レートリミット
    allowed_rl, retry_after, rl_detail = check_rate_limit(
        username=username,
        token_id=auth.token_id or "",
        ip=request.remote_addr or "",
    )
    if not allowed_rl:
        body, status = openai_error(
            "Rate limit exceeded. Please retry later.",
            error_type="rate_limit_error",
            code="rate_limit_exceeded",
            status=429,
        )
        resp = jsonify(body)
        resp.status_code = status
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    allowed, plan_err = plan_allows_chat(username)
    if not allowed:
        body, status = openai_error(
            plan_err or "Plan does not allow chat",
            error_type="insufficient_quota",
            code="insufficient_quota",
            status=403,
        )
        return jsonify(body), status

    config = load_system_config()
    models = models_for_openai_api(config.get("models") or {})
    return jsonify(build_models_list(models))


@app.route("/v1/chat/completions", methods=["POST", "OPTIONS"])
def v1_chat_completions():
    if request.method == "OPTIONS":
        return Response("", status=204)

    # 前処理の所要時間を計測（X-Nexgate-Timing ヘッダーで返す）
    _timings = {}
    _t0 = time.perf_counter()

    def _mark(key):
        _timings[key] = round((time.perf_counter() - _t0) * 1000, 1)

    resolved, err_response = _resolve_v1_api_user(required_scope="chat_completions")
    if err_response:
        return err_response
    username, record, auth = resolved
    _mark("auth")

    # レートリミット
    allowed_rl, retry_after, rl_detail = check_rate_limit(
        username=username,
        token_id=auth.token_id or "",
        ip=request.remote_addr or "",
    )
    if not allowed_rl:
        body, status = openai_error(
            "Rate limit exceeded. Please retry later.",
            error_type="rate_limit_error",
            code="rate_limit_exceeded",
            status=429,
        )
        resp = jsonify(body)
        resp.status_code = status
        resp.headers["Retry-After"] = str(retry_after)
        return resp
    _mark("ratelimit")

    if feature_blocked("chat_disabled"):
        body, status = openai_error(
            "Chat is temporarily disabled",
            error_type="permission_error",
            code="chat_disabled",
            status=403,
        )
        return jsonify(body), status

    allowed, plan_err = plan_allows_chat(username)
    if not allowed:
        body, status = openai_error(
            plan_err or "Plan does not allow chat",
            error_type="insufficient_quota",
            code="insufficient_quota",
            status=403,
        )
        return jsonify(body), status
    _mark("plan")

    data = request.get_json(silent=True)
    parsed, err = parse_chat_completions_request(data)
    if err:
        body, status = err
        return jsonify(body), status
    _mark("parse")

    plan_key = effective_plan_for_features(record)
    config = load_system_config()
    requested_model = parsed["model"]
    try:
        resolved = resolve_chat_model(requested_model, config, public_api=True)
    except ValueError as exc:
        body, status = openai_error(str(exc), status=400)
        return jsonify(body), status

    catalog_model_id = resolved["model_id"]
    api_model = resolved["api_model"]
    provider_id = resolved["provider"]
    public_model = get_model_api_id(resolved["entry"], catalog_model_id)
    _mark("model")

    billing_event = create_billing_event(
        username,
        session_id="",
        model_id=catalog_model_id,
        payment_type="metered",
        status="running",
    )
    billing_event_id = billing_event["id"]
    update_billing_event(
        billing_event_id,
        api_source="api_token",
        api_token_id=auth.token_id or "",
    )
    _mark("billing")

    client, api_key = make_openai_client_for_provider(
        provider_id, config.get("providers")
    )
    if not api_key:
        body, status = openai_error(
            "Model provider is not configured",
            error_type="server_error",
            code="provider_unavailable",
            status=503,
        )
        return jsonify(body), status
    _mark("client")

    parsed["response_model"] = public_model

    # 同時実行制限：上限到達時は「待たせず」即時 503（遅延させない）
    if not _v1_concurrency_sem.acquire(blocking=False):
        update_billing_event(billing_event_id, status="failed")
        body, status = openai_error(
            "Server is at capacity. Please retry shortly.",
            error_type="server_error",
            code="overloaded",
            status=503,
        )
        return jsonify(body), status

    if not parsed["stream"]:
        try:
            try:
                payload = run_v1_chat_sync(
                    client=client,
                    api_model=api_model,
                    parsed=parsed,
                    provider_id=provider_id,
                )
            except Exception as exc:
                update_billing_event(billing_event_id, status="failed")
                body, status = openai_error(
                    format_v1_provider_error(exc, provider_id=provider_id),
                    error_type="server_error",
                    code="provider_error",
                    status=502,
                )
                return jsonify(body), status

            turn_usage = payload.get("usage") or empty_usage()
            if not int(turn_usage.get("total_tokens") or 0):
                assistant_text = ""
                choice = (payload.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                assistant_text = message.get("content") or ""
                merge_usage(
                    turn_usage,
                    estimate_turn_tokens(
                        parsed["messages"], assistant_text, "", api_model
                    ),
                )
                payload["usage"] = {
                    "prompt_tokens": int(turn_usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(turn_usage.get("completion_tokens") or 0),
                    "total_tokens": int(turn_usage.get("total_tokens") or 0),
                    "prompt_cache_hit_tokens": int(
                        turn_usage.get("input_cache_hit_tokens") or 0
                    ),
                    "prompt_cache_miss_tokens": int(
                        turn_usage.get("input_cache_miss_tokens") or 0
                    ),
                }
            record_chat_usage(
                username,
                turn_usage,
                model=catalog_model_id,
                billing_event_id=billing_event_id,
            )
            update_billing_event(
                billing_event_id,
                status="completed",
                token_usage=turn_usage,
                model_id=catalog_model_id,
            )
            resp = jsonify(payload)
            resp.headers["X-Nexgate-Timing"] = json.dumps(_timings, ensure_ascii=False)
            return resp
        finally:
            _v1_concurrency_sem.release()

    def generate_openai_stream():
        # プロバイダー応答を待たずに、まず SSE コメント行を送って
        # HTTP ヘッダーを即座に確定させる（TTFB の体感を短縮）。
        yield ": connected\n\n"
        turn_usage = empty_usage()
        event_status = "completed"
        output_text = ""
        try:
            for chunk in iter_v1_chat_stream(
                client=client,
                api_model=api_model,
                parsed=parsed,
                provider_id=provider_id,
            ):
                if chunk.startswith("data:") and "[DONE]" not in chunk:
                    try:
                        raw = chunk.strip().removeprefix("data:").strip()
                        payload = json.loads(raw)
                        delta = ((payload.get("choices") or [{}])[0].get("delta") or {})
                        piece = delta.get("content")
                        if piece:
                            output_text += piece
                        usage_payload = payload.get("usage")
                        if usage_payload:
                            merge_usage(turn_usage, usage_payload)
                    except json.JSONDecodeError:
                        pass
                yield chunk
        except Exception as exc:
            event_status = "failed"
            update_billing_event(billing_event_id, status="failed")
            from openai_compat import completion_id as new_completion_id, sse_chat_chunk, sse_chat_done

            cid = new_completion_id()
            yield sse_chat_chunk(
                public_model,
                content_delta=format_v1_provider_error(exc, provider_id=provider_id),
                completion_id_value=cid,
            )
            yield sse_chat_chunk(
                public_model,
                finish_reason="stop",
                completion_id_value=cid,
            )
            yield sse_chat_done()
        finally:
            _v1_concurrency_sem.release()
            if event_status != "failed":
                if not int(turn_usage.get("total_tokens") or 0):
                    merge_usage(
                        turn_usage,
                        estimate_turn_tokens(
                            parsed["messages"], output_text, "", api_model
                        ),
                    )
                record_chat_usage(
                    username,
                    turn_usage,
                    model=catalog_model_id,
                    billing_event_id=billing_event_id,
                )
                update_billing_event(
                    billing_event_id,
                    status=event_status,
                    token_usage=turn_usage,
                    model_id=catalog_model_id,
                )

    return Response(
        stream_with_context(generate_openai_stream()),
        mimetype="text/event-stream",
        headers={
            **SSE_STREAM_HEADERS,
            "X-Nexgate-Timing": json.dumps(_timings, ensure_ascii=False),
        },
    )


def init_coupons_store():
    from coupons import COUPONS_FILE, save_coupons_store

    if not COUPONS_FILE.exists():
        save_coupons_store({"coupons": []})


init_system_config()
init_coupons_store()
init_users()

project_ws_handlers = build_project_ws_handlers(
    PERMISSIONS=PERMISSIONS,
    find_accessible_project=find_accessible_project,
    has_permission=has_permission,
    _resolve_owned_project=_resolve_owned_project,
    load_users=load_users,
    load_user_projects=load_user_projects,
    load_user_projects_bundle=load_user_projects_bundle,
    save_user_projects=save_user_projects,
    save_owner_project=save_owner_project,
    attach_project_access=attach_project_access,
    normalize_members=normalize_members,
    normalize_invites=normalize_invites,
    normalize_role=normalize_role,
    normalize_username=normalize_username,
    validate_new_username=validate_new_username,
    serialize_member_public=serialize_member_public,
    serialize_invite_public=serialize_invite_public,
    get_member_role=get_member_role,
    sync_member_indexes=sync_member_indexes,
    add_incoming_invite=add_incoming_invite,
    remove_incoming_invite=remove_incoming_invite,
    load_incoming_invites=load_incoming_invites,
    publish_members_updated=publish_members_updated,
    publish_user_sync=publish_user_sync,
    emit_project_saved=_emit_project_saved,
    emit_project_deleted=_emit_project_deleted,
    user_projects_enabled=user_projects_enabled,
    feature_blocked=feature_blocked,
    is_user_blocked=is_user_blocked,
    plan_allows_chat=plan_allows_chat,
    user_reasoning_cards_enabled=user_reasoning_cards_enabled,
    user_reasoning_disabled=user_reasoning_disabled,
    load_system_config=load_system_config,
    resolve_chat_model=resolve_chat_model,
    effective_reasoning_in_english=effective_reasoning_in_english,
    make_openai_client_for_provider=make_openai_client_for_provider,
    filter_chat_messages=filter_chat_messages,
    prepare_project_chat_messages=prepare_project_chat_messages,
    stream_project_chat=stream_project_chat,
    normalize_project_mode=normalize_project_mode,
    sse_event=sse_event,
    empty_usage=empty_usage,
    merge_usage=merge_usage,
    estimate_turn_tokens=estimate_turn_tokens,
    record_chat_usage=record_chat_usage,
    format_chat_provider_error=format_chat_provider_error,
)

from user_question_pending import consume_user_question_pending

chat_ws_handlers = build_chat_ws_handlers(
    load_users=load_users,
    feature_blocked=feature_blocked,
    is_user_blocked=is_user_blocked,
    plan_allows_chat=plan_allows_chat,
    effective_plan_for_features=effective_plan_for_features,
    create_billing_event=create_billing_event,
    update_billing_event=update_billing_event,
    try_reserve_chat_usage=try_reserve_chat_usage,
    release_chat_usage_reserve=release_chat_usage_reserve,
    usage_summary_for_record=usage_summary_for_record,
    user_web_search_enabled=user_web_search_enabled,
    resolve_engines_for_plan=resolve_engines_for_plan,
    get_plan_features=get_plan_features,
    user_geolocation_enabled=user_geolocation_enabled,
    sanitize_location_context=sanitize_location_context,
    user_reasoning_cards_enabled=user_reasoning_cards_enabled,
    user_tool_trace_enabled=user_tool_trace_enabled,
    user_full_info_display_enabled=user_full_info_display_enabled,
    user_expression_extension_enabled=user_expression_extension_enabled,
    user_reasoning_disabled=user_reasoning_disabled,
    user_cost_performance_maximized=user_cost_performance_maximized,
    user_google_calendar_enabled=user_google_calendar_enabled,
    user_google_gmail_enabled=user_google_gmail_enabled,
    resolve_user_tasks_enabled=resolve_user_tasks_enabled,
    plan_tasks_enabled=plan_tasks_enabled,
    resolve_user_memory_enabled=resolve_user_memory_enabled,
    plan_memory_enabled=plan_memory_enabled,
    user_computelab_tools_enabled=user_computelab_tools_enabled,
    user_image_generation_enabled=user_image_generation_enabled,
    resolve_user_deep_research_enabled=resolve_user_deep_research_enabled,
    plan_deep_research_enabled=plan_deep_research_enabled,
    get_user_deep_research_prefs=get_user_deep_research_prefs,
    user_intelligent_search_override_enabled=user_intelligent_search_override_enabled,
    get_user_image_generation_prefs=get_user_image_generation_prefs,
    find_custom_agent=find_custom_agent,
    apply_custom_agent_chat_reasoning_prefs=apply_custom_agent_chat_reasoning_prefs,
    load_system_config=load_system_config,
    user_file_upload_enabled=user_file_upload_enabled,
    message_has_pdfs=message_has_pdfs,
    preprocess_messages_with_pdf=preprocess_messages_with_pdf,
    user_ocr_enabled=user_ocr_enabled,
    ocr_globally_enabled=ocr_globally_enabled,
    message_has_images=message_has_images,
    resolve_ocr_model_for_plan=resolve_ocr_model_for_plan,
    get_anthropic_api_key=get_anthropic_api_key,
    preprocess_messages_with_ocr=preprocess_messages_with_ocr,
    resolve_chat_model=resolve_chat_model,
    make_openai_client_for_provider=make_openai_client_for_provider,
    normalize_model_entry=normalize_model_entry,
    effective_reasoning_in_english=effective_reasoning_in_english,
    user_user_questions_enabled=user_user_questions_enabled,
    summarize_messages_for_audit=summarize_messages_for_audit,
    last_user_message_text=last_user_message_text,
    begin_monitored_chat=begin_monitored_chat,
    begin_request_detail=begin_request_detail,
    admin_monitor_token_snapshot=admin_monitor_token_snapshot,
    compute_turn_price_usd=compute_turn_price_usd,
    update_monitored_chat=update_monitored_chat,
    record_request_detail_sse=record_request_detail_sse,
    filter_chat_messages=filter_chat_messages,
    stream_agent_chat=stream_agent_chat,
    stream_chat_completion=stream_chat_completion,
    stream_resume_after_ask_user=stream_resume_after_ask_user,
    stream_with_abort=stream_with_abort,
    is_chat_aborted=is_chat_aborted,
    format_chat_provider_error=format_chat_provider_error,
    resolve_turn_token_usage=resolve_turn_token_usage,
    record_chat_usage=record_chat_usage,
    finish_request_detail=finish_request_detail,
    end_monitored_chat=end_monitored_chat,
    merge_usage=merge_usage,
    empty_usage=empty_usage,
    public_base_url=public_base_url,
    request_chat_abort=request_chat_abort,
    consume_user_question_pending=consume_user_question_pending,
    sse_event=sse_event,
    get_collab_record=get_collab_record,
    get_chat_session_meta=get_chat_session_meta,
    get_chat_session_messages=get_chat_session_messages,
    upsert_chat_session=upsert_chat_session,
    collab_public_payload=lambda rec: collab_public_payload(rec, url_builder=_collab_live_url),
)

_server_mode = get_server_mode()
if _server_mode in (SERVER_MODE_COMBINED, SERVER_MODE_API):
    init_project_realtime(app, project_ws_handlers)
    init_chat_realtime(app, chat_ws_handlers)
    init_admin_session_monitor(app)
elif _server_mode == SERVER_MODE_FRONTEND:
    register_ws_proxy(app, projects=True, admin_sessions=True, chat=True)
apply_server_mode(app)

try:
    from startup_checks import run_startup_checks

    run_startup_checks(load_system_config())
except Exception:
    logging.getLogger(__name__).exception("startup checks failed")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":
    debug = _env_bool("FLASK_DEBUG", True)
    use_reloader = _env_bool("FLASK_USE_RELOADER", False)
    app.run(
        debug=debug,
        use_reloader=use_reloader,
        threaded=True,
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
    )
