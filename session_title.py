"""Generate a short chat session title from the user's first message (non-thinking)."""

from __future__ import annotations

import re

from chat_agent import (
    apply_disable_reasoning_kwargs,
    apply_tool_choice_kwargs,
    sanitize_assistant_text,
)
from token_usage import empty_usage, usage_from_openai

SESSION_TITLE_SYSTEM = (
    "あなたはチャットセッションのタイトルを付けるアシスタントです。"
    "ユーザーの最初のメッセージの内容がわかる短いタイトルを、1行だけ出力してください。\n"
    "ルール:\n"
    "- 日本語\n"
    "- 20文字以内を推奨（最大30文字）\n"
    "- 引用符・説明・句読点の羅列は不要\n"
    "- タイトルの文字列のみ（前置きや理由は書かない）"
)

def extract_plain_user_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
        return "\n".join(parts).strip()
    return ""


def fallback_session_title(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "新しいチャット"
    return t[:30] + ("…" if len(t) > 30 else "")


def normalize_session_title(raw: str) -> str:
    text = sanitize_assistant_text(raw or "")
    text = text.replace("\r\n", "\n").split("\n", 1)[0].strip()
    for pair in (('"', '"'), ("'", "'"), ("「", "」"), ("『", "』"), ("`", "`")):
        if text.startswith(pair[0]) and text.endswith(pair[1]) and len(text) >= 2:
            text = text[1:-1].strip()
            break
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    if len(text) > 30:
        return text[:30] + "…"
    return text


def generate_session_title(client, model, user_message, *, provider_id=None):
    prompt = (user_message or "").strip()
    if not prompt:
        return {"title": "", "usage": empty_usage()}

    messages = [
        {"role": "system", "content": SESSION_TITLE_SYSTEM},
        {"role": "user", "content": f"ユーザーの最初のメッセージ:\n{prompt[:2000]}"},
    ]
    kwargs = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": 48,
    }
    apply_tool_choice_kwargs(
        kwargs,
        tools=None,
        tool_choice="none",
        disable_reasoning=True,
        provider_id=provider_id,
    )
    apply_disable_reasoning_kwargs(kwargs, True, provider_id)

    response = client.chat.completions.create(**kwargs)
    msg = response.choices[0].message
    title = normalize_session_title(msg.content or "")
    usage = usage_from_openai(getattr(response, "usage", None))
    return {"title": title, "usage": usage}
