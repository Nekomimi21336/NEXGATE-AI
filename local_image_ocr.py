"""Local (non-AI) image text extraction for chat preprocessing."""

from __future__ import annotations

from image_ocr import OCR_NO_TEXT_PLACEHOLDER, parse_data_url, resize_image, sanitize_ocr_transcript


def extract_text_from_image_bytes(image_bytes: bytes, media_type: str) -> str:
    from custom_local_ocr import run

    resized, out_type = resize_image(image_bytes)
    raw = run(resized, out_type)
    text = sanitize_ocr_transcript(str(raw or "").strip())
    return text or OCR_NO_TEXT_PLACEHOLDER


def ocr_image_from_data_url_local(data_url: str) -> str:
    parsed = parse_data_url(data_url)
    if not parsed:
        raise ValueError("画像データの形式が不正です")
    image_bytes, media_type = parsed
    return extract_text_from_image_bytes(image_bytes, media_type)
