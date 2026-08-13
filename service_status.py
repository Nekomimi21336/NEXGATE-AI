"""Fetch live service status from official Statuspage APIs (status.*.com)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

_STATUS_INTENT = re.compile(
    r"ステータス|稼働|サービス状態|障害|ダウン|落ち|メンテナンス|"
    r"outage|operational|incident|障害情報|復旧|正常|メンテ|"
    r"障害中|使えない|繋がら|接続でき",
    re.IGNORECASE,
)

_STATUS_SERVICES = (
    (re.compile(r"claude|anthropic", re.I), "https://status.claude.com", "Claude"),
    (re.compile(r"openai|chatgpt|gpt-?4o?", re.I), "https://status.openai.com", "OpenAI"),
    (
        re.compile(r"gemini|google\s*ai|bard", re.I),
        "https://status.cloud.google.com",
        "Google Cloud / Gemini",
    ),
    (re.compile(r"github", re.I), "https://www.githubstatus.com", "GitHub"),
    (re.compile(r"cloudflare", re.I), "https://www.cloudflarestatus.com", "Cloudflare"),
    (re.compile(r"discord", re.I), "https://discordstatus.com", "Discord"),
    (re.compile(r"slack", re.I), "https://status.slack.com", "Slack"),
    (re.compile(r"notion", re.I), "https://status.notion.so", "Notion"),
    (re.compile(r"stripe", re.I), "https://status.stripe.com", "Stripe"),
    (re.compile(r"vercel", re.I), "https://www.vercel-status.com", "Vercel"),
    (re.compile(r"supabase", re.I), "https://status.supabase.com", "Supabase"),
)

_FETCH_TIMEOUT = 14
_USER_AGENT = "Mozilla/5.0 (compatible; NexgateAI/1.0; +https://nexgate.ai)"


def wants_service_status_search(user_text):
    text = (user_text or "").strip()
    if not text or not _STATUS_INTENT.search(text):
        return False
    return bool(resolve_status_services(text))


def resolve_status_services(user_text):
    text = user_text or ""
    found = []
    seen = set()
    for pattern, base_url, label in _STATUS_SERVICES:
        if not pattern.search(text):
            continue
        key = base_url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        found.append({"base_url": base_url, "label": label})
    return found


def _fetch_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _fmt_utc(iso_str):
    if not iso_str:
        return "（時刻不明）"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return iso_str


def _format_incident(inc):
    lines = [
        f"インシデント: {inc.get('name') or '（名称なし）'}",
        f"状態: {inc.get('status') or 'unknown'}",
        f"影響: {inc.get('impact') or 'unknown'}",
        f"開始: {_fmt_utc(inc.get('started_at') or inc.get('created_at'))}",
        f"更新: {_fmt_utc(inc.get('updated_at'))}",
    ]
    updates = inc.get("incident_updates") or []
    if updates:
        lines.append("更新履歴（新しい順）:")
        for upd in updates[:6]:
            body = re.sub(r"\s+", " ", (upd.get("body") or "").strip())
            if len(body) > 400:
                body = body[:400] + "…"
            lines.append(
                f"  - [{upd.get('status')}] {_fmt_utc(upd.get('created_at'))}: {body}"
            )
    return "\n".join(lines)


def fetch_statuspage_report(base_url):
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return None

    summary_url = f"{base}/api/v2/summary.json"
    try:
        data = _fetch_json(summary_url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    page = data.get("page") or {}
    overall = data.get("status") or {}
    indicator = overall.get("indicator") or "unknown"
    description = overall.get("description") or ""

    lines = [
        f"公式ステータス（Statuspage API・取得時刻 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}）",
        f"ページ: {page.get('name') or base}",
        f"URL: {page.get('url') or base}",
        f"全体インジケータ: {indicator}",
        f"全体説明: {description}",
        "",
    ]

    components = data.get("components") or []
    degraded = [
        c
        for c in components
        if (c.get("status") or "").lower() not in ("operational", "under_maintenance")
    ]
    if degraded:
        lines.append("影響を受けているコンポーネント:")
        for c in degraded[:12]:
            lines.append(
                f"  - {c.get('name')}: {c.get('status')} — {c.get('description') or ''}".strip()
            )
        lines.append("")

    incidents = data.get("incidents") or []
    active = [
        inc
        for inc in incidents
        if (inc.get("status") or "").lower() not in ("resolved", "postmortem")
    ]
    if active:
        lines.append(f"進行中のインシデント（{len(active)}件）:")
        for inc in active[:5]:
            lines.append("")
            lines.append(_format_incident(inc))
    else:
        lines.append("進行中のインシデント: なし（API上は未解決インシデントなし）")

    scheduled = data.get("scheduled_maintenances") or []
    upcoming = [
        m
        for m in scheduled
        if (m.get("status") or "").lower() in ("scheduled", "in_progress")
    ]
    if upcoming:
        lines.append("")
        lines.append("予定メンテナンス:")
        for m in upcoming[:3]:
            lines.append(f"  - {m.get('name')} ({m.get('status')})")

    return "\n".join(lines).strip()


def build_official_status_search_result(service, user_text=""):
    base_url = service["base_url"]
    label = service["label"]
    body = fetch_statuspage_report(base_url)
    if not body:
        return None

    indicator_match = re.search(r"全体インジケータ:\s*(\S+)", body)
    indicator = indicator_match.group(1) if indicator_match else "unknown"
    has_active = "進行中のインシデント: なし" not in body

    title = f"（公式ステータス・最優先）{label}"
    if has_active or indicator not in ("none", "operational"):
        title += f" — {indicator}"

    return {
        "title": title,
        "href": base_url,
        "body": body,
        "fetched_full": True,
        "provider": "official_status_api",
        "date_label": datetime.now().strftime("%Y-%m-%d"),
        "synthetic": False,
    }


def prepend_official_status_results(results, user_text):
    if not wants_service_status_search(user_text):
        return results

    out = list(results or [])
    seen_href = {
        (r.get("href") or "").strip().lower().rstrip("/") for r in out if r.get("href")
    }
    prepended = []
    for service in resolve_status_services(user_text):
        key = service["base_url"].lower().rstrip("/")
        item = build_official_status_search_result(service, user_text)
        if not item:
            continue
        if key in seen_href:
            out = [r for r in out if (r.get("href") or "").strip().lower().rstrip("/") != key]
        prepended.append(item)
        seen_href.add(key)

    return prepended + out
