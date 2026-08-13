"""Document structure pipeline: scanner OCR + dedicated structuring LLM (separate from chat AI)."""

from __future__ import annotations

import io
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from image_ocr import parse_data_url
from model_registry import get_default_model_id, make_openai_client_for_provider, resolve_chat_model
from ocr_dependencies import ensure_ocr_dependencies

SCANNER_DIR = Path(__file__).resolve().parent / "scanner"
if str(SCANNER_DIR) not in sys.path:
    sys.path.insert(0, str(SCANNER_DIR))

_OCR_ENGINE = None


def _cv2():
    import cv2

    return cv2


def _np():
    import numpy as np

    return np

@lru_cache(maxsize=1)
def _scanner_modules():
    from extract_text import create_ocr_engine, extract_from_page
    from structure_content import structure_worksheet_with_openai, structured_to_markdown

    return create_ocr_engine, extract_from_page, structure_worksheet_with_openai, structured_to_markdown


def _get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        create_ocr_engine, _, _, _ = _scanner_modules()
        _OCR_ENGINE = create_ocr_engine()
    return _OCR_ENGINE


def decode_image_to_bgr(image_bytes: bytes, media_type: str):
    np = _np()
    cv2 = _cv2()
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is not None:
        return image
    from PIL import Image

    pil = Image.open(io.BytesIO(image_bytes))
    if pil.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", pil.size, (255, 255, 255))
        if pil.mode == "P":
            pil = pil.convert("RGBA")
        background.paste(pil, mask=pil.split()[-1] if pil.mode in ("RGBA", "LA") else None)
        pil = background
    elif pil.mode != "RGB":
        pil = pil.convert("RGB")
    rgb = np.array(pil)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def resolve_structure_model(config: dict) -> dict:
    extended = (config or {}).get("extended_models") or {}
    ocr = extended.get("ocr") or {}
    model_id = (ocr.get("structure_model_id") or "").strip() or get_default_model_id(config)
    return resolve_chat_model(model_id, config)


def structure_image_bytes(
    image_bytes: bytes,
    media_type: str,
    *,
    config: dict,
    display_name: str = "attachment",
) -> dict[str, Any]:
    ensure_ocr_dependencies()
    from document_loader import DocumentPage
    _, extract_from_page, structure_worksheet_with_openai, structured_to_markdown = (
        _scanner_modules()
    )

    image = decode_image_to_bgr(image_bytes, media_type)
    if image is None:
        raise ValueError("画像をデコードできません")

    page = DocumentPage(
        source_path=Path(display_name),
        page_number=None,
        stem=Path(display_name).stem or "attachment",
        kind="image",
        image=image,
    )

    ocr = _get_ocr_engine()
    data, _, _, _, _ = extract_from_page(
        ocr,
        page,
        min_score=0.45,
        preprocess=False,
        page_margin_ratio=0.08,
        use_page_filter=True,
    )

    ocr_text = (data.get("text") or "").strip()
    if not ocr_text:
        raise RuntimeError("画像から読み取れる文字がありませんでした")

    resolved = resolve_structure_model(config)
    client, api_key = make_openai_client_for_provider(
        resolved["provider"],
        (config or {}).get("providers"),
    )
    if not api_key:
        raise RuntimeError("文書構造化用の API キーが設定されていません")

    structured = structure_worksheet_with_openai(
        client,
        resolved["api_model"],
        ocr_text,
        data.get("ocr_items"),
    )
    markdown = structured_to_markdown(structured)

    return {
        "ocr_text": ocr_text,
        "structured": structured,
        "markdown": markdown,
        "title": str(structured.get("title") or "").strip(),
        "summary": str(structured.get("summary") or "").strip(),
        "structure_model": resolved["api_model"],
    }


def structure_image_from_data_url(data_url: str, *, config: dict) -> dict[str, Any]:
    parsed = parse_data_url(data_url)
    if not parsed:
        raise ValueError("画像データの形式が不正です")
    image_bytes, media_type = parsed
    return structure_image_bytes(image_bytes, media_type, config=config)
