from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from pdf_extractor import load_pdf_page_contents

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS


@dataclass
class DocumentPage:
    source_path: Path
    page_number: int | None
    stem: str
    kind: str
    image: np.ndarray | None = None
    native_text: str = ""
    embedded_images: list[np.ndarray] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if self.page_number is None:
            return self.source_path.name
        return f"{self.source_path.name} (p.{self.page_number})"


def is_supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def page_stem(source_path: Path, page_number: int | None) -> str:
    if page_number is None:
        return source_path.stem
    return f"{source_path.stem}_p{page_number:03d}"


def load_image_page(image_path: Path) -> DocumentPage:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"画像を読み込めません: {image_path}")
    return DocumentPage(
        source_path=image_path,
        page_number=None,
        stem=page_stem(image_path, None),
        kind="image",
        image=image,
    )


def load_pdf_pages(pdf_path: Path, dpi: int = 200) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    for content in load_pdf_page_contents(pdf_path, dpi=dpi):
        page_number = int(content["page_number"])
        pages.append(
            DocumentPage(
                source_path=pdf_path,
                page_number=page_number,
                stem=page_stem(pdf_path, page_number),
                kind="pdf",
                image=content["fallback_image"],
                native_text=str(content["native_text"]),
                embedded_images=list(content["embedded_images"]),
            )
        )
    return pages


def load_document(path: Path, pdf_dpi: int = 200) -> list[DocumentPage]:
    suffix = path.suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return load_pdf_pages(path, dpi=pdf_dpi)
    if suffix in IMAGE_EXTENSIONS:
        return [load_image_page(path)]
    raise ValueError(f"未対応の形式です: {path}")


def collect_input_paths(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if not is_supported_file(input_path):
            raise ValueError(f"未対応の形式です: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"入力が見つかりません: {input_path}")

    files = sorted(
        path for path in input_path.iterdir() if is_supported_file(path)
    )
    if not files:
        raise FileNotFoundError(
            f"対応ファイルが見つかりません（pdf/jpg/jpeg/png）: {input_path}"
        )
    return files


def load_documents(input_path: Path, pdf_dpi: int = 200) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    for path in collect_input_paths(input_path):
        pages.extend(load_document(path, pdf_dpi=pdf_dpi))
    return pages
