#!/usr/bin/env python3
import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

from document_loader import DocumentPage, load_documents
from page_region import (
    PageRegion,
    detect_page_region,
    draw_page_region,
    extract_page_image,
    is_inside_page_region,
    split_by_page_region,
)
from structure_content import structured_to_markdown, structure_worksheet

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
SECTION_PATTERN = re.compile(
    r"^[回国知図](\d+)[\.．。]?\s*(.+)$"
)
SECTION_INLINE_PATTERN = re.compile(
    r"^(知\d+)(.+)$"
)
QUESTION_PATTERN = re.compile(
    r"^[（(]?([0-9０-９①②③④⑤⑥⑦⑧⑨⑩]+)[）)]?\s*(.+)$"
)
CHOICE_PATTERN = re.compile(
    r"^[（(]([a-zA-Zア-ンぁ-んα-ωイウエオアイウエオ]+)[）)]\s*(.+)$"
)
BLANK_PATTERN = re.compile(r"^[\s\[\]［］()（）〔〕「」『』]+$")
ORDER_STEP_PATTERN = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*(.+)$")
OPTION_PATTERN = re.compile(r"^の\s*(.+)$")

TEXT_CORRECTIONS = (
    (re.compile(r"^国(\d+)"), r"知\1"),
    (re.compile(r"^回(\d+)"), r"知\1"),
    (re.compile(r"^図(\d+)"), r"知\1"),
    (re.compile(r"基本間題"), "基本問題"),
    (re.compile(r"精造"), "構造"),
    (re.compile(r"構遣"), "構造"),
    (re.compile(r"間い"), "問い"),
    (re.compile(r"^（口）"), "（1）"),
    (re.compile(r"^\(口\)"), "(1)"),
    (re.compile(r"^\(口）"), "(1)"),
    (re.compile(r"（日\)"), "（b）"),
    (re.compile(r"\(日\)"), "(b)"),
    (re.compile(r"^\(週"), "(ウ"),
    (re.compile(r"^\(込"), "(オ"),
    (re.compile(r"リードて"), "リード"),
    (re.compile(r"レぼり"), "レボルバー"),
    (re.compile(r"レボルパー"), "レボルバー"),
    (re.compile(r"ステーン"), "ステージ"),
    (re.compile(r"しほり"), "しぼり"),
    (re.compile(r"対物レソズ"), "対物レンズ"),
    (re.compile(r"シP4国盟1"), "p.4例題1"),
    (re.compile(r"つP4国題1"), "p.4例題1"),
    (re.compile(r"路銀の使い方"), "顕微鏡の使い方"),
    (re.compile(r"助仙銘の住方"), "顕微鏡の使い方"),
)


@dataclass
class OcrLine:
    text: str
    score: float
    box: list[list[float]]
    y: float
    x: float


@dataclass
class StructuredBlock:
    kind: str
    text: str = ""
    choices: list[dict[str, str]] = field(default_factory=list)
    blanks: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)


@dataclass
class StructuredSection:
    id: str
    title: str
    blocks: list[StructuredBlock] = field(default_factory=list)


