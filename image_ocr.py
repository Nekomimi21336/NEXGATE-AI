"""Image resize and Anthropic vision text-only OCR for chat preprocessing."""

from __future__ import annotations

import base64
import io
import re
from typing import Any

import httpx

from extended_models_registry import get_anthropic_api_key

LONG_EDGE_MAX = 1568
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
OCR_CONTENT_MARKER = "[画像内の文字]"
OCR_LEGACY_CONTENT_MARKER = "[画像内容]"
STRUCTURED_DOCUMENT_MARKER = "[文書構造化]"
OCR_NO_TEXT_PLACEHOLDER = "（画像内に読み取れる文字はありません）"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"

OCR_SYSTEM_PROMPT = (
    "You are a strict text-only OCR transcriber. Extract ONLY visible characters from images. "
    "Never describe scenes, objects, people, memes, characters, UI layout, colors, or spatial relationships. "
    "Never interpret, explain, or guess what the image depicts. Never invent text. "
    "Output plain text only (no markdown fences or section headings). "
    f"If there is no readable text, output exactly: {OCR_NO_TEXT_PLACEHOLDER}"
)

OCR_USER_PROMPT = (
    "Transcribe ALL visible text in this image.\n"
    "- Preserve line breaks and natural reading order.\n"
    "- Copy text exactly as shown; do not add commentary.\n"
    "- Use Japanese when the text is primarily Japanese; otherwise use the dominant language in the image.\n"
    f"- If no readable text exists, output only: {OCR_NO_TEXT_PLACEHOLDER}\n"
    "- FORBIDDEN: scene descriptions, object or character identification, meme or cultural interpretation, "
    "guessing subjects, colors, layout, or any content beyond literal visible text."
)

_OCR_SECTION_HEADER_RE = re.compile(
    r"^(?:#+\s*)?(?:transcription|ocr|text extraction|extracted text|"
    r"抽出(?:結果|テキスト)?|文字(?:列)?|読み取り結果)\s*:?\s*$",
    re.IGNORECASE,
)
_OCR_FORBIDDEN_LINE_RE = re.compile(
    r"(?:"
    r"\b(?:the image (?:shows|depicts|contains|appears)|this (?:image|picture|screenshot) (?:shows|depicts|contains))\b"
    r"|(?:この)?画像(?:には|は|を見ると|からは).{0,40}(?:写って|描かれ|表示され|確認でき|見え)"
    r"|\b(?:scene description|visual(?:ly)?|meme|character identification)\b"
    r"|(?:シーン|場面|構図|配色|レイアウト).{0,24}(?:です|ます|である|と思|らしい)"
    r"|(?:と思われ|と推測|と考えられ|のようです|らしいです|かもしれません)\s*$"
    r"|^(?:説明|解説|要約)\s*[:：]"
    r")",
    re.IGNORECASE,
)
_OCR_IMAGE_CONTENT_QUESTION_RE = re.compile(
    r"(?:どんな内容|何の内容|内容は何|内容を教|何が書いて|何と書いて|"
    r"何が書かれ|読み取って|読み取り|文字を教|テキストを教|文字起こし)",
    re.IGNORECASE,
)

OCR_CHAT_SYSTEM_APPEND = """

## 添付画像（文字OCRのみ）
提供されているのは添付画像から機械抽出した**表示文字のテキストのみ**です。画像そのもの・視覚情報・シーンはモデルに渡されていません。

**厳守**
- 映像作品・ゲーム・ミーム・SCP・人物・キャラクター・出典・シーン解説への言及や推測を一切行わない
- `[画像内の文字]` または `[画像内容]` ブロック内の文字列以外を根拠にしない（過去メッセージの `[画像内容]` も文字列の転写としてのみ扱う）
- 抽出テキストに無い語句・ストーリー・世界観を補完しない

**「どんな内容」「何が書いてある」等の質問**
- 抽出テキストの要約・言い換え・整理のみ（外部知識での解釈禁止）
- 推奨: 「画像内の文字は以下の通りです。」のあと、抽出テキストをそのまままたは短く整理して示す
- 読み取れる文字が無い場合はその旨のみ述べる"""

