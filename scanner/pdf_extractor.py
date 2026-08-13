from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np

MIN_EMBEDDED_IMAGE_SIZE = 80


def pixmap_to_bgr(pixmap: fitz.Pixmap) -> np.ndarray:
    if pixmap.n == 4:
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, 4
        )
        return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
    if pixmap.n == 1:
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width
        )
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def bytes_to_bgr(image_bytes: bytes) -> np.ndarray | None:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    return image


def extract_page_text(page: fitz.Page) -> str:
    blocks = page.get_text("blocks")
    text_blocks: list[tuple[float, float, str]] = []
    for block in blocks:
        if len(block) < 7 or block[6] != 0:
            continue
        text = str(block[4]).strip()
        if text:
            text_blocks.append((float(block[1]), float(block[0]), text))
    text_blocks.sort(key=lambda item: (item[0], item[1]))
    return "\n".join(text for _, _, text in text_blocks)


def is_large_enough(image: np.ndarray) -> bool:
    height, width = image.shape[:2]
    return min(height, width) >= MIN_EMBEDDED_IMAGE_SIZE


def extract_embedded_images(document: fitz.Document, page: fitz.Page) -> list[np.ndarray]:
    images: list[np.ndarray] = []
    seen_xrefs: set[int] = set()

    for image_info in page.get_images(full=True):
        xref = int(image_info[0])
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        try:
            extracted = document.extract_image(xref)
        except (ValueError, RuntimeError):
            continue

        image = bytes_to_bgr(extracted["image"])
        if image is None or not is_large_enough(image):
            continue
        images.append(image)

    return images


def render_page(document: fitz.Document, page: fitz.Page, dpi: int) -> np.ndarray:
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    return pixmap_to_bgr(pixmap)


def needs_scanned_fallback(native_text: str, embedded_images: list[np.ndarray]) -> bool:
    if embedded_images:
        return False
    if native_text.strip():
        return False
    return True


def load_pdf_page_contents(
    pdf_path: Path,
    dpi: int = 200,
) -> list[dict[str, object]]:
    document = fitz.open(pdf_path)
    pages: list[dict[str, object]] = []
    try:
        for index, page in enumerate(document, start=1):
            native_text = extract_page_text(page)
            embedded_images = extract_embedded_images(document, page)
            use_fallback = needs_scanned_fallback(native_text, embedded_images)
            fallback_image = (
                render_page(document, page, dpi) if use_fallback else None
            )
            pages.append(
                {
                    "page_number": index,
                    "native_text": native_text,
                    "embedded_images": embedded_images,
                    "fallback_image": fallback_image,
                    "mode": "scanned" if use_fallback else "text",
                }
            )
    finally:
        document.close()
    return pages
