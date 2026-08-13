from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from server_split import (
    SERVER_MODE_API,
    SERVER_MODE_API_PORTAL,
    SERVER_MODE_COMBINED,
    SERVER_MODE_FRONTEND,
    api_internal_base_url,
    get_server_mode,
)

logger = logging.getLogger(__name__)

SERIES_FILE = Path(__file__).parent / "data" / "server_health_series.json"
SERIES_RETENTION_HOURS = 168
APP_STARTED_AT = datetime.now()
APP_STARTED_MONO = time.monotonic()

OPERATION_MODE_RUN_SERVERS = "run-servers"
OPERATION_MODE_COMBINED = "combined"
OPERATION_MODES = (OPERATION_MODE_RUN_SERVERS, OPERATION_MODE_COMBINED)

STATUS_OPERATING = "operating"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_CRITICAL = "critical"

STATUS_LEVELS = {
    STATUS_OPERATING: 0,
    STATUS_WARNING: 1,
    STATUS_ERROR: 2,
    STATUS_CRITICAL: 3,
}

STATUS_LABELS = {
    STATUS_OPERATING: "operating",
    STATUS_WARNING: "warning",
    STATUS_ERROR: "error",
    STATUS_CRITICAL: "critical",
}

SERVICE_IDS = ("frontend", "api_portal", "api")

SERVICE_META = {
    "frontend": {
        "id": "frontend",
        "label": "フロントサーバー",
        "role": "frontend",
        "url_key": "frontend_base_url",
    },
    "api_portal": {
        "id": "api_portal",
        "label": "APIフロントサーバー",
        "role": "api_portal",
        "url_key": "api_portal_base_url",
    },
    "api": {
        "id": "api",
        "label": "APIサーバー",
        "role": "api",
        "url_key": "api_base_url",
    },
}

DEFAULT_DEPLOYMENT = {
    "operation_mode": OPERATION_MODE_RUN_SERVERS,
}

RUNTIME_MODE_LABELS = {
    SERVER_MODE_COMBINED: "単一運用 (combined)",
    SERVER_MODE_FRONTEND: "フロント分離 (frontend)",
    SERVER_MODE_API_PORTAL: "APIフロント分離 (api_portal)",
    SERVER_MODE_API: "API分離 (api)",
}

OPERATION_MODE_LABELS = {
    OPERATION_MODE_RUN_SERVERS: "run-servers",
    OPERATION_MODE_COMBINED: "単一運用",
}


def normalize_deployment(raw):
    src = raw if isinstance(raw, dict) else {}
    mode = (src.get("operation_mode") or OPERATION_MODE_RUN_SERVERS).strip().lower()
    if mode not in OPERATION_MODES:
        mode = OPERATION_MODE_RUN_SERVERS
    return {"operation_mode": mode}


def uptime_seconds():
    return max(0, int(time.monotonic() - APP_STARTED_MONO))


def format_uptime(seconds):
    total = max(0, int(seconds or 0))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}日")
    if hours or days:
        parts.append(f"{hours}時間")
    if minutes or hours or days:
        parts.append(f"{minutes}分")
    if not parts:
        parts.append(f"{secs}秒")
    return "".join(parts)


def local_health_payload():
    mode = get_server_mode()
    roles = []
    if mode == SERVER_MODE_COMBINED:
        roles = list(SERVICE_IDS)
    elif mode == SERVER_MODE_FRONTEND:
        roles = ["frontend"]
    elif mode == SERVER_MODE_API_PORTAL:
        roles = ["api_portal"]
    elif mode == SERVER_MODE_API:
        roles = ["api"]
    return {
        "ok": True,
        "mode": mode,
        "roles": roles,
        "started_at": APP_STARTED_AT.isoformat(timespec="seconds"),
        "uptime_seconds": uptime_seconds(),
    }


def _load_series():
    if not SERIES_FILE.exists():
        return {sid: {} for sid in SERVICE_IDS}
    try:
        with SERIES_FILE.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {sid: {} for sid in SERVICE_IDS}
    if not isinstance(data, dict):
        return {sid: {} for sid in SERVICE_IDS}
    out = {}
    for sid in SERVICE_IDS:
        bucket = data.get(sid) or {}
        out[sid] = bucket if isinstance(bucket, dict) else {}
    return out