STRUCTURED_DOCUMENT_CHAT_APPEND = """

## 添付文書（構造化済み）
別の文書構造化モジュールが、画像から OCR したうえで設問・セクション・意図を復元した結果です。チャット用 AI はこのブロックを**唯一の根拠**として答えてください。画像そのものは渡されていません。

**厳守**
- `[文書構造化]` ブロック内のセクション・設問・選択肢・手順以外を根拠にしない
- 構造化結果に無い設問・選択肢・解答を推測で補完しない
- 映像・ミーム・シーン解説など文書外の知識で答えない

**答え方**
- ユーザーが教材の内容・設問・手順について聞いた場合は、構造化 Markdown を要約・整理して答える
- 並べ替え・選択・記述問題は、構造化データの `type`（ordering / multiple_choice 等）に沿って説明する
- 構造化に情報が無い場合はその旨のみ述べる"""

ALLOWED_IMAGE_MEDIA_TYPES = frozenset(
    ("image/jpeg", "image/png", "image/gif", "image/webp")
)

_MEDIA_TYPE_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "image/x-png": "image/png",
}


def normalize_image_media_type(media_type: str) -> str | None:
    cleaned = (media_type or "").split(";", 1)[0].strip().lower()
    if not cleaned:
        return None
    cleaned = _MEDIA_TYPE_ALIASES.get(cleaned, cleaned)
    if cleaned in ALLOWED_IMAGE_MEDIA_TYPES:
        return cleaned
    return None


def resize_image(image_bytes: bytes, long_edge_max: int = LONG_EDGE_MAX) -> tuple[bytes, str]:
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    long_edge = max(w, h)
    if long_edge > long_edge_max:
        scale = long_edge_max / float(long_edge)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue(), "image/jpeg"


def parse_data_url(url: str) -> tuple[bytes, str] | None:
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith("data:"):
        return None
    comma = url.find(",")
    if comma < 0:
        return None
    meta = url[5:comma]
    payload = url[comma + 1 :]
    if ";base64" not in meta:
        return None
    media_type = normalize_image_media_type(meta.split(";", 1)[0])
    if not media_type:
        return None
    payload = "".join(payload.split())
    try:
        raw = base64.standard_b64decode(payload)
    except Exception:
        try:
            raw = base64.b64decode(payload, altchars=b"-_")
        except Exception:
            return None
    if not raw:
        return None
    if len(raw) > MAX_IMAGE_UPLOAD_BYTES:
        return None
    return raw, media_type


def _text_has_ocr_marker(text: str) -> bool:
    return (
        OCR_CONTENT_MARKER in text
        or OCR_LEGACY_CONTENT_MARKER in text
        or STRUCTURED_DOCUMENT_MARKER in text
    )


def _text_has_structured_marker(text: str) -> bool:
    return STRUCTURED_DOCUMENT_MARKER in text


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        inner = stripped[3:-3].strip()
        if inner.lower().startswith("text\n"):
            inner = inner[5:]
        return inner.strip()
    return stripped


