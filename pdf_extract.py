"""Local text extraction from PDF attachments in chat preprocessing."""

from __future__ import annotations

import base64
import io
from typing import Any

from pypdf import PdfReader

MAX_PDF_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PDF_EXTRACT_CHARS = 80_000
PDF_CONTENT_MARKER = "[PDF内の文字]"
PDF_LEGACY_CONTENT_MARKER = "[PDF内容]"
PDF_NO_TEXT_PLACEHOLDER = "（PDFから抽出できるテキストがありません）"

PDF_CHAT_SYSTEM_APPEND = """

## 添付PDF（テキスト抽出のみ）
提供されているのはPDFから機械抽出した**文字列のみ**です。PDFバイナリ・レイアウト・図表の視覚解釈はモデルに渡されていません。

**厳守**
- `[PDF内の文字]` ブロック内のテキスト以外を根拠にしない
- 抽出テキストに無い内容の推測・補完をしない
- シーン説明・文書の意図推測は行わず、質問には抽出テキストに基づいて答える"""


def _text_has_pdf_marker(text: str) -> bool:
    return PDF_CONTENT_MARKER in text or PDF_LEGACY_CONTENT_MARKER in text


def parse_pdf_data_url(url: str) -> bytes | None:
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith("data:"):
        return None
    comma = url.find(",")
    if comma < 0:
        return None
    meta = url[5:comma]
    if ";base64" not in meta:
        return None
    media_type = meta.split(";", 1)[0].strip().lower()
    if media_type != "application/pdf":
        return None
    payload = "".join(url[comma + 1 :].split())
    try:
        raw = base64.standard_b64decode(payload)
    except Exception:
        try:
            raw = base64.b64decode(payload, altchars=b"-_")
        except Exception:
            return None
    if not raw:
        return None
    if len(raw) > MAX_PDF_UPLOAD_BYTES:
        return None
    if not raw.startswith(b"%PDF"):
        return None
    return raw


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(text)
    combined = "\n\n".join(parts).strip()
    if not combined:
        return PDF_NO_TEXT_PLACEHOLDER
    if len(combined) > MAX_PDF_EXTRACT_CHARS:
        combined = (
            combined[:MAX_PDF_EXTRACT_CHARS].rstrip()
            + "\n\n（PDFテキストが長いため一部を省略しました）"
        )
    return combined


def extract_text_from_pdf_data_url(data_url: str) -> str:
    raw = parse_pdf_data_url(data_url)
    if raw is None:
        raise ValueError("PDFデータの形式が不正です")
    return extract_text_from_pdf_bytes(raw)


def message_has_pdfs(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    return any(isinstance(p, dict) and p.get("type") == "pdf_url" for p in content)


def extract_pdf_urls(content: Any) -> list[str]:
    if not isinstance(content, list):
        return []
    urls = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "pdf_url":
            continue
        block = part.get("pdf_url") or {}
        url = (block.get("url") or block.get("data") or "").strip()
        if url:
            urls.append(url)
    return urls


def content_already_has_pdf(content: Any) -> bool:
    if isinstance(content, str):
        return _text_has_pdf_marker(content)
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                if _text_has_pdf_marker(part.get("text") or ""):
                    return True
    return False


def strip_pdf_urls_from_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content
    filtered = [
        p
        for p in content
        if not (isinstance(p, dict) and p.get("type") == "pdf_url")
    ]
    if len(filtered) == len(content):
        return content
    if not filtered:
        return content
    if len(filtered) == 1 and filtered[0].get("type") == "text":
        return filtered[0].get("text") or ""
    return filtered


def augment_content_with_pdf(content: Any, pdf_sections: list[str]) -> Any:
    combined = "\n\n".join(s.strip() for s in pdf_sections if s and s.strip()).strip()
    if not combined:
        return content

    pdf_block = f"{PDF_CONTENT_MARKER}\n{combined}"
    if isinstance(content, str):
        base = content.strip()
        return f"{base}\n\n{pdf_block}" if base else pdf_block

    if not isinstance(content, list):
        return pdf_block

    text_parts = []
    non_pdf = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "pdf_url":
            continue
        non_pdf.append(part)
        if part.get("type") == "text":
            text_parts.append(part.get("text") or "")

    merged_text = "\n".join(t.strip() for t in text_parts if t and str(t).strip()).strip()
    if merged_text:
        new_text = f"{merged_text}\n\n{pdf_block}"
    else:
        new_text = pdf_block

    rebuilt = [{"type": "text", "text": new_text}]
    for part in non_pdf:
        if part.get("type") == "text":
            continue
        rebuilt.append(part)
    if len(rebuilt) == 1:
        return rebuilt[0]["text"]
    return rebuilt


def messages_include_pdf_context(messages: list[dict]) -> bool:
    for msg in messages or []:
        if msg.get("role") != "user":
            continue
        if content_already_has_pdf(msg.get("content")):
            return True
    return False


def build_pdf_chat_system_append() -> str:
    return PDF_CHAT_SYSTEM_APPEND


def preprocess_messages_with_pdf(messages: list[dict], *, enabled: bool = True) -> list[dict]:
    if not enabled:
        return messages

    out = []
    for msg in messages:
        if msg.get("role") != "user":
            out.append(msg)
            continue
        content = msg.get("content")
        if not message_has_pdfs(content):
            out.append(msg)
            continue
        if content_already_has_pdf(content):
            stripped = strip_pdf_urls_from_content(content)
            out.append({**msg, "content": stripped} if stripped != content else msg)
            continue

        urls = extract_pdf_urls(content)
        pdf_sections = []
        for idx, url in enumerate(urls, start=1):
            try:
                text = extract_text_from_pdf_data_url(url)
                if len(urls) > 1:
                    pdf_sections.append(f"--- PDF {idx} ---\n{text}")
                else:
                    pdf_sections.append(text)
            except Exception as exc:
                label = f"PDF {idx}" if len(urls) > 1 else "PDF"
                pdf_sections.append(f"[{label}の読み取りに失敗: {exc}]")

        new_content = augment_content_with_pdf(content, pdf_sections)
        new_content = strip_pdf_urls_from_content(new_content)
        out.append({**msg, "content": new_content})
    return out