def _save_series(data):
    SERIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SERIES_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def _hour_key(dt=None):
    dt = dt or datetime.now()
    return dt.strftime("%Y-%m-%dT%H")


def _prune_series(bucket):
    cutoff = datetime.now() - timedelta(hours=SERIES_RETENTION_HOURS)
    kept = {}
    for key, entry in (bucket or {}).items():
        try:
            dt = datetime.strptime(key, "%Y-%m-%dT%H")
        except ValueError:
            continue
        if dt >= cutoff.replace(minute=0, second=0, microsecond=0):
            kept[key] = entry
    return kept


def record_health_samples(samples):
    data = _load_series()
    hour = _hour_key()
    for sid, sample in (samples or {}).items():
        if sid not in SERVICE_IDS or not isinstance(sample, dict):
            continue
        bucket = _prune_series(data.setdefault(sid, {}))
        bucket[hour] = {
            "status": sample.get("status") or STATUS_CRITICAL,
            "level": STATUS_LEVELS.get(sample.get("status"), 3),
            "uptime_seconds": int(sample.get("uptime_seconds") or 0),
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
        }
        data[sid] = bucket
    _save_series(data)


def _worst_status(statuses):
    order = (
        STATUS_CRITICAL,
        STATUS_ERROR,
        STATUS_WARNING,
        STATUS_OPERATING,
    )
    for status in order:
        if status in statuses:
            return status
    return STATUS_CRITICAL


def _classify_probe(
    *,
    reachable,
    status_code=0,
    role_ok=True,
    mode_ok=True,
    warnings=None,
    errors=None,
):
    warnings = warnings or []
    errors = errors or []
    if not reachable:
        return STATUS_CRITICAL, errors or ["接続できません"]
    if status_code >= 500:
        return STATUS_CRITICAL, errors or [f"HTTP {status_code}"]
    if status_code >= 400 or not role_ok or not mode_ok:
        msgs = list(errors)
        if not role_ok:
            msgs.append("サービス種別が一致しません")
        if not mode_ok:
            msgs.append("稼働タイプと実行モードが一致しません")
        return STATUS_ERROR, msgs or [f"HTTP {status_code}"]
    if warnings:
        return STATUS_WARNING, warnings
    return STATUS_OPERATING, []


def _fetch_health(url):
    target = f"{url.rstrip('/')}/api/system/health"
    try:
        with httpx.Client(timeout=3.0, follow_redirects=True) as client:
            response = client.get(target)
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if not isinstance(payload, dict):
            payload = {}
        return True, response.status_code, payload, None
    except Exception as exc:
        logger.debug("health probe failed for %s: %s", target, exc)
        return False, 0, {}, str(exc)


def _same_origin(a, b):
    pa, pb = urlparse(a or ""), urlparse(b or "")
    return pa.scheme == pb.scheme and pa.netloc == pb.netloc and bool(pa.netloc)


def _service_url(service_urls, key, fallback=""):
    value = (service_urls or {}).get(key) or fallback
    return str(value or "").strip().rstrip("/")


def _expected_runtime_modes(operation_mode):
    if operation_mode == OPERATION_MODE_COMBINED:
        return {SERVER_MODE_COMBINED}
    return {SERVER_MODE_FRONTEND, SERVER_MODE_API_PORTAL, SERVER_MODE_API}


