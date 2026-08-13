"""Agent tools for FLUX 2.0 image generation."""

from __future__ import annotations

import json
import re

from image_generation_prefs import (
    normalize_user_image_generation_prefs,
    resolve_image_model_by_id,
)
from image_generation_registry import get_image_provider_credentials
from image_generation_service import generate_flux_image
from image_generation_storage import persist_generated_image_from_url

GENERATE_IMAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": (
            "FLUX 2.0 で画像を生成する。"
            "ユーザーがイラスト・写真風画像・デザイン・ビジュアルの新規作成を依頼したときに使用。"
            "使わない: 既存画像の説明のみ、テキスト回答だけで足りる質問、Web検索で済む最新情報。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "画像生成プロンプト（具体的な被写体・スタイル・構図。英語推奨）",
                },
                "reason": {
                    "type": "string",
                    "description": "ユーザー向け：何を生成するか（日本語で短く）",
                },
            },
            "required": ["prompt", "reason"],
        },
    },
}

IMAGE_GENERATION_TOOL_NAMES = frozenset({"generate_image"})

_IMAGE_GEN_VERB = re.compile(
    r"画像.{0,8}(生成|作成|描|作)|"
    r"(生成|作成|描いて|作って).{0,12}(画像|イラスト|絵)|"
    r"イラスト.{0,8}(生成|作成|描)|"
    r"generate.{0,12}image|create.{0,12}image",
    re.IGNORECASE,
)
_IMAGE_GEN_MORE = re.compile(
    r"^(もっと|さらに|もう少し|増や|追加|あと)",
    re.IGNORECASE,
)
_IMAGE_GEN_REDO = re.compile(
    r"描き直|作り直|別の|バリエーション|パターン|差し替",
    re.IGNORECASE,
)
_IMAGE_EXPLAIN_ONLY = re.compile(
    r"説明して|解説|何が写|意味|分析して|教えて$",
    re.IGNORECASE,
)
_ASSISTANT_IMAGE_DONE = re.compile(
    r"画像を生成|生成しています|生成中です|生成が完了|"
    r"完成です|完成しました|できました|作りました|"
    r"表示されています|表示済み|生成しました",
    re.IGNORECASE,
)

IMAGE_GENERATION_TOOL_REQUIRED_NUDGE = (
    "【システム】直前の返答では generate_image ツールを呼んでいません。"
    "ユーザーは新しい画像の生成（または修正版の再生成）を求めています。"
    "「画像を生成しています」「完成です」「生成しました」などの完了表現は、"
    "ツール実行前に書いてはいけません。必ず generate_image を1回だけ呼び出してください。"
    "prompt には英語で具体的な被写体・構図・スタイルを書いてください。"
)


def build_image_generation_tool_list():
    return [GENERATE_IMAGE_TOOL]


def _conversation_had_generate_image(messages):
    for msg in messages or []:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if fn.get("name") == "generate_image":
                return True
    return False


def user_wants_image_generation(user_text, messages=None):
    text = (user_text or "").strip()
    if not text:
        return False
    if _IMAGE_EXPLAIN_ONLY.search(text) and not _IMAGE_GEN_VERB.search(text):
        return False
    if _IMAGE_GEN_VERB.search(text):
        return True
    if _IMAGE_GEN_REDO.search(text):
        return True
    if _IMAGE_GEN_MORE.search(text) and _conversation_had_generate_image(messages):
        return True
    return False


def assistant_hallucinates_image_generation(content):
    return bool(_ASSISTANT_IMAGE_DONE.search(content or ""))


def image_generation_system_prompt_append():
    return (
        "\n\n## 画像生成（generate_image）\n"
        "ユーザーが新しい画像の作成・修正（「もっと〇〇」など）を求めたときは、必ず `generate_image` を呼び出す。\n"
        "手順:\n"
        "1. 短く生成内容を伝える（assistant 本文・1〜2文）\n"
        "2. 直後に `generate_image` を呼ぶ（`reason` は日本語、`prompt` は具体的な英語）\n"
        "画像サイズとエンジンはユーザーがチャット入力欄で選んだ設定が自動適用される（width/height は指定不要）。\n"
        "**禁止**\n"
        "- generate_image を呼ばずに「画像を生成しています」「生成中」「完成です」「生成しました」と書くこと\n"
        "- 英語の prompt 全文をユーザー向け本文に貼ること（prompt はツール引数のみ）\n"
        "- 前ターンの画像を文章だけで済ませること（修正依頼は必ず再度 generate_image）\n"
        "ツール完了後: 画像はUIに自動表示される。Markdown 画像記法・URLの再掲は不要。"
        "プロンプトの意図を日本語で短く説明するだけにする。\n"
    )


