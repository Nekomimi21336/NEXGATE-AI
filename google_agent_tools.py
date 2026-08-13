import json

from google_services import (
    calendar_create_event,
    calendar_delete_event,
    calendar_list_events,
    format_tool_result,
    gmail_get_message,
    gmail_list_messages,
    gmail_send_message,
)

GOOGLE_CALENDAR_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": "google_calendar_list",
        "description": (
            "【Googleカレンダー】指定期間の予定一覧を取得する。"
            "使う: 予定・スケジュール・空きの確認。"
            "使わない: 一般知識、予定の作成(google_calendar_create)、削除、カレンダー無関係の質問。"
            " (List calendar events in a date range; not for create/delete or unrelated topics.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "time_min": {
                    "type": "string",
                    "description": "Range start (ISO date or datetime, e.g. 2026-05-23 or 2026-05-23T09:00)",
                },
                "time_max": {
                    "type": "string",
                    "description": "Range end (ISO date or datetime)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max events to return (default 25, max 50)",
                },
            },
        },
    },
}

GOOGLE_CALENDAR_CREATE_TOOL = {
    "type": "function",
    "function": {
        "name": "google_calendar_create",
        "description": (
            "【Googleカレンダー】予定を新規作成する。"
            "使う: ユーザーが予定の追加・登録を明示したとき（日時を確認してから）。"
            "使わない: 一覧(google_calendar_list)、削除、仮定の予定、カレンダー無関係。"
            " (Create a calendar event; not for list/delete or hypothetical events.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title"},
                "start": {
                    "type": "string",
                    "description": "Start date/time (required)",
                },
                "end": {
                    "type": "string",
                    "description": "End date/time (required for timed events)",
                },
                "description": {"type": "string"},
                "location": {"type": "string"},
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone, default Asia/Tokyo",
                },
            },
            "required": ["summary", "start"],
        },
    },
}

GOOGLE_CALENDAR_DELETE_TOOL = {
    "type": "function",
    "function": {
        "name": "google_calendar_delete",
        "description": (
            "【Googleカレンダー】event_id で予定を削除する。"
            "使う: ユーザーが特定予定の削除を明示し、id が分かるとき。"
            "使わない: 一覧・作成、id 不明、確認なしの削除。"
            " (Delete event by id from list; not without confirmed event_id.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Google Calendar event id",
                },
            },
            "required": ["event_id"],
        },
    },
}

GMAIL_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": "gmail_list",
        "description": (
            "【Gmail】受信メールの一覧（件名・差出人・スニペット）を取得する。"
            "使う: 受信確認、送信者/件名での検索、最近のメール把握。"
            "使わない: 本文全文(gmail_get)、送信(gmail_send)、メール無関係。"
            " (List recent Gmail; not for full body, send, or non-mail tasks.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query (optional), e.g. from:foo subject:invoice",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max messages (default 15, max 30)",
                },
            },
        },
    },
}

GMAIL_GET_TOOL = {
    "type": "function",
    "function": {
        "name": "gmail_get",
        "description": (
            "【Gmail】message_id のメール本文を取得する。"
            "使う: 特定メールの内容を読んで要約・返信案を作るとき。"
            "使わない: 一覧(gmail_list)、送信(gmail_send)、id なし。"
            " (Get full message body by id; not for list/send.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "Gmail message id",
                },
            },
            "required": ["message_id"],
        },
    },
}

GMAIL_SEND_TOOL = {
    "type": "function",
    "function": {
        "name": "gmail_send",
        "description": (
            "【Gmail】メールを送信する。"
            "使う: ユーザーが送信を明示し、宛先・内容が確定したときのみ。"
            "使わない: 未確認の送信、一覧・本文取得、メール無関係。"
            " (Send email; only with explicit user approval and recipient.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email"},
                "subject": {"type": "string"},
                "body": {"type": "string", "description": "Plain text body"},
                "cc": {"type": "string"},
            },
            "required": ["to", "body"],
        },
    },
}

GOOGLE_TOOL_NAMES = frozenset(
    {
        "google_calendar_list",
        "google_calendar_create",
        "google_calendar_delete",
        "gmail_list",
        "gmail_get",
        "gmail_send",
    }
)


def build_google_tool_list(calendar_enabled=False, gmail_enabled=False):
    tools = []
    if calendar_enabled:
        tools.extend(
            [
                GOOGLE_CALENDAR_LIST_TOOL,
                GOOGLE_CALENDAR_CREATE_TOOL,
                GOOGLE_CALENDAR_DELETE_TOOL,
            ]
        )
    if gmail_enabled:
        tools.extend([GMAIL_LIST_TOOL, GMAIL_GET_TOOL, GMAIL_SEND_TOOL])
    return tools


def google_system_prompt_append(calendar_enabled=False, gmail_enabled=False):
    parts = []
    if calendar_enabled:
        parts.append(
            "## Googleカレンダー\n"
            "- 予定の確認: `google_calendar_list`\n"
            "- 予定の追加: `google_calendar_create`（日時を確認してから）\n"
            "- 予定の削除: `google_calendar_delete`（event_id が分かるときのみ）\n"
            "カレンダーと無関係な質問では呼び出さない。"
        )
    if gmail_enabled:
        parts.append(
            "## Gmail\n"
            "- 受信一覧: `gmail_list`\n"
            "- 本文取得: `gmail_get`（message_id 必須）\n"
            "- 送信: `gmail_send`（ユーザーが送信を明示したときのみ）\n"
            "メールと無関係な質問では呼び出さない。"
        )
    if not parts:
        return ""
    return "\n\n" + "\n".join(parts)


def _parse_json_args(arguments_str):
    try:
        data = json.loads(arguments_str or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def execute_google_tool(username, tool_name, arguments_str):
    data = _parse_json_args(arguments_str)
    if data is None:
        return format_tool_result(None, "Invalid tool arguments JSON")

    if tool_name == "google_calendar_list":
        result, err = calendar_list_events(
            username,
            time_min=data.get("time_min"),
            time_max=data.get("time_max"),
            max_results=data.get("max_results") or 25,
        )
        return format_tool_result(result, err)

    if tool_name == "google_calendar_create":
        result, err = calendar_create_event(
            username,
            summary=data.get("summary"),
            start=data.get("start"),
            end=data.get("end"),
            description=data.get("description"),
            location=data.get("location"),
            timezone_name=data.get("timezone") or "Asia/Tokyo",
        )
        return format_tool_result(result, err)

    if tool_name == "google_calendar_delete":
        result, err = calendar_delete_event(username, data.get("event_id"))
        return format_tool_result(result, err)

    if tool_name == "gmail_list":
        result, err = gmail_list_messages(
            username,
            query=data.get("query"),
            max_results=data.get("max_results") or 15,
        )
        return format_tool_result(result, err)

    if tool_name == "gmail_get":
        result, err = gmail_get_message(username, data.get("message_id"))
        return format_tool_result(result, err)

    if tool_name == "gmail_send":
        result, err = gmail_send_message(
            username,
            to=data.get("to"),
            subject=data.get("subject"),
            body=data.get("body"),
            cc=data.get("cc"),
        )
        return format_tool_result(result, err)

    return format_tool_result(None, f"Unknown tool: {tool_name}")
