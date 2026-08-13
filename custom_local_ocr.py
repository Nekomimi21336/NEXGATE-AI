"""Deprecated: use document_structure_service instead."""

from __future__ import annotations

from document_structure_service import structure_image_bytes


def run(image_bytes: bytes, media_type: str) -> str:
    raise NotImplementedError(
        "custom_local_ocr.run は直接呼び出さないでください。"
        "document_structure_service を使用してください。"
    )
