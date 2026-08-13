import base64
import email.utils
from datetime import datetime, timezone
from email.mime.text import MIMEText

from google_oauth import authorized_session

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
GMAIL_BASE = "https://www.googleapis.com/gmail/v1"


def _api_error(resp):
    try:
        data = resp.json()
        err = data.get("error") or {}
        if isinstance(err, dict):
            return err.get("message") or str(data)
        return str(err) or resp.text[:300]
    except Exception:
        return resp.text[:300] or f"HTTP {resp.status_code}"


def _parse_rfc3339(value, end_of_day=False):
    text = (value or "").strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        suffix = "T23:59:59" if end_of_day else "T00:00:00"
        text = f"{text}{suffix}"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def calendar_list_events(username, time_min=None, time_max=None, max_results=25):
    session = authorized_session(username)
    params = {
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": max(1, min(int(max_results or 25), 50)),
    }
    tmin = _parse_rfc3339(time_min)
    tmax = _parse_rfc3339(time_max, end_of_day=True)
    if tmin:
        params["timeMin"] = tmin
    if tmax:
        params["timeMax"] = tmax
    resp = session.get(
        f"{CALENDAR_BASE}/calendars/primary/events",
        params=params,
        timeout=30,
    )
    if resp.status_code >= 400:
        return None, _api_error(resp)
    items = resp.json().get("items") or []
    events = []
    for ev in items:
        start = ev.get("start") or {}
        end = ev.get("end") or {}
        events.append(
            {
                "id": ev.get("id", ""),
                "summary": ev.get("summary", "(無題)"),
                "start": start.get("dateTime") or start.get("date", ""),
                "end": end.get("dateTime") or end.get("date", ""),
                "location": ev.get("location", ""),
                "description": (ev.get("description") or "")[:500],
            }
        )
    return {"events": events, "count": len(events)}, None


def calendar_create_event(
    username,
    summary,
    start,
    end=None,
    description=None,
    location=None,
    timezone_name="Asia/Tokyo",
):
    session = authorized_session(username)
    start_iso = _parse_rfc3339(start)
    if not start_iso:
        return None, "start の日時形式が不正です (例: 2026-05-23T15:00 または 2026-05-23)"
    body = {
        "summary": (summary or "").strip() or "(無題)",
    }
    if description:
        body["description"] = str(description).strip()[:4000]
    if location:
        body["location"] = str(location).strip()[:500]
    if len(start_iso) == 10:
        body["start"] = {"date": start_iso}
        end_date = _parse_rfc3339(end, end_of_day=True) if end else start_iso
        body["end"] = {"date": (end_date or start_iso)[:10]}
    else:
        tz = (timezone_name or "Asia/Tokyo").strip() or "Asia/Tokyo"
        body["start"] = {"dateTime": start_iso.replace("Z", ""), "timeZone": tz}
        end_iso = _parse_rfc3339(end) if end else None
        if not end_iso:
            return None, "時刻付きイベントには end が必要です"
        body["end"] = {"dateTime": end_iso.replace("Z", ""), "timeZone": tz}
    resp = session.post(
        f"{CALENDAR_BASE}/calendars/primary/events",
        json=body,
        timeout=30,
    )
    if resp.status_code >= 400:
        return None, _api_error(resp)
    ev = resp.json()
    return {
        "id": ev.get("id", ""),
        "summary": ev.get("summary", ""),
        "htmlLink": ev.get("htmlLink", ""),
    }, None


def calendar_delete_event(username, event_id):
    event_id = (event_id or "").strip()
    if not event_id:
        return None, "event_id が必要です"
    session = authorized_session(username)
    resp = session.delete(
        f"{CALENDAR_BASE}/calendars/primary/events/{event_id}",
        timeout=30,
    )
    if resp.status_code == 404:
        return {"deleted": False, "message": "イベントが見つかりません"}, None
    if resp.status_code >= 400:
        return None, _api_error(resp)
    return {"deleted": True, "event_id": event_id}, None


def gmail_list_messages(username, query=None, max_results=15):
    session = authorized_session(username)
    params = {"maxResults": max(1, min(int(max_results or 15), 30))}
    q = (query or "").strip()
    if q:
        params["q"] = q[:200]
    resp = session.get(f"{GMAIL_BASE}/users/me/messages", params=params, timeout=30)
    if resp.status_code >= 400:
        return None, _api_error(resp)
    ids = [m.get("id") for m in resp.json().get("messages") or [] if m.get("id")]
    messages = []
    for mid in ids[: params["maxResults"]]:
        detail, err = gmail_get_message(username, mid, session=session)
        if err:
            continue
        messages.append(detail)
    return {"messages": messages, "count": len(messages)}, None


def _header_value(headers, name):
    name_lower = name.lower()
    for h in headers or []:
        if (h.get("name") or "").lower() == name_lower:
            return h.get("value") or ""
    return ""


def gmail_get_message(username, message_id, session=None):
    message_id = (message_id or "").strip()
    if not message_id:
        return None, "message_id が必要です"
    session = session or authorized_session(username)
    resp = session.get(
        f"{GMAIL_BASE}/users/me/messages/{message_id}",
        params={"format": "full"},
        timeout=30,
    )
    if resp.status_code >= 400:
        return None, _api_error(resp)
    data = resp.json()
    payload = data.get("payload") or {}
    headers = payload.get("headers") or []
    body_text = _extract_body(payload)
    return {
        "id": data.get("id", message_id),
        "threadId": data.get("threadId", ""),
        "subject": _header_value(headers, "Subject"),
        "from": _header_value(headers, "From"),
        "to": _header_value(headers, "To"),
        "date": _header_value(headers, "Date"),
        "snippet": data.get("snippet", ""),
        "body": body_text[:12000],
    }, None


def _extract_body(payload):
    if not payload:
        return ""
    mime = payload.get("mimeType") or ""
    body = payload.get("body") or {}
    data = body.get("data")
    if data and mime.startswith("text/"):
        return _decode_b64(data)
    parts = payload.get("parts") or []
    plain = ""
    html = ""
    for part in parts:
        part_mime = part.get("mimeType") or ""
        if part_mime == "text/plain":
            plain = _decode_b64((part.get("body") or {}).get("data")) or plain
        elif part_mime == "text/html" and not plain:
            html = _decode_b64((part.get("body") or {}).get("data")) or html
        elif part.get("parts"):
            nested = _extract_body(part)
            if nested:
                return nested
    return plain or html


def _decode_b64(data):
    if not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def gmail_send_message(username, to, subject, body, cc=None):
    to_addr = (to or "").strip()
    if not to_addr:
        return None, "to (宛先) が必要です"
    msg = MIMEText((body or "").strip() or "(本文なし)", "plain", "utf-8")
    msg["To"] = to_addr
    msg["Subject"] = (subject or "").strip() or "(件名なし)"
    if cc:
        msg["Cc"] = str(cc).strip()
    msg["Date"] = email.utils.formatdate(localtime=True)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    session = authorized_session(username)
    resp = session.post(
        f"{GMAIL_BASE}/users/me/messages/send",
        json={"raw": raw},
        timeout=30,
    )
    if resp.status_code >= 400:
        return None, _api_error(resp)
    data = resp.json()
    return {"id": data.get("id", ""), "threadId": data.get("threadId", "")}, None


def format_tool_result(data, error=None):
    import json

    if error:
        return json.dumps({"ok": False, "error": error}, ensure_ascii=False)
    return json.dumps({"ok": True, **(data or {})}, ensure_ascii=False)