def find_images(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def preprocess_image(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    if max(height, width) < 2000:
        scale = 2000 / max(height, width)
        image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, green_red, blue_yellow = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    lightness = clahe.apply(lightness)
    enhanced = cv2.merge([lightness, green_red, blue_yellow])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def create_ocr_engine() -> RapidOCR:
    return RapidOCR(
        params={
            "Rec.lang_type": LangRec.JAPAN,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV4,
        }
    )


def normalize_text(text: str) -> str:
    normalized = text.strip()
    for pattern, replacement in TEXT_CORRECTIONS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def to_ocr_lines(result: Any) -> list[OcrLine]:
    if not result or not result.txts:
        return []

    lines: list[OcrLine] = []
    for box, text, score in zip(result.boxes, result.txts, result.scores):
        ys = [float(point[1]) for point in box]
        xs = [float(point[0]) for point in box]
        lines.append(
            OcrLine(
                text=normalize_text(str(text)),
                score=float(score),
                box=box.tolist(),
                y=min(ys),
                x=min(xs),
            )
        )

    lines.sort(key=lambda line: (line.y, line.x))
    return lines


def box_right(box: list[list[float]]) -> float:
    return max(point[0] for point in box)


def box_left(box: list[list[float]]) -> float:
    return min(point[0] for point in box)


def merge_line_items(
    items: list[OcrLine],
    y_threshold: float = 16.0,
    x_gap_threshold: float = 70.0,
) -> list[str]:
    if not items:
        return []

    grouped: list[list[OcrLine]] = []
    current_group: list[OcrLine] = []
    current_y: float | None = None

    for item in items:
        if current_y is None or abs(item.y - current_y) <= y_threshold:
            current_group.append(item)
            current_y = item.y if current_y is None else (current_y + item.y) / 2
            continue

        grouped.append(current_group)
        current_group = [item]
        current_y = item.y

    if current_group:
        grouped.append(current_group)

    merged_lines: list[str] = []
    for group in grouped:
        group.sort(key=lambda line: line.x)
        current_text = group[0].text
        previous_right = box_right(group[0].box)

        for item in group[1:]:
            if box_left(item.box) - previous_right > x_gap_threshold:
                merged_lines.append(current_text.strip())
                current_text = item.text
            else:
                current_text += item.text
            previous_right = box_right(item.box)

        merged_lines.append(current_text.strip())

    return [line for line in merged_lines if line]


def classify_line(text: str) -> StructuredBlock:
    if BLANK_PATTERN.fullmatch(text):
        return StructuredBlock(kind="blank", text=text, blanks=[text])

    section_match = SECTION_PATTERN.match(text)
    if section_match:
        section_id = section_match.group(1)
        title = section_match.group(2).strip()
        return StructuredBlock(kind="section", text=f"知{section_id}. {title}")

    section_inline_match = SECTION_INLINE_PATTERN.match(text)
    if section_inline_match:
        section_label = section_inline_match.group(1)
        title = section_inline_match.group(2).strip()
        section_id = re.search(r"\d+", section_label)
        return StructuredBlock(
            kind="section",
            text=f"知{section_id.group()}. {title}" if section_id else text,
        )

    question_match = QUESTION_PATTERN.match(text)
    if question_match:
        return StructuredBlock(
            kind="question",
            text=f"({question_match.group(1)}) {question_match.group(2).strip()}",
        )

    choice_match = CHOICE_PATTERN.match(text)
    if choice_match:
        return StructuredBlock(
            kind="choice",
            text=text,
            choices=[
                {
                    "label": choice_match.group(1),
                    "text": choice_match.group(2).strip(),
                }
            ],
        )

    order_match = ORDER_STEP_PATTERN.match(text)
    if order_match:
        return StructuredBlock(kind="step", text=text, steps=[order_match.group(1).strip()])

    option_match = OPTION_PATTERN.match(text)
    if option_match:
        return StructuredBlock(
            kind="option",
            text=text,
            choices=[{"label": "", "text": option_match.group(1).strip()}],
        )

    if "選べ" in text or "答えよ" in text or "並べ" in text:
        return StructuredBlock(kind="instruction", text=text)

    return StructuredBlock(kind="text", text=text)


def build_sections(lines: list[str]) -> list[StructuredSection]:
    sections: list[StructuredSection] = []
    current_section: StructuredSection | None = None

    for line in lines:
        block = classify_line(line)

        if block.kind == "section":
            section_id = re.search(r"知(\d+)", block.text)
            current_section = StructuredSection(
                id=section_id.group(1) if section_id else "",
                title=block.text,
            )
            sections.append(current_section)
            continue

        if current_section is None:
            current_section = StructuredSection(id="", title="")
            sections.append(current_section)

        current_section.blocks.append(block)

    return sections


def prepare_image(image: np.ndarray, preprocess: bool) -> np.ndarray:
    if preprocess:
        return preprocess_image(image)
    return image


def build_ocr_item_dict(index: int, line: OcrLine, in_page: bool) -> dict[str, Any]:
    return {
        "index": index,
        "text": line.text,
        "score": round(line.score, 4),
        "box": line.box,
        "center": [
            round(sum(point[0] for point in line.box) / 4, 1),
            round(sum(point[1] for point in line.box) / 4, 1),
        ],
        "in_page": bool(in_page),
    }


def ocr_on_image(
    ocr: RapidOCR,
    image: np.ndarray,
    min_score: float,
    preprocess: bool,
) -> tuple[str, list[OcrLine], Any]:
    prepared = prepare_image(image, preprocess)
    result = ocr(prepared)
    ocr_lines = [line for line in to_ocr_lines(result) if line.score >= min_score]
    merged_lines = merge_line_items(ocr_lines)
    return "\n".join(merged_lines), ocr_lines, result


def extract_from_image_page(
    ocr: RapidOCR,
    page: DocumentPage,
    min_score: float,
    preprocess: bool,
    page_margin_ratio: float,
    use_page_filter: bool,
) -> tuple[dict[str, Any], Any, list[OcrLine], np.ndarray | None, PageRegion | None]:
    if page.image is None:
        raise ValueError(f"画像データがありません: {page.display_name}")

    image = prepare_image(page.image, preprocess)
    result = ocr(image)
    ocr_lines = [line for line in to_ocr_lines(result) if line.score >= min_score]

    page_region = detect_page_region(
        image,
        ocr_lines,
        margin_ratio=page_margin_ratio,
    )
    in_page_lines, out_page_lines = split_by_page_region(ocr_lines, page_region)
    active_lines = in_page_lines if use_page_filter and page_region else ocr_lines

    merged_lines = merge_line_items(active_lines)
    sections = build_sections(merged_lines)
    excluded_lines = merge_line_items(out_page_lines) if out_page_lines else []

    page_region_dict = page_region.to_dict() if page_region else None
    if page_region_dict is not None:
        page_region_dict["excluded_count"] = len(out_page_lines)
        page_region_dict["included_count"] = len(in_page_lines)

    data = {
        "file": page.display_name,
        "source": {
            "path": str(page.source_path),
            "page": page.page_number,
            "format": page.source_path.suffix.lower().lstrip("."),
            "kind": "image",
            "extraction": "ocr",
        },
        "text": "\n".join(merged_lines),
        "excluded_text": "\n".join(excluded_lines),
        "line_count": len(merged_lines),
        "sections": [asdict(section) for section in sections],
        "page_region": page_region_dict,
        "ocr_items": [
            build_ocr_item_dict(
                index,
                line,
                page_region is None
                or is_inside_page_region(line.box, page_region),
            )
            for index, line in enumerate(ocr_lines)
        ],
    }
    return data, result, ocr_lines, image, page_region


def build_pdf_combined_text(
    native_text: str,
    embedded_ocr_texts: list[str],
    scanned_ocr_text: str,
) -> str:
    parts: list[str] = []
    if native_text.strip():
        parts.append(native_text.strip())
    for index, text in enumerate(embedded_ocr_texts, start=1):
        cleaned = text.strip()
        if cleaned:
            parts.append(f"[画像OCR {index}]\n{cleaned}")
    if scanned_ocr_text.strip():
        parts.append(scanned_ocr_text.strip())
    return "\n\n".join(parts)


def extract_from_pdf_page(
    ocr: RapidOCR,
    page: DocumentPage,
    min_score: float,
    preprocess: bool,
    page_margin_ratio: float,
    use_page_filter: bool,
) -> tuple[dict[str, Any], Any, list[OcrLine], np.ndarray | None, PageRegion | None]:
    embedded_ocr_texts: list[str] = []
    embedded_ocr_details: list[dict[str, Any]] = []
    all_ocr_lines: list[OcrLine] = []
    all_ocr_items: list[dict[str, Any]] = []
    result: Any = None
    image: np.ndarray | None = None
    page_region: PageRegion | None = None
    scanned_ocr_text = ""

    for index, embedded_image in enumerate(page.embedded_images, start=1):
        text, ocr_lines, ocr_result = ocr_on_image(
            ocr,
            embedded_image,
            min_score,
            preprocess,
        )
        embedded_ocr_texts.append(text)
        embedded_ocr_details.append(
            {
                "index": index,
                "text": text,
                "line_count": len([line for line in text.splitlines() if line.strip()]),
            }
        )
        item_offset = len(all_ocr_items)
        all_ocr_lines.extend(ocr_lines)
        all_ocr_items.extend(
            build_ocr_item_dict(item_offset + item_index, line, True)
            for item_index, line in enumerate(ocr_lines)
        )
        result = ocr_result

    if page.image is not None:
        scanned_data, result, ocr_lines, image, page_region = extract_from_image_page(
            ocr,
            page,
            min_score,
            preprocess,
            page_margin_ratio,
            use_page_filter,
        )
        scanned_ocr_text = scanned_data["text"]
        item_offset = len(all_ocr_items)
        all_ocr_lines.extend(ocr_lines)
        all_ocr_items.extend(
            {
                **item,
                "index": item_offset + item["index"],
                "source": "scanned_page",
            }
            for item in scanned_data.get("ocr_items", [])
        )

    combined_text = build_pdf_combined_text(
        page.native_text,
        embedded_ocr_texts,
        scanned_ocr_text,
    )

    has_native = bool(page.native_text.strip())
    has_embedded_ocr = any(text.strip() for text in embedded_ocr_texts)
    has_scanned = bool(scanned_ocr_text.strip())

    if has_scanned and page.image is not None:
        extraction_mode = "scanned"
    elif has_native and has_embedded_ocr:
        extraction_mode = "text+image_ocr"
    elif has_embedded_ocr:
        extraction_mode = "image_ocr"
    elif has_native:
        extraction_mode = "text"
    else:
        extraction_mode = "empty"

    sections = build_sections(
        [line for line in combined_text.splitlines() if line.strip()]
    )

    data = {
        "file": page.display_name,
        "source": {
            "path": str(page.source_path),
            "page": page.page_number,
            "format": "pdf",
            "kind": "pdf",
            "extraction": extraction_mode,
        },
        "pdf_native_text": page.native_text,
        "embedded_image_ocr": embedded_ocr_details,
        "scanned_ocr_text": scanned_ocr_text,
        "text": combined_text,
        "excluded_text": "",
        "line_count": len([line for line in combined_text.splitlines() if line.strip()]),
        "sections": [asdict(section) for section in sections],
        "page_region": page_region.to_dict() if page_region else None,
        "ocr_items": all_ocr_items,
    }

    return data, result, all_ocr_lines, image, page_region


def extract_from_page(
    ocr: RapidOCR,
    page: DocumentPage,
    min_score: float,
    preprocess: bool,
    page_margin_ratio: float,
    use_page_filter: bool,
) -> tuple[dict[str, Any], Any, list[OcrLine], np.ndarray | None, PageRegion | None]:
    if page.kind == "pdf":
        return extract_from_pdf_page(
            ocr,
            page,
            min_score,
            preprocess,
            page_margin_ratio,
            use_page_filter,
        )
    return extract_from_image_page(
        ocr,
        page,
        min_score,
        preprocess,
        page_margin_ratio,
        use_page_filter,
    )


def save_coordinate_visualization(
    image: np.ndarray,
    ocr_lines: list[OcrLine],
    output_path: Path,
    page_region: Any | None = None,
) -> None:
    in_page_lines, out_page_lines = split_by_page_region(ocr_lines, page_region)

    if page_region is not None:
        overlay = draw_page_region(
            image,
            page_region,
            in_page_lines,
            out_page_lines,
        )
    else:
        overlay = image.copy()

    for index, line in enumerate(ocr_lines):
        if page_region is not None and not is_inside_page_region(line.box, page_region):
            continue

        box = np.array(line.box, dtype=np.int32)
        cv2.polylines(overlay, [box], True, (0, 180, 0), 2)

        label_x = int(line.x)
        label_y = max(int(line.y) - 6, 16)
        cv2.putText(
            overlay,
            f"#{index}",
            (label_x, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", overlay)[1].tofile(str(output_path))


def save_page_region_visualization(
    image: np.ndarray,
    ocr_lines: list[OcrLine],
    page_region: Any,
    output_path: Path,
) -> None:
    in_page_lines, out_page_lines = split_by_page_region(ocr_lines, page_region)
    overlay = draw_page_region(
        image,
        page_region,
        in_page_lines,
        out_page_lines,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", overlay)[1].tofile(str(output_path))


def save_visualization(
    result: Any,
    image: np.ndarray | None,
    image_stem: str,
    ocr_lines: list[OcrLine],
    output_dir: Path,
    page_region: PageRegion | None,
) -> tuple[Path | None, Path | None, Path | None]:
    if image is None or not ocr_lines:
        return None, None, None

    output_path = output_dir / f"{image_stem}_output.png"
    save_coordinate_visualization(image, ocr_lines, output_path, page_region)

    page_region_path: Path | None = None
    if page_region is not None:
        page_region_path = output_dir / f"{image_stem}_page_region.png"
        save_page_region_visualization(image, ocr_lines, page_region, page_region_path)

    vis_path: Path | None = None
    if result and result.boxes is not None and len(result) > 0:
        vis_path = output_dir / f"{image_stem}_vis.png"
        result.vis(save_path=str(vis_path))

    return output_path, vis_path, page_region_path


def save_outputs(
    output_dir: Path,
    stem: str,
    data: dict[str, Any],
    result: Any,
    ocr_lines: list[OcrLine],
    image: np.ndarray | None,
    page_region: PageRegion | None,
    save_vis: bool,
    use_structure: bool,
    api_token: str | None,
    api_model: str | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    text_path = output_dir / f"{stem}.txt"
    text_path.write_text(data["text"], encoding="utf-8")

    if data.get("excluded_text"):
        excluded_path = output_dir / f"{stem}_excluded.txt"
        excluded_path.write_text(data["excluded_text"], encoding="utf-8")

    if save_vis and image is not None and ocr_lines:
        output_png, vis_png, page_region_png = save_visualization(
            result,
            image,
            stem,
            ocr_lines,
            output_dir,
            page_region,
        )
        if output_png is not None:
            data["visualization"] = {
                "output_png": output_png.name,
                "vis_png": vis_png.name if vis_png else None,
                "page_region_png": page_region_png.name if page_region_png else None,
            }

    if page_region is not None and image is not None:
        page_image = extract_page_image(image, page_region)
        page_path = output_dir / f"{stem}_page.jpg"
        cv2.imencode(".jpg", page_image)[1].tofile(str(page_path))
        if data.get("visualization") is None:
            data["visualization"] = {}
        data["visualization"]["page_jpg"] = page_path.name

    if use_structure:
        try:
            structured = structure_worksheet(
                data["text"],
                data.get("ocr_items"),
                api_token=api_token,
                model=api_model,
            )
            data["structured"] = structured
            structured_json_path = output_dir / f"{stem}_structured.json"
            structured_json_path.write_text(
                json.dumps(structured, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            structured_md_path = output_dir / f"{stem}_structured.md"
            structured_md_path.write_text(
                structured_to_markdown(structured),
                encoding="utf-8",
            )
        except (ValueError, RuntimeError, json.JSONDecodeError) as error:
            print(f"構造化に失敗しました: {error}", file=sys.stderr)
            data["structured_error"] = str(error)

    json_path = output_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PDF・画像から日本語OCRで文字を抽出します。"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=".",
        type=Path,
        help="入力ファイルまたはフォルダ（省略時はカレントディレクトリ）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="結果を保存するフォルダ（省略時は input/output）",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.45,
        help="信頼度のしきい値（デフォルト: 0.45）",
    )
    parser.add_argument(
        "--preprocess",
        action="store_true",
        help="コントラスト補正と拡大の前処理を有効化する",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="ファイルに保存せず標準出力へ出力する",
    )
    parser.add_argument(
        "--no-vis",
        action="store_true",
        help="座標付き画像の出力を無効化する",
    )
    parser.add_argument(
        "--page-margin",
        type=float,
        default=0.08,
        help="ページ幅に対する左右余白の比率（デフォルト: 0.08）",
    )
    parser.add_argument(
        "--no-page-filter",
        action="store_true",
        help="ページ範囲によるテキスト除外を無効化する",
    )
    parser.add_argument(
        "--structure",
        action="store_true",
        help="AIでOCR結果を構造化する",
    )
    parser.add_argument(
        "--api-token",
        type=str,
        default=None,
        help="Nexgate APIトークン（省略時は環境変数 NEXGATE_API_TOKEN）",
    )
    parser.add_argument(
        "--api-model",
        type=str,
        default=None,
        help="使用するモデルID（省略時は nexgate-base）",
    )
    parser.add_argument(
        "--pdf-dpi",
        type=int,
        default=200,
        help="スキャンPDFのページレンダリング解像度（デフォルト: 200）",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    try:
        pages = load_documents(input_path, pdf_dpi=args.pdf_dpi)
    except (FileNotFoundError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)

    if input_path.is_file():
        output_dir = (args.output or input_path.parent / "output").resolve()
    else:
        output_dir = (args.output or input_path / "output").resolve()

    ocr = create_ocr_engine()
    preprocess = args.preprocess

    for index, page in enumerate(pages):
        print(f"処理中: {page.display_name}", file=sys.stderr)
        data, result, ocr_lines, image, page_region = extract_from_page(
            ocr,
            page,
            args.min_score,
            preprocess,
            args.page_margin,
            use_page_filter=not args.no_page_filter,
        )

        if args.stdout:
            print(f"=== {page.display_name} ===")
            print(data["text"])
            if data.get("excluded_text"):
                print("\n--- excluded ---")
                print(data["excluded_text"])
            if index != len(pages) - 1:
                print()
            continue

        save_outputs(
            output_dir,
            page.stem,
            data,
            result,
            ocr_lines,
            image,
            page_region,
            save_vis=not args.no_vis,
            use_structure=args.structure,
            api_token=args.api_token,
            api_model=args.api_model,
        )
        print(f"保存しました: {output_dir / page.stem}.txt", file=sys.stderr)
        print(f"保存しました: {output_dir / page.stem}.json", file=sys.stderr)
        if data.get("excluded_text"):
            print(
                f"保存しました: {output_dir / f'{page.stem}_excluded.txt'}",
                file=sys.stderr,
            )
        if not args.no_vis and image is not None and ocr_lines:
            print(
                f"保存しました: {output_dir / f'{page.stem}_output.png'}",
                file=sys.stderr,
            )
            page_region_png = output_dir / f"{page.stem}_page_region.png"
            if page_region_png.exists():
                print(f"保存しました: {page_region_png}", file=sys.stderr)
        if args.structure:
            structured_json = output_dir / f"{page.stem}_structured.json"
            if structured_json.exists():
                print(f"保存しました: {structured_json}", file=sys.stderr)
            structured_md = output_dir / f"{page.stem}_structured.md"
            if structured_md.exists():
                print(f"保存しました: {structured_md}", file=sys.stderr)
        if page_region is not None:
            page_path = output_dir / f"{page.stem}_page.jpg"
            if page_path.exists():
                print(f"保存しました: {page_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