def parse_generate_image_tool_args(arguments_str):
    try:
        data = json.loads(arguments_str or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    prompt = (data.get("prompt") or "").strip()
    reason = (data.get("reason") or "").strip()
    if not prompt:
        return None
    return {
        "prompt": prompt,
        "reason": reason or prompt[:120],
    }


def format_image_generation_context(result, *, model_display_name=""):
    url = (result or {}).get("url") or ""
    prompt = (result or {}).get("prompt") or ""
    model_label = model_display_name or (result or {}).get("api_model") or "FLUX 2.0"
    lines = [
        f"画像生成が完了しました（モデル: {model_label}）。",
        f"プロンプト: {prompt}",
        f"画像URL: {url}",
        "チャット画面には既に生成画像が表示されています。"
        "回答本文に `![...](URL)` や同じURLの画像記法を入れないでください（重複表示になります）。",
    ]
    return "\n".join(lines)


def build_image_generation_followup_system(context, user_text=""):
    base = (
        "あなたは NEXGATE AI のアシスタントです。日本語で回答してください。\n\n"
        "【画像生成結果】\n"
        f"{context}\n\n"
        "上記の生成画像は既にチャットに表示済みです（ツール実行済みの場合のみ）。"
        "日本語で短く説明するだけにし、`![...](URL)` 形式や画像URLの再掲は禁止です。"
        "「生成しています」「完成です」など、今から生成するような表現は禁止。"
        "追加の generate_image 呼び出しも禁止です。"
    )
    if user_text:
        base += f"\n\nユーザーの依頼: {user_text}"
    return base


def execute_generate_image_tool(
    plan_key,
    image_generation_config,
    providers_config,
    arguments_str,
    *,
    user_prefs=None,
    username=None,
    public_base_url="",
):
    prefs = normalize_user_image_generation_prefs(
        user_prefs,
        plan_key=plan_key,
        image_generation=image_generation_config,
    )
    resolved = resolve_image_model_by_id(
        plan_key, image_generation_config, prefs["model_id"]
    )
    if not resolved:
        return None, "現在のプランでは利用できる画像生成モデルがありません。"
    api_key, base_url = get_image_provider_credentials(
        resolved["provider"], providers_config
    )
    if not api_key:
        return None, "画像生成用の BFL API キーが設定されていません（BFL_API_KEY または管理画面）"

    parsed = parse_generate_image_tool_args(arguments_str)
    if not parsed:
        return None, "画像生成パラメータが不正です。"

    width = prefs["width"]
    height = prefs["height"]

    try:
        result = generate_flux_image(
            api_key=api_key,
            base_url=base_url,
            api_model=resolved["api_model"],
            prompt=parsed["prompt"],
            width=width,
            height=height,
        )
    except RuntimeError as exc:
        return None, str(exc)

    result["model_id"] = resolved["model_id"]
    result["display_name"] = resolved.get("display_name") or resolved["model_id"]
    result["width"] = width
    result["height"] = height
    model_entry = resolved.get("entry") if isinstance(resolved.get("entry"), dict) else {}
    try:
        result["price_usd_per_image"] = max(
            0.0, float(model_entry.get("price_usd_per_image") or 0)
        )
    except (TypeError, ValueError):
        result["price_usd_per_image"] = 0.0

    provider_url = result.get("url") or ""
    if username and provider_url:
        try:
            stored = persist_generated_image_from_url(
                username,
                provider_url,
                prompt=result.get("prompt") or parsed["prompt"],
                model_id=result["model_id"],
                api_model=result.get("api_model") or "",
                width=width,
                height=height,
                base_url=public_base_url,
            )
            result["provider_url"] = provider_url
            result["url"] = stored["url"]
            result["image_id"] = stored["id"]
        except RuntimeError as exc:
            return None, str(exc)

    context = format_image_generation_context(
        result, model_display_name=result["display_name"]
    )
    return result, context


def stream_image_generation_events(
    plan_key,
    image_generation_config,
    providers_config,
    arguments_str,
    *,
    user_prefs=None,
    username=None,
    public_base_url="",
):
    parsed = parse_generate_image_tool_args(arguments_str)
    if not parsed:
        yield {"type": "error", "message": "画像生成パラメータが不正です"}
        return

    yield {
        "type": "intent",
        "reason": parsed["reason"],
        "prompt": parsed["prompt"],
    }
    yield {"type": "start", "prompt": parsed["prompt"]}

    result, context = execute_generate_image_tool(
        plan_key,
        image_generation_config,
        providers_config,
        arguments_str,
        user_prefs=user_prefs,
        username=username,
        public_base_url=public_base_url,
    )
    if result is None:
        yield {"type": "error", "message": context or "画像生成に失敗しました"}
        return

    yield {
        "type": "done",
        "url": result.get("url"),
        "prompt": result.get("prompt"),
        "model": result.get("display_name"),
        "price_usd": result.get("price_usd_per_image") or 0.0,
        "_result": result,
        "_context": context,
    }
