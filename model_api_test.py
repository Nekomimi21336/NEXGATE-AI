"""Minimal API connectivity tests for admin model list."""

from __future__ import annotations

import httpx

from chat_agent import apply_disable_reasoning_kwargs, format_chat_provider_error
from model_registry import (
    PROVIDERS,
    get_provider_credentials,
    make_openai_client_for_provider,
    validate_model_id,
)

ANTHROPIC_VERSION = "2023-06-01"


def _resolve_model_test_target(model_id, config):
    mid = validate_model_id(model_id)
    if not mid:
        raise ValueError("モデルIDが不正です")
    entry = (config.get("models") or {}).get(mid)
    if not entry:
        raise ValueError("モデルが見つかりません")
    api_model = (entry.get("api_model") or mid).strip() or mid
    provider = (entry.get("provider") or "deepseek").strip().lower()
    if provider not in PROVIDERS:
        provider = "deepseek"
    return mid, api_model, provider


def _anthropic_messages_url(base_url):
    base = (base_url or "https://api.anthropic.com").rstrip("/")
    return f"{base}/v1/messages"


def _test_anthropic(api_key, base_url, api_model):
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": api_model,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "ping"}],
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(_anthropic_messages_url(base_url), headers=headers, json=body)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        try:
            err_json = resp.json()
            detail = err_json.get("error", {}).get("message") or detail
        except Exception:
            pass
        raise RuntimeError(detail)


def _test_openai_compatible(provider_id, providers_config, api_model):
    client, api_key = make_openai_client_for_provider(provider_id, providers_config)
    if not api_key:
        meta = PROVIDERS.get(provider_id) or {}
        label = meta.get("label") or provider_id
        raise ValueError(f"{label} の API キーが設定されていません（管理画面または環境変数）")
    kwargs = {
        "model": api_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    apply_disable_reasoning_kwargs(kwargs, disable_reasoning=True, provider_id=provider_id)
    client.chat.completions.create(**kwargs)


def test_model_api(model_id, config):
    mid, api_model, provider = _resolve_model_test_target(model_id, config)
    meta = PROVIDERS.get(provider) or {}
    label = meta.get("label") or provider
    base_result = {
        "model_id": mid,
        "provider": provider,
        "api_model": api_model,
    }
    try:
        if provider == "anthropic":
            api_key, base_url = get_provider_credentials(provider, config.get("providers"))
            if not api_key:
                return {
                    **base_result,
                    "ok": False,
                    "message": f"{label} の API キーが設定されていません（管理画面または環境変数）",
                    "missing_api_key": True,
                }
            _test_anthropic(api_key, base_url, api_model)
        else:
            _test_openai_compatible(provider, config.get("providers"), api_model)
        return {
            **base_result,
            "ok": True,
            "message": f"{label} への接続に成功しました（{api_model}）",
        }
    except ValueError as exc:
        text = str(exc).strip()
        missing = "API キーが設定されていません" in text
        return {
            **base_result,
            "ok": False,
            "message": text,
            "missing_api_key": missing,
        }
    except Exception as exc:
        return {
            **base_result,
            "ok": False,
            "message": format_chat_provider_error(exc, provider_id=provider),
        }
