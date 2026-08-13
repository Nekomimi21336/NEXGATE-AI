import json

from google_services import format_tool_result
from tasks_storage import create_task_card, list_task_cards_summary

CREATE_TASK_CARD_TOOL = {
    "type": "function",
    "function": {
        "name": "create_task_card",
        "description": (
            "【TASKSホワイトボード】ユーザーのTASKSボードにカードを1枚追加する。"
            "使う: ユーザーがタスク・TODO・メモ・リストの作成を依頼したとき。"
            "使わない: 一般知識、カレンダー/Gmail、既存カードの一覧だけが必要なときは list_task_cards。"
            " (Create a card on the user's TASKS whiteboard.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["todo", "task", "list", "memo"],
                    "description": "Card type",
                },
                "title": {
                    "type": "string",
                    "description": "Card title (optional for memo)",
                },
                "body": {
                    "type": "string",
                    "description": "Notes or memo body (task/memo)",
                },
                "items": {
                    "type": "array",
                    "description": "Checklist lines for todo/list",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "done": {"type": "boolean"},
                        },
                    },
                },
                "x": {"type": "number", "description": "Optional X position (px)"},
                "y": {"type": "number", "description": "Optional Y position (px)"},
            },
            "required": ["type"],
        },
    },
}

LIST_TASK_CARDS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_task_cards",
        "description": (
            "【TASKSホワイトボード】既存カードの一覧（要約）を取得する。"
            "使う: ボードの現状確認、重複回避、更新前の把握。"
            "使わない: 新規作成(create_task_card)、TASKS無関係の質問。"
            " (List existing TASKS whiteboard cards.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Max cards to return (default 40)",
                },
            },
        },
    },
}

TASKS_TOOL_NAMES = frozenset({"create_task_card", "list_task_cards"})


def build_tasks_tool_list():
    return [CREATE_TASK_CARD_TOOL, LIST_TASK_CARDS_TOOL]


def tasks_system_prompt_append():
    return (
        "\n\n## TASKSホワイトボード\n"
        "ユーザーはTASKS画面でカード（todo / task / list / memo）を管理できます。\n"
        "- 新規カード: `create_task_card`（type 必須、title/body/items は内容に応じて）\n"
        "- 既存確認: `list_task_cards`\n"
        "TASKSと無関係な質問では呼び出さない。"
    )


def _parse_json_args(arguments_str):
    try:
        data = json.loads(arguments_str or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def execute_tasks_tool(username, tool_name, arguments_str):
    data = _parse_json_args(arguments_str)
    if data is None:
        return format_tool_result(None, "Invalid tool arguments JSON"), False

    if tool_name == "create_task_card":
        card, err = create_task_card(
            username,
            data.get("type"),
            title=data.get("title"),
            body=data.get("body"),
            items=data.get("items"),
            x=data.get("x"),
            y=data.get("y"),
        )
        if err:
            return format_tool_result(None, err), False
        return (
            format_tool_result(
                {
                    "message": "TASKSボードにカードを追加しました",
                    "card": {
                        "id": card.get("id"),
                        "type": card.get("type"),
                        "title": card.get("title"),
                    },
                }
            ),
            True,
        )

    if tool_name == "list_task_cards":
        summary = list_task_cards_summary(
            username, max_cards=data.get("max_results") or 40
        )
        return format_tool_result(summary), False

    return format_tool_result(None, f"Unknown tool: {tool_name}"), False
