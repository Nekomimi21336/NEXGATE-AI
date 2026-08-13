import json

from google_services import format_tool_result
from expert_crawler import iter_crawl_pipeline, run_crawl_pipeline
from expert_knowledge_storage import (
    delete_knowledge_item,
    get_knowledge_item,
    list_knowledge_summaries,
    search_knowledge_items,
    upsert_knowledge_item,
)
from info_experts_storage import find_info_expert, update_info_expert

EXPERT_CRAWL_SITE_TOOL = {
    "type": "function",
    "function": {
        "name": "expert_crawl_site",
        "description": (
            "【Expert】指定URLから同一サイト内をクロールし、ページ内容を要約して知識ベースに保存する。"
            "使う: ユーザーがURLを渡したとき、ドキュメントサイトやWikiを専門家の知識として取り込むとき。"
            "使わない: 単一ページだけなら expert_upsert_knowledge で手動登録。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "クロール開始URL (http/https)"},
                "max_pages": {
                    "type": "integer",
                    "description": "最大取得ページ数 (default 20, max 50)",
                },
                "summarize": {
                    "type": "boolean",
                    "description": "LLMで要約してから保存するか (default true)",
                },
            },
            "required": ["url"],
        },
    },
}

EXPERT_LIST_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "expert_list_knowledge",
        "description": "【Expert】この専門家の知識ベース一覧（要約）を取得する。",
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "最大件数 (default 30)"},
            },
        },
    },
}

EXPERT_READ_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "expert_read_knowledge",
        "description": "【Expert】知識ベースの1項目を全文読み取る。id は expert_list_knowledge で取得。",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "知識項目ID"},
            },
            "required": ["id"],
        },
    },
}

EXPERT_UPSERT_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "expert_upsert_knowledge",
        "description": (
            "【Expert】知識ベースに項目を追加または更新する。"
            "チャットで得た専門知識を構造化して保存するときに使う。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "更新時のみ。新規は省略"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "source_url": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["title", "content"],
        },
    },
}

EXPERT_DELETE_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "expert_delete_knowledge",
        "description": "【Expert】知識ベースの項目を削除する。",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
            },
            "required": ["id"],
        },
    },
}

EXPERT_SEARCH_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "expert_search_knowledge",
        "description": "【Expert】知識ベースをキーワード検索する。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
}

EXPERT_UPDATE_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "expert_update_profile",
        "description": (
            "【Expert】専門家の名前・説明・指示を更新する。"
            "作成フローで十分な情報が揃ったときに反映する。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "instructions": {"type": "string"},
            },
        },
    },
}

EXPERT_TOOL_NAMES = frozenset(
    {
        "expert_crawl_site",
        "expert_list_knowledge",
        "expert_read_knowledge",
        "expert_upsert_knowledge",
        "expert_delete_knowledge",
        "expert_search_knowledge",
        "expert_update_profile",
    }
)

MUTATING_EXPERT_TOOLS = frozenset(
    {
        "expert_crawl_site",
        "expert_upsert_knowledge",
        "expert_delete_knowledge",
        "expert_update_profile",
    }
)


def build_expert_tool_list():
    return [
        EXPERT_CRAWL_SITE_TOOL,
        EXPERT_LIST_KNOWLEDGE_TOOL,
        EXPERT_READ_KNOWLEDGE_TOOL,
        EXPERT_UPSERT_KNOWLEDGE_TOOL,
        EXPERT_DELETE_KNOWLEDGE_TOOL,
        EXPERT_SEARCH_KNOWLEDGE_TOOL,
        EXPERT_UPDATE_PROFILE_TOOL,
    ]


def expert_system_prompt_append(*, creation_mode="chat"):
    mode = (creation_mode or "chat").strip().lower()
    crawl_note = ""
    if mode == "crawl":
        crawl_note = (
            "\n- このセッションは「URLクロール」モードです。"
            "ユーザーがURLを提示したら expert_crawl_site で取り込み、結果を説明してください。"
        )
    return (
        "\n\n## Expert 専用ツール（固定・切替不可）\n"
        "Web検索 (web_search / web_fetch) と以下の Expert ツールのみ利用できます。\n"
        "- expert_crawl_site: URLからサイトをクロールして知識化\n"
        "- expert_list_knowledge / expert_read_knowledge / expert_search_knowledge: 知識の参照\n"
        "- expert_upsert_knowledge / expert_delete_knowledge: 知識の編集\n"
        "- expert_update_profile: 専門家名・説明・指示の更新\n"
        "専門家作成では、対話を通じて知識を蓄積し、十分に整ったら expert_update_profile で反映してください。"
        f"{crawl_note}\n"
        "ツール実行が必要なときは宣言だけで終えず、実際に呼び出してから報告してください。"
    )


