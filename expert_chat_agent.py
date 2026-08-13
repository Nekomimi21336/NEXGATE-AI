import json
import re
import time
from datetime import datetime

from chat_agent import (
    WEB_FETCH_TOOL,
    WEB_SEARCH_TOOL,
    WEB_TOOL_NAMES,
    _emit_round_events,
    _format_search_tool_content,
    _sse_fetch_event,
    _stream_followup_with_recovery,
    _yield_web_search_execution,
    append_tool_round_to_conversation,
    apply_reasoning_english_to_messages,
    complete_model_round,
    extract_user_text,
    filter_tool_calls_for_web_access,
    format_fetch_context,
    merge_search_result_lists,
    openai_tool_calls_list,
    parse_web_fetch_tool_args,
    stream_model_round,
    stream_web_fetch,
    strip_reasoning_content_from_messages,
)
from expert_agent_tools import (
    EXPERT_TOOL_NAMES,
    MUTATING_EXPERT_TOOLS,
    build_expert_tool_list,
    execute_expert_tool,
    expert_system_prompt_append,
    iter_expert_crawl_tool,
)
from expert_knowledge_storage import format_knowledge_for_prompt
from full_info_trace import full_info_payload
from info_experts_storage import serialize_expert
from token_usage import empty_usage, estimate_turn_tokens, merge_usage
from tool_trace import run_tool_calls_parallel, tool_trace_payload

MAX_EXPERT_TOOL_ROUNDS = 14
MAX_EXPERT_HISTORY_MESSAGES = 24
MAX_EXPERT_MESSAGE_CHARS = 6000
MAX_EXPERT_OLDER_MESSAGE_CHARS = 2800

_EXPERT_TOOL_CLAIM_RE = re.compile(
    r"知識ベースに(追加|保存|登録|反映)|クロール(しました|完了|を実行)|"
    r"(取得|保存|登録|更新|削除)(しました|完了)|ツールを(実行|使用|呼び出し)|"
    r"expert_[a-z_]+",
    re.I,
)
_EXPERT_ACTION_REQUEST_RE = re.compile(
    r"https?://|www\.|クロール|検索して|調べて|調査して|"
    r"知識(を|に)(追加|保存|登録|更新)|プロフィールを更新|削除して|"
    r"取り込んで|読み込んで|web_search|web_fetch",
    re.I,
)

EXPERT_BASE_PROMPT = """あなたは NEXGATE AI の Expert モード専用アシスタントです。
ユーザーの対話を通じて「専門家（InfoExpert）」を作成・育成します。

共通ルール:
- 日本語で、読みやすい段落と箇条書きで応答する
- 専門家の名前・説明・指示・知識ベースを段階的に整える
- 推測で事実を捏造しない。不明点は確認する
- Web検索と Expert ツールのみ利用可能（他ツールは使わない）
- ツール実行が必要なときは実際に呼び出してから報告する
"""


def _truncate_message_content(content, limit):
    text = str(content or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…[省略]"


def _truncate_chat_message(message, limit):
    role = message.get("role")
    if role == "user":
        return {"role": "user", "content": _truncate_message_content(message.get("content"), limit)}
    if role == "assistant":
        entry = {
            "role": "assistant",
            "content": _truncate_message_content(message.get("content"), limit),
        }
        if message.get("tool_calls"):
            entry["tool_calls"] = message["tool_calls"]
        return entry
    if role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.get("tool_call_id") or "",
            "content": _truncate_message_content(message.get("content"), limit),
        }
    return message


def trim_expert_chat_history(messages):
    if not messages:
        return messages
    system_msgs = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    if len(rest) <= MAX_EXPERT_HISTORY_MESSAGES:
        return system_msgs + [
            _truncate_chat_message(m, MAX_EXPERT_MESSAGE_CHARS) for m in rest
        ]
    omitted = len(rest) - MAX_EXPERT_HISTORY_MESSAGES
    kept = rest[-MAX_EXPERT_HISTORY_MESSAGES:]
    trimmed = []
    for idx, message in enumerate(kept):
        limit = (
            MAX_EXPERT_OLDER_MESSAGE_CHARS
            if idx < max(0, omitted)
            else MAX_EXPERT_MESSAGE_CHARS
        )
        trimmed.append(_truncate_chat_message(message, limit))
    notice = {
        "role": "user",
        "content": f"[以前の会話 {omitted} 件は省略されました。必要なら要点を再度指示してください。]",
    }
    return system_msgs + [notice] + trimmed