def _line_looks_like_ocr_commentary(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _OCR_SECTION_HEADER_RE.match(s):
        return True
    return bool(_OCR_FORBIDDEN_LINE_RE.search(s))


def sanitize_ocr_transcript(text: str) -> str:
    raw = _strip_markdown_fences((text or "").strip())
    if not raw:
        return OCR_NO_TEXT_PLACEHOLDER
    if raw == OCR_NO_TEXT_PLACEHOLDER:
        return raw

    kept: list[str] = []
    for line in raw.splitlines():
        if _line_looks_like_ocr_commentary(line):
            continue
        kept.append(line.rstrip())

    result = "\n".join(kept).strip()
    if not result:
        return OCR_NO_TEXT_PLACEHOLDER
    return result


def strip_image_urls_from_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content
    filtered = [
        p
        for p in content
        if not (isinstance(p, dict) and p.get("type") == "image_url")
    ]
    if len(filtered) == len(content):
        return content
    if not filtered:
        return content
    if len(filtered) == 1 and filtered[0].get("type") == "text":
        return filtered[0].get("text") or ""
    return filtered


def messages_include_ocr_context(messages: list[dict]) -> bool:
    for msg in messages or []:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if _content_has_plain_ocr(content):
            return True
    return False


def messages_include_structured_document(messages: list[dict]) -> bool:
    for msg in messages or []:
        if msg.get("role") != "user":
            continue
        if _content_has_structured_document(msg.get("content")):
            return True
    return False


def _content_has_plain_ocr(content: Any) -> bool:
    if isinstance(content, str):
        return (
            OCR_CONTENT_MARKER in content or OCR_LEGACY_CONTENT_MARKER in content
        ) and STRUCTURED_DOCUMENT_MARKER not in content
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text") or ""
                if (
                    OCR_CONTENT_MARKER in text or OCR_LEGACY_CONTENT_MARKER in text
                ) and STRUCTURED_DOCUMENT_MARKER not in text:
                    return True
    return False


def _content_has_structured_document(content: Any) -> bool:
    if isinstance(content, str):
        return STRUCTURED_DOCUMENT_MARKER in content
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                if STRUCTURED_DOCUMENT_MARKER in (part.get("text") or ""):
                    return True
    return False


def build_structured_document_chat_system_append() -> str:
    return STRUCTURED_DOCUMENT_CHAT_APPEND


def user_asks_image_text_question(messages: list[dict]) -> bool:
    for msg in reversed(messages or []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        text = content if isinstance(content, str) else ""
        if isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            text = "\n".join(parts)
        text = (text or "").strip()
        if not text:
            return False
        user_part = text.split(OCR_CONTENT_MARKER, 1)[0]
        user_part = user_part.split(OCR_LEGACY_CONTENT_MARKER, 1)[0]
        user_part = user_part.split(STRUCTURED_DOCUMENT_MARKER, 1)[0]
        return bool(_OCR_IMAGE_CONTENT_QUESTION_RE.search(user_part.strip()))
    return False


def build_ocr_chat_system_append(messages: list[dict]) -> str:
    extra = OCR_CHAT_SYSTEM_APPEND
    if user_asks_image_text_question(messages):
        extra += (
            "\n\n【今回のユーザー質問】画像内文字の説明のみ。"
            "作品名・ミーム・SCP・シーン解説は禁止。"
            "回答は「画像内の文字は以下の通りです。」から始め、抽出テキストを根拠に答えること。"
        )
    return extra


def content_already_has_ocr(content: Any) -> bool:
    if isinstance(content, str):
        return _text_has_ocr_marker(content)
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                if _text_has_ocr_marker(part.get("text") or ""):
                    return True
    return False


def _anthropic_image_block(image_bytes: bytes, media_type: str) -> dict:
    resized, out_type = resize_image(image_bytes)
    b64 = base64.standard_b64encode(resized).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": out_type,
            "data": b64,
        },
    }


def call_anthropic_vision(
    *,
    api_key: str,
    api_model: str,
    image_bytes: bytes,
    media_type: str,
    max_tokens: int = 4096,
) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": api_model,
        "max_tokens": max_tokens,
        "system": OCR_SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    _anthropic_image_block(image_bytes, media_type),
                    {"type": "text", "text": OCR_USER_PROMPT},
                ],
            }
        ],
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(ANTHROPIC_MESSAGES_URL, headers=headers, json=body)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        try:
            err_json = resp.json()
            detail = err_json.get("error", {}).get("message") or detail
        except Exception:
            pass
        raise RuntimeError(f"OCR API error ({resp.status_code}): {detail}")

    data = resp.json()
    parts = []
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    text = "\n".join(p.strip() for p in parts if p and str(p).strip()).strip()
    if not text:
        return OCR_NO_TEXT_PLACEHOLDER
    return sanitize_ocr_transcript(text)


def ocr_image_from_data_url(data_url: str, *, api_key: str, api_model: str) -> str:
    parsed = parse_data_url(data_url)
    if not parsed:
        raise ValueError("画像データの形式が不正です")
    image_bytes, media_type = parsed
    return call_anthropic_vision(
        api_key=api_key,
        api_model=api_model,
        image_bytes=image_bytes,
        media_type=media_type,
    )


def ocr_image_from_data_url_with_engine(
    data_url: str,
    *,
    engine: str = "ai",
    api_key: str = "",
    api_model: str = "",
    config: dict | None = None,
) -> str:
    if engine == "local":
        from ocr_dependencies import ensure_ocr_dependencies

        ensure_ocr_dependencies()
        from document_structure_service import structure_image_from_data_url

        result = structure_image_from_data_url(data_url, config=config or {})
        return format_structured_document_for_chat(result)
    if not api_key:
        raise RuntimeError("AI OCR用の Anthropic API キーが設定されていません")
    if not api_model:
        raise RuntimeError("AI OCR用のモデルが設定されていません")
    return ocr_image_from_data_url(data_url, api_key=api_key, api_model=api_model)


