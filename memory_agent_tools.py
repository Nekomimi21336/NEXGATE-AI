import json

from google_services import format_tool_result
from memory_storage import (
    add_memory,
    delete_memory,
    format_memories_for_prompt,
    list_memories_summary,
    update_memory,
)

SAVE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "save_memory",
        "description": (
            "【メモリ】ユーザーについて覚えておくべき事実を新規保存する。"
            "使う: ユーザーが明示的に記憶してほしいと言ったとき、継続的な好み・関係・文脈。"
            "使わない: 一時的な雑談、既存メモリの更新（update_memory）、削除（delete_memory）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short label"},
                "content": {"type": "string", "description": "What to remember"},
                "category": {
                    "type": "string",
                    "enum": ["person", "conversation", "thing", "general"],
                },
            },
            "required": ["content"],
        },
    },
}

UPDATE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "update_memory",
        "description": (
            "【メモリ】既存の記憶エントリを更新する。id は list_memories で取得。"
            "使う: 内容の修正・追記が必要なとき。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Memory entry id"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": ["person", "conversation", "thing", "general"],
                },
            },
            "required": ["id"],
        },
    },
}

DELETE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "delete_memory",
        "description": (
            "【メモリ】記憶エントリを削除する。"
            "使う: ユーザーが忘れてほしい・不要と言ったとき。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Memory entry id"},
            },
            "required": ["id"],
        },
    },
}

LIST_MEMORIES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_memories",
        "description": (
            "【メモリ】保存済みの記憶一覧（要約）を取得する。"
            "使う: 既存の記憶を確認してから更新・削除する場合。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Max entries (default 40)",
                },
            },
        },
    },
}

MEMORY_TOOL_NAMES = frozenset(
    {"save_memory", "update_memory", "delete_memory", "list_memories"}
)


def build_memory_tool_list():
    return [
        SAVE_MEMORY_TOOL,
        UPDATE_MEMORY_TOOL,
        DELETE_MEMORY_TOOL,
        LIST_MEMORIES_TOOL,
    ]


def memory_system_prompt_append(username=None):
    base = (
        "\n\n## メモリ（試験）\n"
        "人・会話・物事について、過去のやり取りから自然に覚えているかのように応答してください。\n"
        "- 新規保存: `save_memory`（content 必須、category は person|conversation|thing|general）\n"
        "- 更新: `update_memory`（id 必須）\n"
        "- 削除: `delete_memory`（id 必須。`list_memories` で id を取得）\n"
        "- 一覧確認: `list_memories`\n"
        "複数の操作が必要な場合は、完了するまで必要なツールを連続して呼び出してからユーザーへ報告してください。\n"
        "操作が未完了のまま「これから実行します」等の宣言だけで終えないでください。\n"
        "ユーザーが明示した好み・文脈を一貫して踏まえてください。"
    )
    if username:
        block = format_memories_for_prompt(username)
        if block:
            base += "\n\n### 保存済みメモリ（参照用）\n" + block
    return base


def _parse_json_args(arguments_str):
    try:
        data = json.loads(arguments_str or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def execute_memory_tool(username, tool_name, arguments_str):
    data = _parse_json_args(arguments_str)
    if data is None:
        return format_tool_result(None, "Invalid tool arguments JSON"), False

    if tool_name == "save_memory":
        entry, err = add_memory(
            username,
            title=data.get("title"),
            content=data.get("content"),
            category=data.get("category"),
            source="chat",
        )
        if err:
            return format_tool_result(None, err), False
        return (
            format_tool_result(
                {
                    "message": "メモリを保存しました",
                    "memory": {
                        "id": entry.get("id"),
                        "title": entry.get("title"),
                        "category": entry.get("category"),
                    },
                }
            ),
            True,
        )

    if tool_name == "update_memory":
        entry_id = (data.get("id") or "").strip()
        if not entry_id:
            return format_tool_result(None, "id is required"), False
        entry, err = update_memory(
            username,
            entry_id,
            title=data.get("title"),
            content=data.get("content"),
            category=data.get("category"),
        )
        if err:
            return format_tool_result(None, err), False
        return (
            format_tool_result(
                {
                    "message": "メモリを更新しました",
                    "memory": {
                        "id": entry.get("id"),
                        "title": entry.get("title"),
                        "category": entry.get("category"),
                    },
                }
            ),
            True,
        )

    if tool_name == "delete_memory":
        entry_id = (data.get("id") or "").strip()
        if not entry_id:
            return format_tool_result(None, "id is required"), False
        ok, err = delete_memory(username, entry_id)
        if err:
            return format_tool_result(None, err), False
        return format_tool_result({"message": "メモリを削除しました", "deleted": ok}), True

    if tool_name == "list_memories":
        summary = list_memories_summary(
            username, max_entries=data.get("max_results") or 40
        )
        return format_tool_result(summary), False

    return format_tool_result(None, f"Unknown tool: {tool_name}"), False