def _knowledge_prompt_budget(prepared_len):
    if prepared_len > 30:
        return 6, 3000
    if prepared_len > 16:
        return 8, 6000
    return 12, 12000


def _allowed_expert_tool_names(*, allow_web_search):
    allowed = set(EXPERT_TOOL_NAMES)
    if allow_web_search:
        allowed |= set(WEB_TOOL_NAMES)
    return frozenset(allowed)


def _should_force_expert_tool_round(user_text, assistant_content):
    if not (assistant_content or "").strip():
        return False
    if not _EXPERT_ACTION_REQUEST_RE.search(user_text or ""):
        return False
    return bool(_EXPERT_TOOL_CLAIM_RE.search(assistant_content))


def build_expert_creation_system_message(
    expert,
    *,
    creation_mode="chat",
    username=None,
    expert_id=None,
    kb_max_items=12,
    kb_max_chars=12000,
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    expert_data = serialize_expert(expert) or {}
    mode = (creation_mode or "chat").strip().lower()
    parts = [
        EXPERT_BASE_PROMPT,
        expert_system_prompt_append(creation_mode=mode),
        f"現在日時（サーバー）: {now}",
        f"作成中の専門家 ID: {expert_data.get('id') or ''}",
        f"専門家名: {expert_data.get('name') or '（未設定）'}",
        f"説明: {expert_data.get('description') or '（未設定）'}",
        f"指示: {expert_data.get('instructions') or '（未設定）'}",
        f"作成モード: {'URLクロール' if mode == 'crawl' else 'チャット'}",
    ]
    if mode == "chat":
        parts.append(
            "チャットモード: ユーザーとの対話から専門分野・回答方針・知識を聞き出し、"
            "expert_upsert_knowledge で知識化し、expert_update_profile でプロフィールを更新してください。"
        )
    else:
        parts.append(
            "クロールモード: ユーザーが渡すURLを expert_crawl_site で取り込み、"
            "要約結果を確認しながら expert_update_profile で専門家を仕上げてください。"
        )
    if username and expert_id:
        kb = format_knowledge_for_prompt(
            username,
            expert_id,
            max_items=kb_max_items,
            max_chars=kb_max_chars,
        )
        if kb:
            parts.append(kb)
    return "\n\n".join(parts)


def prepare_expert_chat_messages(prepared, expert, *, creation_mode="chat", username=None, expert_id=None, allow_web_search=True, provider_id=None, reasoning_in_english=False):
    kb_items, kb_chars = _knowledge_prompt_budget(len(prepared or []))
    system_content = build_expert_creation_system_message(
        expert,
        creation_mode=creation_mode,
        username=username,
        expert_id=expert_id,
        kb_max_items=kb_items,
        kb_max_chars=kb_chars,
    )
    if allow_web_search:
        system_content += (
            "\n\n## Web検索 (web_search / web_fetch)\n"
            "最新情報や指定URLの取得が必要なときのみ利用してください。"
        )
    msgs = trim_expert_chat_history(
        [{"role": "system", "content": system_content}, *(prepared or [])]
    )
    msgs = strip_reasoning_content_from_messages(msgs, provider_id)
    return apply_reasoning_english_to_messages(msgs, reasoning_in_english)


def _partition_tool_calls(tool_calls):
    crawl_calls = []
    expert_other = []
    web_search_calls = []
    web_fetch_calls = []
    for tc in tool_calls or []:
        name = tc["function"]["name"]
        if name == "expert_crawl_site":
            crawl_calls.append(tc)
        elif name in EXPERT_TOOL_NAMES:
            expert_other.append(tc)
        elif name == "web_search":
            web_search_calls.append(tc)
        elif name == "web_fetch":
            web_fetch_calls.append(tc)
    return crawl_calls, expert_other, web_search_calls, web_fetch_calls


def _yield_expert_round_web_tools(
    web_search_calls,
    web_fetch_calls,
    *,
    user_text,
    search_engines,
    sse_event,
    emit_tool_trace,
):
    tool_contents_by_id = {}
    traces = []
    executed = []
    all_results = []
    all_queries = []

    for tc in web_search_calls:
        batch = yield from _yield_web_search_execution(
            tc,
            user_text,
            search_engines,
            sse_event,
            emit_tool_trace=emit_tool_trace,
        )
        if not batch:
            continue
        all_results = merge_search_result_lists(all_results, batch["results"])
        all_queries.extend(batch["queries"])
        combined_query = ", ".join(dict.fromkeys(all_queries))
        tool_contents_by_id[tc["id"]] = _format_search_tool_content(
            all_results,
            combined_query,
            user_text,
            1,
            1,
        )
        executed.append(tc)

    for tc in web_fetch_calls:
        parsed = parse_web_fetch_tool_args(tc["function"]["arguments"])
        if not parsed:
            continue
        started = time.perf_counter()
        page = None
        for event in stream_web_fetch(parsed["url"], reason=parsed["reason"]):
            if event.get("type") == "done" and event.get("_page"):
                page = event["_page"]
            yield sse_event(_sse_fetch_event(event))
        context = format_fetch_context(
            page or {"url": parsed["url"], "text": ""},
            user_text=user_text,
            query=parsed["reason"],
        )
        tool_contents_by_id[tc["id"]] = context
        traces.append(("web_fetch", (time.perf_counter() - started) * 1000, True, None))
        executed.append(tc)

    return tool_contents_by_id, traces, executed


def stream_expert_tool_loop(
    client,
    model,
    messages,
    username,
    expert_id,
    initial_round_data,
    initial_tool_calls,
    sse_event,
    usage_out,
    *,
    user_text="",
    llm_config=None,
    allow_web_search=True,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    emit_tool_trace=False,
    emit_full_info=False,
):
    expert_tools = build_expert_tool_list()
    allowed_names = _allowed_expert_tool_names(allow_web_search=allow_web_search)
    search_engines = (llm_config or {}).get("search_engines") or {"ddg": True}
    conversation = list(messages)
    round_data = initial_round_data
    tool_calls = [
        tc for tc in initial_tool_calls if tc["function"]["name"] in allowed_names
    ]
    rounds = 0

    while tool_calls and rounds < MAX_EXPERT_TOOL_ROUNDS:
        rounds += 1
        yield sse_event({"segment_end": True})
        mutation_flags = []

        crawl_calls, expert_other, web_search_calls, web_fetch_calls = _partition_tool_calls(
            tool_calls
        )

        tool_contents_by_id = {}
        traces = []
        executed_calls = []

        if crawl_calls:
            crawl_contents, crawl_traces = yield from _stream_expert_crawl_calls(
                crawl_calls,
                username,
                expert_id,
                llm_config,
                sse_event,
                emit_full_info=emit_full_info,
            )
            tool_contents_by_id.update(crawl_contents)
            traces.extend(crawl_traces)
            executed_calls.extend(crawl_calls)
            mutation_flags.append(1)

        if expert_other:
            if emit_full_info:
                for tc in expert_other:
                    yield sse_event(
                        full_info_payload(
                            "tool_invoke",
                            name=tc["function"]["name"],
                            tool_call_id=tc["id"],
                            arguments=tc["function"]["arguments"],
                        )
                    )

            def expert_runner(tc):
                context, mutated = execute_expert_tool(
                    username,
                    expert_id,
                    tc["function"]["name"],
                    tc["function"]["arguments"],
                    llm_config=llm_config,
                )
                if mutated:
                    mutation_flags.append(1)
                return context

            other_contents, other_traces = run_tool_calls_parallel(
                expert_other, expert_runner, max_workers=4
            )
            tool_contents_by_id.update(other_contents)
            traces.extend(other_traces)
            executed_calls.extend(expert_other)
            if emit_full_info:
                for tc in expert_other:
                    yield sse_event(
                        full_info_payload(
                            "tool_result",
                            name=tc["function"]["name"],
                            tool_call_id=tc["id"],
                            content=tool_contents_by_id.get(tc["id"]) or "",
                        )
                    )

        if allow_web_search and (web_search_calls or web_fetch_calls):
            web_contents, web_traces, web_executed = yield from _yield_expert_round_web_tools(
                web_search_calls,
                web_fetch_calls,
                user_text=user_text,
                search_engines=search_engines,
                sse_event=sse_event,
                emit_tool_trace=emit_tool_trace,
            )
            tool_contents_by_id.update(web_contents)
            traces.extend(web_traces)
            executed_calls.extend(web_executed)

        if not executed_calls:
            break

        yield from _yield_expert_tool_trace(
            sse_event, emit_tool_trace, traces, executed_calls
        )
        if mutation_flags:
            yield sse_event({"expert_knowledge_updated": True})

        conversation = trim_expert_chat_history(conversation)
        conversation = append_tool_round_to_conversation(
            conversation,
            round_data,
            executed_calls,
            tool_contents_by_id,
            provider_id=provider_id,
        )
        yield sse_event({"segment_start": True, "discard_previous": False})

        round_state = {
            "round_data": None,
            "reasoning_streamed": False,
            "reasoning_done_sent": False,
            "reasoning_card_started": False,
            "reasoning_emitted_len": 0,
            "reasoning_buffer": [],
            "usage_out": usage_out,
            "emit_reasoning_cards": emit_reasoning_cards,
        }
        all_tools = list(expert_tools)
        if allow_web_search:
            all_tools = [WEB_SEARCH_TOOL, WEB_FETCH_TOOL] + all_tools
        conversation = trim_expert_chat_history(conversation)
        if emit_full_info:
            from full_info_trace import model_request_payload

            yield sse_event(
                model_request_payload(
                    model,
                    conversation,
                    tools=all_tools,
                    label=f"expert_tool_round_{rounds}",
                )
            )
        for kind, payload in stream_model_round(
            client,
            model,
            conversation,
            all_tools,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
        ):
            yield from _emit_round_events(kind, payload, sse_event, round_state)
            if kind == "end":
                round_data = round_state["round_data"]

        if round_data is None:
            tool_calls = []
            break

        merge_usage(usage_out, round_data.get("usage") or {})
        next_calls = openai_tool_calls_list(round_data["tool_calls_map"], allowed_names)
        tool_calls = [
            tc for tc in (next_calls or []) if tc["function"]["name"] in allowed_names
        ]

    if tool_calls:
        yield sse_event({"segment_start": True, "discard_previous": False})
        yield from _stream_followup_with_recovery(
            client,
            model,
            trim_expert_chat_history(conversation),
            user_text,
            sse_event,
            usage_out,
            emit_reasoning_cards=emit_reasoning_cards,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            recovery_hint="これまでの Expert ツール結果を根拠に、ユーザーへ日本語で報告してください。",
            allow_recovery=False,
        )


def prepared_from_messages(conversation):
    return [m for m in conversation if m.get("role") in ("user", "assistant")]


def _stream_expert_crawl_calls(
    tool_calls,
    username,
    expert_id,
    llm_config,
    sse_event,
    *,
    emit_full_info=False,
):
    tool_contents_by_id = {}
    traces = []
    for tc in tool_calls:
        name = tc["function"]["name"]
        if emit_full_info:
            yield sse_event(
                full_info_payload(
                    "tool_invoke",
                    name=name,
                    tool_call_id=tc["id"],
                    arguments=tc["function"]["arguments"],
                )
            )
        started = time.perf_counter()
        context = None
        ok = True
        err = None
        for evt in iter_expert_crawl_tool(
            username,
            expert_id,
            tc["function"]["arguments"],
            llm_config=llm_config,
        ):
            evt_type = evt.get("type")
            if evt_type == "error":
                ok = False
                err = evt.get("message")
                yield sse_event({"expert_crawl": {"type": "error", "message": err}})
                break
            if evt_type == "tool_result":
                context = evt.get("context")
                ok = bool(evt.get("ok"))
                break
            yield sse_event({"expert_crawl": evt})
        duration_ms = (time.perf_counter() - started) * 1000
        if context is None and not err:
            context = json.dumps({"ok": False, "error": "crawl failed"}, ensure_ascii=False)
            ok = False
        tool_contents_by_id[tc["id"]] = context or ""
        traces.append((name, duration_ms, ok, err))
        if emit_full_info:
            yield sse_event(
                full_info_payload(
                    "tool_result",
                    name=name,
                    tool_call_id=tc["id"],
                    content=tool_contents_by_id[tc["id"]],
                )
            )
    return tool_contents_by_id, traces


def _yield_expert_tool_trace(sse_event, emit_tool_trace, traces, tool_calls):
    if emit_tool_trace and traces:
        for name, duration_ms, ok, err in traces:
            yield sse_event(
                tool_trace_payload(name, duration_ms, ok=ok, error=err)
            )
    for tc in tool_calls:
        if tc["function"]["name"] in MUTATING_EXPERT_TOOLS:
            yield sse_event({"expert_tool_used": True})


def stream_expert_creation_chat(
    prepared,
    expert,
    *,
    username,
    expert_id,
    creation_mode="chat",
    api_key,
    model,
    make_client,
    sse_event,
    usage_out=None,
    allow_web_search=True,
    search_engines=None,
    emit_reasoning_cards=True,
    disable_reasoning=False,
    provider_id=None,
    reasoning_in_english=False,
    emit_tool_trace=False,
    llm_config=None,
    agent_profile="deepseek",
    emit_full_info=False,
):
    usage_out = usage_out if usage_out is not None else empty_usage()
    if not api_key:
        user_text = extract_user_text(prepared)
        demo = f"デモモードです。API キーを設定してください。\n\nメッセージ: 「{user_text}」"
        for word in demo.split():
            yield sse_event({"content": word + " "})
        merge_usage(usage_out, estimate_turn_tokens(prepared, demo, "", model))
        yield sse_event({"done": True, "usage": usage_out})
        return

    client = make_client(api_key)
    user_text = extract_user_text(prepared)
    messages = prepare_expert_chat_messages(
        prepared,
        expert,
        creation_mode=creation_mode,
        username=username,
        expert_id=expert_id,
        allow_web_search=allow_web_search,
        provider_id=provider_id,
        reasoning_in_english=reasoning_in_english,
    )

    tool_list = build_expert_tool_list()
    if allow_web_search:
        tool_list = [WEB_SEARCH_TOOL, WEB_FETCH_TOOL] + tool_list

    cfg = dict(llm_config or {})
    cfg["search_engines"] = search_engines or {"ddg": True}

    round_state = {
        "round_data": None,
        "reasoning_streamed": False,
        "reasoning_done_sent": False,
        "reasoning_card_started": False,
        "reasoning_emitted_len": 0,
        "reasoning_buffer": [],
        "usage_out": usage_out,
        "emit_reasoning_cards": emit_reasoning_cards,
    }
    messages = trim_expert_chat_history(messages)
    if emit_full_info:
        from full_info_trace import model_request_payload, sanitize_messages_for_full_info

        yield sse_event(
            full_info_payload(
                "turn_start",
                messages=sanitize_messages_for_full_info(prepared),
            )
        )
        yield sse_event(
            model_request_payload(
                model,
                messages,
                tools=tool_list,
                label="expert_initial",
            )
        )
    for kind, payload in stream_model_round(
        client,
        model,
        messages,
        tool_list,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
    ):
        yield from _emit_round_events(kind, payload, sse_event, round_state)

    round_data = round_state["round_data"]
    if round_data is None:
        yield sse_event({"done": True, "usage": usage_out})
        return

    allowed = _allowed_expert_tool_names(allow_web_search=allow_web_search)
    tool_calls = openai_tool_calls_list(round_data["tool_calls_map"], allowed)
    if (
        tool_calls
        and not (round_data.get("reasoning_content") or "").strip()
        and (round_data.get("content") or "").strip()
    ):
        streamed_content = round_data.get("content") or ""
        round_data = complete_model_round(
            client,
            model,
            messages,
            tool_list,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
        )
        merge_usage(usage_out, round_data.get("usage"))
        if streamed_content:
            round_data["content"] = streamed_content
        tool_calls = openai_tool_calls_list(round_data["tool_calls_map"], allowed)

    tool_calls = filter_tool_calls_for_web_access(
        tool_calls, allow_web_search, allow_image_generation=False
    )

    if not tool_calls and _should_force_expert_tool_round(
        user_text, round_data.get("content") or ""
    ):
        if (round_data.get("content") or "").strip():
            yield sse_event({"segment_end": True})
        round_data = complete_model_round(
            client,
            model,
            messages,
            tool_list,
            disable_reasoning=disable_reasoning,
            provider_id=provider_id,
            tool_choice="required",
        )
        merge_usage(usage_out, round_data.get("usage"))
        tool_calls = openai_tool_calls_list(round_data["tool_calls_map"], allowed)
        tool_calls = filter_tool_calls_for_web_access(
            tool_calls, allow_web_search, allow_image_generation=False
        )

    if not tool_calls:
        if not usage_out.get("total_tokens"):
            merge_usage(
                usage_out,
                estimate_turn_tokens(
                    messages,
                    round_data.get("content") or "",
                    round_data.get("reasoning_content") or "",
                    model,
                ),
            )
        yield sse_event({"done": True, "usage": usage_out})
        return

    yield from stream_expert_tool_loop(
        client,
        model,
        messages,
        username,
        expert_id,
        round_data,
        tool_calls,
        sse_event,
        usage_out,
        user_text=user_text,
        llm_config=cfg,
        allow_web_search=allow_web_search,
        emit_reasoning_cards=emit_reasoning_cards,
        disable_reasoning=disable_reasoning,
        provider_id=provider_id,
        emit_tool_trace=emit_tool_trace,
        emit_full_info=emit_full_info,
    )
    if not usage_out.get("total_tokens"):
        merge_usage(usage_out, estimate_turn_tokens(messages, "", "", model))
    yield sse_event({"done": True, "usage": usage_out})