def _parse_json_args(arguments_str):
    try:
        data = json.loads(arguments_str or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def save_crawl_pipeline_result(username, expert_id, result):
    saved = []
    errors = []
    for item in result.get("items") or []:
        entry, err = upsert_knowledge_item(
            username,
            expert_id,
            title=item.get("title"),
            content=item.get("content"),
            source_url=item.get("source_url"),
            tags=item.get("tags"),
            crawl_session_id=result.get("crawl_session_id") or "",
        )
        if err:
            errors.append(err)
        elif entry:
            saved.append({"id": entry["id"], "title": entry["title"]})
    return (
        format_tool_result(
            {
                "message": "クロールと知識ベースへの保存が完了しました",
                "crawl_session_id": result.get("crawl_session_id"),
                "pages_total": result.get("pages_total"),
                "pages_saved": len(saved),
                "pages_excluded": result.get("pages_excluded"),
                "pages_error": result.get("pages_error"),
                "saved_items": saved[:20],
                "errors": errors[:5],
            }
        ),
        True,
    )


def iter_expert_crawl_tool(
    username,
    expert_id,
    arguments_str,
    *,
    llm_config=None,
):
    data = _parse_json_args(arguments_str)
    if data is None:
        yield {"type": "error", "message": "Invalid tool arguments JSON"}
        return

    expert = find_info_expert(username, expert_id)
    if not expert:
        yield {"type": "error", "message": "専門家が見つかりません"}
        return

    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        yield {"type": "error", "message": "有効な http(s) URL を指定してください"}
        return

    max_pages = int(data.get("max_pages") or 20)
    max_pages = max(1, min(max_pages, 50))
    summarize = data.get("summarize")
    if summarize is None:
        summarize = True
    else:
        summarize = bool(summarize)
    cfg = llm_config or {}

    try:
        result = None
        for evt in iter_crawl_pipeline(
            url,
            max_pages=max_pages,
            summarize=summarize and bool(cfg.get("api_base_url") and cfg.get("api_key")),
            api_base_url=cfg.get("api_base_url") or "",
            api_key=cfg.get("api_key") or "",
            model=cfg.get("model") or "",
        ):
            if evt.get("type") == "complete":
                result = evt.get("result")
            yield evt
        if not result:
            yield {"type": "error", "message": "クロール結果がありません"}
            return
        context, mutated = save_crawl_pipeline_result(username, expert_id, result)
        yield {"type": "tool_result", "ok": mutated, "context": context}
    except Exception as exc:
        yield {"type": "error", "message": f"クロールに失敗しました: {exc}"}


def execute_expert_tool(
    username,
    expert_id,
    tool_name,
    arguments_str,
    *,
    llm_config=None,
):
    data = _parse_json_args(arguments_str)
    if data is None:
        return format_tool_result(None, "Invalid tool arguments JSON"), False

    expert = find_info_expert(username, expert_id)
    if not expert:
        return format_tool_result(None, "専門家が見つかりません"), False

    if tool_name == "expert_crawl_site":
        url = (data.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return format_tool_result(None, "有効な http(s) URL を指定してください"), False
        max_pages = int(data.get("max_pages") or 20)
        max_pages = max(1, min(max_pages, 50))
        summarize = data.get("summarize")
        if summarize is None:
            summarize = True
        else:
            summarize = bool(summarize)
        cfg = llm_config or {}
        try:
            result = run_crawl_pipeline(
                url,
                max_pages=max_pages,
                summarize=summarize and bool(cfg.get("api_base_url") and cfg.get("api_key")),
                api_base_url=cfg.get("api_base_url") or "",
                api_key=cfg.get("api_key") or "",
                model=cfg.get("model") or "",
            )
        except Exception as exc:
            return format_tool_result(None, f"クロールに失敗しました: {exc}"), False
        return save_crawl_pipeline_result(username, expert_id, result)

    if tool_name == "expert_list_knowledge":
        items = list_knowledge_summaries(
            username, expert_id, max_items=int(data.get("max_results") or 30)
        )
        return format_tool_result({"items": items, "count": len(items)}), False

    if tool_name == "expert_read_knowledge":
        item_id = (data.get("id") or "").strip()
        if not item_id:
            return format_tool_result(None, "id is required"), False
        item = get_knowledge_item(username, expert_id, item_id)
        if not item:
            return format_tool_result(None, "項目が見つかりません"), False
        return format_tool_result({"item": item}), False

    if tool_name == "expert_upsert_knowledge":
        entry, err = upsert_knowledge_item(
            username,
            expert_id,
            item_id=(data.get("id") or "").strip() or None,
            title=data.get("title"),
            content=data.get("content"),
            source_url=data.get("source_url"),
            tags=data.get("tags"),
        )
        if err:
            return format_tool_result(None, err), False
        return (
            format_tool_result({"message": "知識を保存しました", "item": entry}),
            True,
        )

    if tool_name == "expert_delete_knowledge":
        item_id = (data.get("id") or "").strip()
        if not item_id:
            return format_tool_result(None, "id is required"), False
        ok, err = delete_knowledge_item(username, expert_id, item_id)
        if err:
            return format_tool_result(None, err), False
        return format_tool_result({"message": "知識を削除しました", "deleted": ok}), True

    if tool_name == "expert_search_knowledge":
        query = (data.get("query") or "").strip()
        items = search_knowledge_items(
            username,
            expert_id,
            query,
            max_results=int(data.get("max_results") or 12),
        )
        return format_tool_result({"query": query, "items": items}), False

    if tool_name == "expert_update_profile":
        patch = {}
        if "name" in data:
            patch["name"] = data.get("name")
        if "description" in data:
            patch["description"] = data.get("description")
        if "instructions" in data:
            patch["instructions"] = data.get("instructions")
        if not patch:
            return format_tool_result(None, "更新するフィールドがありません"), False
        entry, err = update_info_expert(username, expert_id, **patch)
        if err:
            return format_tool_result(None, err), False
        return (
            format_tool_result(
                {
                    "message": "専門家プロフィールを更新しました",
                    "expert": {
                        "id": entry.get("id"),
                        "name": entry.get("name"),
                        "description": entry.get("description"),
                    },
                }
            ),
            True,
        )

    return format_tool_result(None, f"Unknown tool: {tool_name}"), False
