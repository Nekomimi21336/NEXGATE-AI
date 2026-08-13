#!/usr/bin/env python
"""対話検証スクリプト - Gmailツール呼び出しが後続ターンで発火しない問題を診断"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("FLASK_PORT", "15002")
os.environ.setdefault("FRONTEND_BASE_URL", "http://127.0.0.1:5000")
os.environ.setdefault("API_PORTAL_BASE_URL", "http://127.0.0.1:5001")
os.environ.setdefault("API_INTERNAL_URL", "http://127.0.0.1:5002")

# --- Bootstrap app ---
from app import app, load_system_config, load_users, resolve_chat_model
from chat_agent import (
    prepare_agent_messages,
    _stream_agent_chat_body,
    filter_tool_calls_for_web_access,
    openai_tool_calls_list,
    GOOGLE_TOOL_NAMES,
    stream_model_round,
    agent_system_message,
    apply_tool_choice_kwargs,
    _emit_round_events,
    empty_usage,
)
from chat_request_prepare import prepare_chat_send_job
from model_registry import normalize_model_entry
from google_agent_tools import build_google_tool_list

# --- Config ---
config = load_system_config()
models = config.get("models") or {}
provider_id = "deepseek"
model_id = list(models.keys())[0] if models else "deepseek-chat"
model_entry = models.get(model_id, {})
api_model = model_entry.get("api_model") or model_id
providers_cfg = config.get("providers") or {}
provider_cfg = providers_cfg.get(provider_id) or {}
api_key = provider_cfg.get("api_key") or os.getenv("DEEPSEEK_API_KEY") or ""

print(f"Model: {api_model} (provider={provider_id})")
print(f"API Key: {'***' + api_key[-4:] if api_key else 'NOT SET'}")

# --- Simulate conversation ---
# Messages exactly as they would arrive from the client after 2 rounds of Gmail
conversation = [
    {
        "role": "user",
        "content": "直近のメールを確認してほしい"
    },
    {
        "role": "assistant",
        "content": "直近のメールを確認します。",
        "tool_calls": [
            {
                "id": "call_gmail_list_1",
                "type": "function",
                "function": {
                    "name": "gmail_list",
                    "arguments": json.dumps({"max_results": 10})
                }
            }
        ]
    },
    {
        "role": "tool",
        "tool_call_id": "call_gmail_list_1",
        "content": json.dumps({
            "result": [
                {"id": "msg1", "subject": "マネーフォワードクラウド — 法人成り税額診断", "from": "moneyforward@example.com", "date": "2026-07-15"},
                {"id": "msg2", "subject": "GMOインターネット — ドメインクーポン", "from": "gmo@example.com", "date": "2026-07-15"},
                {"id": "msg3", "subject": "DDPS サーバー監視アラート", "from": "ddps@example.com", "date": "2026-07-14"},
                {"id": "msg4", "subject": "DDPS 月次レポート", "from": "ddps@example.com", "date": "2026-07-13"},
                {"id": "msg5", "subject": "DDPS メンテナンス通知", "from": "ddps@example.com", "date": "2026-07-12"},
            ]
        }, ensure_ascii=False)
    },
    {
        "role": "assistant",
        "content": "直近10件のメールを確認しました。DDPSからのメールが3件含まれています。"
    },
    # --- Round 2: GIGAMC ---
    {
        "role": "user",
        "content": "GIGAMCのメールを確認して"
    },
    {
        "role": "assistant",
        "content": "「GIGAMC」に該当するメールを検索します。",
        "tool_calls": [
            {
                "id": "call_gmail_search_1",
                "type": "function",
                "function": {
                    "name": "gmail_search",
                    "arguments": json.dumps({"query": "GIGAMC"})
                }
            }
        ]
    },
    {
        "role": "tool",
        "tool_call_id": "call_gmail_search_1",
        "content": json.dumps({
            "result": [
                {"id": "msg10", "subject": "GIGAMC メール送信テスト", "from": "support@gigamc.xyz", "date": "2026-06-16"},
                {"id": "msg11", "subject": "Linode Events Notification - GW-GIGAMC-Velocity", "from": "linode@example.com", "date": "2026-01-23"},
            ]
        }, ensure_ascii=False)
    },
    {
        "role": "assistant",
        "content": "「GIGAMC」関連のメールはテストメール1件のみでした。"
    },
    # --- Round 3: DDPS (problematic) ---
    {
        "role": "user",
        "content": "DDPSのメールを確認して"
    },
]

print(f"\n=== Conversation ({len(conversation)} messages) ===")
for i, m in enumerate(conversation):
    role = m.get("role", "?")
    content = m.get("content", "")[:80]
    has_tc = "TC" if m.get("tool_calls") else ""
    print(f"  [{i}] {role} {has_tc}: {content}...")

# --- Step 1: filter_chat_messages ---
from app import filter_chat_messages
filtered = filter_chat_messages(conversation, provider_id=provider_id)
print(f"\n=== After filter_chat_messages ({len(filtered)} messages) ===")
for i, m in enumerate(filtered):
    role = m.get("role", "?")
    content = str(m.get("content", ""))[:100]
    has_tc = "TC" if m.get("tool_calls") else ""
    print(f"  [{i}] {role} {has_tc}: {content}...")

# --- Step 2: prepare_agent_messages ---
messages = prepare_agent_messages(
    filtered,
    allow_web_search=True,
    provider_id=provider_id,
    agent_profile="deepseek",
    google_gmail_enabled=True,
)
print(f"\n=== After prepare_agent_messages ({len(messages)} messages) ===")
for i, m in enumerate(messages):
    role = m.get("role", "?")
    content = str(m.get("content", ""))[:150]
    has_tc = "TC" if m.get("tool_calls") else ""
    print(f"  [{i}] {role} {has_tc}: {content}...")

# --- Step 3: System prompt analysis ---
system_msg = messages[0]["content"] if messages else ""
print(f"\n=== System Prompt ({len(system_msg)} chars) ===")
# Check for Gmail-related instructions
gmail_lines = [l for l in system_msg.split("\n") if "gmail" in l.lower() or "メール" in l]
print(f"  Gmail-related lines: {len(gmail_lines)}")
for l in gmail_lines[:10]:
    print(f"    {l.strip()[:120]}")

# Check total token estimate
print(f"\n  Total messages: {len(messages)}")
total_chars = sum(len(str(m.get("content", ""))) for m in messages)
print(f"  Total chars: {total_chars} (~{total_chars // 4} tokens est.)")

# --- Step 4: Build agent_tools ---
from chat_agent import (
    build_ask_user_tool_list,
    WEB_SEARCH_TOOL,
    WEB_FETCH_TOOL,
    AGENT_TOOL_NAMES,
)
agent_tools = []
agent_tools.extend([WEB_SEARCH_TOOL, WEB_FETCH_TOOL])
agent_tools.extend(build_google_tool_list(False, True))
agent_tools = agent_tools or None
print(f"\n=== Agent Tools ({len(agent_tools) if agent_tools else 0}) ===")
if agent_tools:
    for t in agent_tools:
        fn = t.get("function", {})
        print(f"  - {fn.get('name', '?')}: {fn.get('description', '')[:100]}")

# --- Step 5: Call the model ---
if api_key:
    print(f"\n=== Calling model: {api_model} ===")
    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url=provider_cfg.get("base_url") or "https://api.deepseek.com",
    )
    
    kwargs = {"model": api_model, "messages": messages, "stream": True}
    tool_kwargs = {}
    if agent_tools:
        tool_kwargs["tools"] = agent_tools
        tool_kwargs["tool_choice"] = "auto"
    else:
        tool_kwargs["tool_choice"] = "none"
    kwargs.update(tool_kwargs)
    
    print(f"  tool_choice: {tool_kwargs.get('tool_choice')}")
    
    stream = client.chat.completions.create(**kwargs)
    
    content_parts = []
    tool_calls_map = {}
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if not delta:
            continue
        if delta.content:
            content_parts.append(delta.content)
            print(delta.content, end="", flush=True)
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {"id": tc.id or "", "function": {"name": "", "arguments": ""}}
                if tc.id:
                    tool_calls_map[idx]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        tool_calls_map[idx]["function"]["name"] += tc.function.name
                    if tc.function.arguments:
                        tool_calls_map[idx]["function"]["arguments"] += tc.function.arguments
    
    print("\n")
    content = "".join(content_parts)
    print(f"\n  Content length: {len(content)} chars")
    
    if tool_calls_map:
        print(f"  Tool calls: {len(tool_calls_map)}")
        for idx, tc in tool_calls_map.items():
            print(f"    [{idx}] {tc['function']['name']}({tc['function']['arguments'][:200]})")
    else:
        print("  NO TOOL CALLS!")
        
        # Check if content shows tool intent
        import re
        intent_re = re.compile(
            r"検索|調べ|確認|取得|一覧|リスト|探|送信|作成|追加|更新|削除|"
            r"(?:search|look.?up|find|list|check|fetch|send|create|add|update|delete)",
            re.IGNORECASE,
        )
        if intent_re.search(content):
            print("  ⚠️  CONTENT SHOWS TOOL INTENT but no tool_calls emitted!")
else:
    print("\n⚠️  API key not found - skipping model call")
    print("   Set DEEPSEEK_API_KEY env var or configure providers in system_config.json")