def probe_service(
    service_id,
    *,
    service_urls,
    effective_urls,
    operation_mode,
):
    meta = SERVICE_META[service_id]
    url = _service_url(effective_urls, meta["url_key"]) or _service_url(
        service_urls, meta["url_key"]
    )
    warnings = []
    errors = []

    if not url:
        return {
            "id": service_id,
            "label": meta["label"],
            "url": "",
            "status": STATUS_CRITICAL,
            "status_label": STATUS_LABELS[STATUS_CRITICAL],
            "level": STATUS_LEVELS[STATUS_CRITICAL],
            "uptime_seconds": 0,
            "uptime_label": "—",
            "reachable": False,
            "runtime_mode": "",
            "issues": ["URL が未設定です"],
        }

    reachable, status_code, payload, conn_err = _fetch_health(url)
    runtime_mode = (payload.get("mode") or "").strip().lower()
    roles = payload.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    role_ok = meta["role"] in roles
    expected_modes = _expected_runtime_modes(operation_mode)
    mode_ok = runtime_mode in expected_modes

    if operation_mode == OPERATION_MODE_COMBINED:
        if runtime_mode == SERVER_MODE_COMBINED:
            role_ok = True
            mode_ok = True
        elif _same_origin(url, _service_url(effective_urls, "frontend_base_url")):
            warnings.append("単一運用ですが分離モードで応答しています")
            mode_ok = False

    if service_id == "frontend" and operation_mode == OPERATION_MODE_RUN_SERVERS:
        api_url = api_internal_base_url()
        if api_url:
            api_ok, api_code, api_payload, api_err = _fetch_health(api_url)
            if not api_ok:
                errors.append("バックエンド API に接続できません")
            elif api_code >= 400:
                errors.append(f"バックエンド API が HTTP {api_code} を返しました")
            elif (api_payload.get("mode") or "") != SERVER_MODE_API:
                errors.append("バックエンド API のモードが api ではありません")

    if conn_err:
        errors.append(conn_err)

    status, issues = _classify_probe(
        reachable=reachable,
        status_code=status_code,
        role_ok=role_ok,
        mode_ok=mode_ok,
        warnings=warnings,
        errors=errors,
    )
    uptime = int(payload.get("uptime_seconds") or 0) if reachable else 0

    return {
        "id": service_id,
        "label": meta["label"],
        "url": url,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "level": STATUS_LEVELS[status],
        "uptime_seconds": uptime,
        "uptime_label": format_uptime(uptime) if reachable else "—",
        "reachable": reachable,
        "runtime_mode": runtime_mode,
        "issues": issues,
    }


def build_health_chart(series_data, hours=24):
    end = datetime.now().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=hours - 1)
    labels = []
    slots = []
    cur = start
    while cur <= end:
        slots.append(cur.strftime("%Y-%m-%dT%H"))
        labels.append(cur.strftime("%H時"))
        cur += timedelta(hours=1)

    datasets = {}
    for sid in SERVICE_IDS:
        bucket = series_data.get(sid) or {}
        values = []
        for key in slots:
            entry = bucket.get(key) or {}
            values.append(int(entry.get("level", STATUS_LEVELS[STATUS_CRITICAL])))
        datasets[sid] = values

    return {
        "hours": hours,
        "labels": labels,
        "datasets": datasets,
    }


def serialize_deployment_admin(
    *,
    deployment,
    service_urls,
    effective_urls,
):
    deployment = normalize_deployment(deployment)
    operation_mode = deployment["operation_mode"]
    runtime_mode = get_server_mode()
    expected_modes = _expected_runtime_modes(operation_mode)
    mode_mismatch = runtime_mode not in expected_modes

    services = []
    samples = {}
    for sid in SERVICE_IDS:
        probe = probe_service(
            sid,
            service_urls=service_urls,
            effective_urls=effective_urls,
            operation_mode=operation_mode,
        )
        services.append(probe)
        samples[sid] = probe

    record_health_samples(samples)
    series = _load_series()
    chart = build_health_chart(series)

    overall = _worst_status([s["status"] for s in services])

    restart_hint = ""
    if mode_mismatch:
        if operation_mode == OPERATION_MODE_COMBINED:
            restart_hint = "単一運用に切り替えるには NEXGATE_APP_MODE=combined でアプリを再起動してください。"
        else:
            restart_hint = "run-servers に切り替えるには python run_servers.py で各サーバーを起動してください。"

    return {
        "deployment": {
            "operation_mode": operation_mode,
            "operation_mode_label": OPERATION_MODE_LABELS[operation_mode],
            "runtime_mode": runtime_mode,
            "runtime_mode_label": RUNTIME_MODE_LABELS.get(runtime_mode, runtime_mode),
            "mode_mismatch": mode_mismatch,
            "restart_hint": restart_hint,
        },
        "services": services,
        "overall_status": overall,
        "overall_status_label": STATUS_LABELS[overall],
        "chart": chart,
        "local_health": local_health_payload(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
