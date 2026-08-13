"""Black Forest Labs (FLUX 2.0) image generation API client."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from image_generation_registry import flux_generation_url

POLL_INTERVAL_SEC = 1.5
POLL_MAX_ATTEMPTS = 80


def _json_request(url, *, api_key, method="GET", body=None, timeout=60):
    data = None
    headers = {
        "accept": "application/json",
        "x-key": api_key,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"BFL API HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        raise RuntimeError(f"BFL API 接続エラー: {e}") from e


def _extract_image_url(payload):
    if not isinstance(payload, dict):
        return ""
    result = payload.get("result")
    if isinstance(result, dict):
        for key in ("sample", "url", "image_url", "image"):
            val = result.get(key)
            if isinstance(val, str) and val.strip().startswith("http"):
                return val.strip()
    for key in ("sample", "url", "image_url"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip().startswith("http"):
            return val.strip()
    return ""


def generate_flux_image(
    *,
    api_key,
    base_url,
    api_model,
    prompt,
    width=1024,
    height=1024,
):
    if not (api_key or "").strip():
        raise RuntimeError("BFL API キーが設定されていません")
    prompt_text = (prompt or "").strip()
    if not prompt_text:
        raise RuntimeError("プロンプトが空です")

    w = max(256, min(2048, int(width or 1024)))
    h = max(256, min(2048, int(height or 1024)))
    submit_url = flux_generation_url(base_url, api_model)
    submit = _json_request(
        submit_url,
        api_key=api_key,
        method="POST",
        body={"prompt": prompt_text, "width": w, "height": h},
        timeout=90,
    )
    polling_url = (submit.get("polling_url") or "").strip()
    if not polling_url:
        raise RuntimeError("BFL API から polling_url が返されませんでした")

    last_status = ""
    for _ in range(POLL_MAX_ATTEMPTS):
        poll = _json_request(polling_url, api_key=api_key, timeout=60)
        status = (poll.get("status") or "").strip()
        last_status = status or last_status
        if status in ("Ready", "ready", "COMPLETE", "Complete"):
            url = _extract_image_url(poll)
            if url:
                return {
                    "url": url,
                    "prompt": prompt_text,
                    "width": w,
                    "height": h,
                    "api_model": api_model,
                    "status": status,
                }
            raise RuntimeError("画像URLの取得に失敗しました")
        if status in ("Error", "Failed", "Request Moderated", "Content Moderated"):
            detail = poll.get("detail") or poll.get("error") or status
            raise RuntimeError(f"画像生成に失敗しました: {detail}")
        time.sleep(POLL_INTERVAL_SEC)

    raise RuntimeError(
        f"画像生成がタイムアウトしました（最終ステータス: {last_status or '不明'}）"
    )