def message_has_images(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    return any(
        isinstance(p, dict) and p.get("type") == "image_url"
        for p in content
    )


def extract_image_urls(content: Any) -> list[str]:
    if not isinstance(content, list):
        return []
    urls = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "image_url":
            continue
        block = part.get("image_url") or {}
        url = (block.get("url") or block.get("data") or "").strip()
        if url:
            urls.append(url)
    return urls


def format_structured_document_for_chat(result: dict[str, Any]) -> str:
    lines = [STRUCTURED_DOCUMENT_MARKER]
    title = str(result.get("title") or "").strip()
    summary = str(result.get("summary") or "").strip()
    if title:
        lines.append(f"タイトル: {title}")
    if summary:
        lines.append(f"要約: {summary}")
    if title or summary:
        lines.append("")
    markdown = str(result.get("markdown") or "").strip()
    if markdown:
        lines.append(markdown)
    else:
        lines.append(str(result.get("ocr_text") or "").strip())
    return "\n".join(line for line in lines if line is not None).strip()


def augment_content_with_extraction_block(
    content: Any,
    sections: list[str],
    marker: str,
) -> Any:
    combined = "\n\n".join(s.strip() for s in sections if s and s.strip()).strip()
    if not combined:
        return content

    block = f"{marker}\n{combined}"
    if isinstance(content, str):
        base = content.strip()
        return f"{base}\n\n{block}" if base else block

    if not isinstance(content, list):
        return block

    text_parts = []
    non_image = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "image_url":
            continue
        non_image.append(part)
        if part.get("type") == "text":
            text_parts.append(part.get("text") or "")

    merged_text = "\n".join(t.strip() for t in text_parts if t and str(t).strip()).strip()
    if merged_text:
        new_text = f"{merged_text}\n\n{block}"
    else:
        new_text = block

    rebuilt = [{"type": "text", "text": new_text}]
    for part in non_image:
        if part.get("type") == "text":
            continue
        rebuilt.append(part)
    if len(rebuilt) == 1:
        return rebuilt[0]["text"]
    return rebuilt


def augment_content_with_ocr(content: Any, ocr_sections: list[str]) -> Any:
    return augment_content_with_extraction_block(content, ocr_sections, OCR_CONTENT_MARKER)


def preprocess_messages_with_ocr(
    messages: list[dict],
    *,
    api_key: str = "",
    api_model: str = "",
    engine: str = "ai",
    config: dict | None = None,
    enabled: bool = True,
) -> list[dict]:
    if not enabled:
        return messages
    engine = str(engine or "ai").strip().lower()
    if engine == "ai" and not api_key:
        return messages

    extraction_marker = (
        STRUCTURED_DOCUMENT_MARKER if engine == "local" else OCR_CONTENT_MARKER
    )

    out = []
    for msg in messages:
        if msg.get("role") != "user":
            out.append(msg)
            continue
        content = msg.get("content")
        if not message_has_images(content):
            out.append(msg)
            continue
        if content_already_has_ocr(content):
            stripped = strip_image_urls_from_content(content)
            out.append({**msg, "content": stripped} if stripped != content else msg)
            continue

        urls = extract_image_urls(content)
        ocr_sections = []
        for idx, url in enumerate(urls, start=1):
            try:
                text = ocr_image_from_data_url_with_engine(
                    url,
                    engine=engine,
                    api_key=api_key,
                    api_model=api_model,
                    config=config,
                )
                if len(urls) > 1:
                    ocr_sections.append(f"--- 画像 {idx} ---\n{text}")
                else:
                    ocr_sections.append(text)
            except Exception as exc:
                label = f"画像 {idx}" if len(urls) > 1 else "画像"
                ocr_sections.append(f"[{label}の文字抽出に失敗: {exc}]")

        new_content = augment_content_with_extraction_block(
            content, ocr_sections, extraction_marker
        )
        new_content = strip_image_urls_from_content(new_content)
        out.append({**msg, "content": new_content})
    return out
