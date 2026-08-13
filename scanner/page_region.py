import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass
class BoxGeometry:
    width: float
    height: float
    angle: float
    center: np.ndarray


@dataclass
class PageRegion:
    angle_deg: float
    angle_rad: float
    max_line_width: float
    margin_x: float
    margin_y: float
    left_bound: float
    right_bound: float
    top_bound: float
    bottom_bound: float
    origin: tuple[float, float]
    corners: list[list[float]]
    reference_index: int | None
    horizontal_line_count: int
    detection_method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "angle_deg": round(self.angle_deg, 2),
            "max_line_width": round(self.max_line_width, 1),
            "margin_x": round(self.margin_x, 1),
            "margin_y": round(self.margin_y, 1),
            "left_bound": round(self.left_bound, 1),
            "right_bound": round(self.right_bound, 1),
            "top_bound": round(self.top_bound, 1),
            "bottom_bound": round(self.bottom_bound, 1),
            "origin": [round(self.origin[0], 1), round(self.origin[1], 1)],
            "corners": [
                [round(point[0], 1), round(point[1], 1)] for point in self.corners
            ],
            "reference_index": self.reference_index,
            "horizontal_line_count": self.horizontal_line_count,
            "detection_method": self.detection_method,
        }


def box_geometry(box: list[list[float]]) -> BoxGeometry:
    points = np.array(box, dtype=np.float64)
    top_edge = points[1] - points[0]
    bottom_edge = points[2] - points[3]
    left_edge = points[3] - points[0]
    right_edge = points[2] - points[1]

    top_len = float(np.linalg.norm(top_edge))
    bottom_len = float(np.linalg.norm(bottom_edge))
    left_len = float(np.linalg.norm(left_edge))
    right_len = float(np.linalg.norm(right_edge))

    width = (top_len + bottom_len) / 2
    height = (left_len + right_len) / 2

    if width >= height:
        direction = (top_edge / top_len) if top_len > 0 else np.array([1.0, 0.0])
    else:
        direction = (right_edge / right_len) if right_len > 0 else np.array([0.0, 1.0])

    angle = math.atan2(float(direction[1]), float(direction[0]))
    center = points.mean(axis=0)
    return BoxGeometry(width=width, height=height, angle=angle, center=center)


def align_angle(angle: float, reference: float) -> float:
    aligned = angle
    while aligned - reference > math.pi / 2:
        aligned -= math.pi
    while aligned - reference < -math.pi / 2:
        aligned += math.pi
    return aligned


def weighted_angle(angles: list[float], weights: list[float]) -> float:
    sin_sum = sum(math.sin(angle) * weight for angle, weight in zip(angles, weights))
    cos_sum = sum(math.cos(angle) * weight for angle, weight in zip(angles, weights))
    if abs(sin_sum) < 1e-9 and abs(cos_sum) < 1e-9:
        return angles[0] if angles else 0.0
    return math.atan2(sin_sum, cos_sum)


def to_document_coords(
    point: np.ndarray,
    origin: np.ndarray,
    angle: float,
) -> np.ndarray:
    relative = point - origin
    cos_a = math.cos(-angle)
    sin_a = math.sin(-angle)
    x = relative[0] * cos_a - relative[1] * sin_a
    y = relative[0] * sin_a + relative[1] * cos_a
    return np.array([x, y], dtype=np.float64)


def from_document_coords(
    point: np.ndarray,
    origin: np.ndarray,
    angle: float,
) -> np.ndarray:
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    x = point[0] * cos_a - point[1] * sin_a
    y = point[0] * sin_a + point[1] * cos_a
    return origin + np.array([x, y], dtype=np.float64)


def order_corners(points: np.ndarray) -> np.ndarray:
    corners = np.array(points, dtype=np.float64).reshape(-1, 2)
    if len(corners) != 4:
        rect = cv2.minAreaRect(corners.astype(np.float32))
        corners = cv2.boxPoints(rect)

    ordered = np.zeros((4, 2), dtype=np.float64)
    sums = corners.sum(axis=1)
    diffs = np.diff(corners, axis=1).reshape(-1)
    ordered[0] = corners[np.argmin(sums)]
    ordered[2] = corners[np.argmax(sums)]
    ordered[1] = corners[np.argmin(diffs)]
    ordered[3] = corners[np.argmax(diffs)]
    return ordered


def clip_corners(corners: np.ndarray, image_width: int, image_height: int) -> np.ndarray:
    clipped = corners.copy()
    clipped[:, 0] = np.clip(clipped[:, 0], 0, image_width - 1)
    clipped[:, 1] = np.clip(clipped[:, 1], 0, image_height - 1)
    return clipped


def angle_from_corners(corners: np.ndarray) -> float:
    top_edge = corners[1] - corners[0]
    return math.atan2(float(top_edge[1]), float(top_edge[0]))


def corners_to_bounds(
    corners: np.ndarray,
    angle: float,
) -> tuple[np.ndarray, float, float, float, float, float, float]:
    origin = corners.mean(axis=0)
    doc_corners = [to_document_coords(point, origin, angle) for point in corners]
    xs = [point[0] for point in doc_corners]
    ys = [point[1] for point in doc_corners]
    left = float(min(xs))
    right = float(max(xs))
    top = float(min(ys))
    bottom = float(max(ys))
    width = right - left
    return origin, left, right, top, bottom, width, bottom - top


def build_corners(
    origin: np.ndarray,
    angle: float,
    left: float,
    right: float,
    top: float,
    bottom: float,
) -> list[list[float]]:
    doc_corners = [
        np.array([left, top], dtype=np.float64),
        np.array([right, top], dtype=np.float64),
        np.array([right, bottom], dtype=np.float64),
        np.array([left, bottom], dtype=np.float64),
    ]
    return [
        [float(point[0]), float(point[1])]
        for point in (from_document_coords(corner, origin, angle) for corner in doc_corners)
    ]


def is_horizontal_text(
    geometry: BoxGeometry,
    text: str,
    min_width_ratio: float,
    min_chars: int,
) -> bool:
    if geometry.height <= 0:
        return False
    if len(text.strip()) < min_chars:
        return False
    return geometry.width / geometry.height >= min_width_ratio


def collect_horizontal_lines(
    ocr_items: list[Any],
    image_width: int,
    min_width_ratio: float,
    min_chars: int,
) -> list[tuple[int, BoxGeometry, str]]:
    horizontal_lines: list[tuple[int, BoxGeometry, str]] = []
    for index, item in enumerate(ocr_items):
        geometry = box_geometry(item.box)
        if is_horizontal_text(geometry, item.text, min_width_ratio, min_chars):
            horizontal_lines.append((index, geometry, item.text))

    if horizontal_lines:
        return horizontal_lines

    for index, item in enumerate(ocr_items):
        geometry = box_geometry(item.box)
        if geometry.width >= image_width * 0.12 and len(item.text.strip()) >= 2:
            horizontal_lines.append((index, geometry, item.text))
    return horizontal_lines


def estimate_document_angle(
    horizontal_lines: list[tuple[int, BoxGeometry, str]],
) -> tuple[float, int]:
    ranked = sorted(horizontal_lines, key=lambda item: item[1].width, reverse=True)
    reference_index, reference_geometry, _ = ranked[0]
    reference_angle = reference_geometry.angle

    candidate_lines = ranked[: max(5, len(ranked) // 4)]
    angles = [align_angle(geometry.angle, reference_angle) for _, geometry, _ in candidate_lines]
    weights = [geometry.width for _, geometry, _ in candidate_lines]
    return weighted_angle(angles, weights), reference_index


def detect_page_mask(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness = cv2.GaussianBlur(lab[:, :, 0], (7, 7), 0)
    _, mask = cv2.threshold(lightness, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=4)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    return mask


def detect_corners_from_color(image: np.ndarray) -> np.ndarray | None:
    mask = detect_page_mask(image)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < image.shape[0] * image.shape[1] * 0.15:
        return None

    epsilon = 0.015 * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
    if len(approx) < 4:
        rect = cv2.minAreaRect(contour)
        approx = cv2.boxPoints(rect)
    return order_corners(approx)


def sample_luminance(image: np.ndarray, point: np.ndarray) -> float:
    x = int(np.clip(point[0], 0, image.shape[1] - 1))
    y = int(np.clip(point[1], 0, image.shape[0] - 1))
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    return float(lab[y, x, 0])


def refine_vertical_edge(
    image: np.ndarray,
    corners: np.ndarray,
    angle: float,
    side: str,
    steps: int = 40,
) -> float:
    origin, left, right, top, bottom, width, _ = corners_to_bounds(corners, angle)
    span = bottom - top
    doc_y_values = np.linspace(top + span * 0.05, bottom - span * 0.05, steps)
    edge_positions: list[float] = []

    search_direction = -1.0 if side == "right" else 1.0
    start_x = right if side == "right" else left
    search_distance = width * 0.12

    for doc_y in doc_y_values:
        best_x = start_x
        for offset in np.linspace(0, search_distance, 24):
            candidate_x = start_x + search_direction * offset
            point = from_document_coords(np.array([candidate_x, doc_y]), origin, angle)
            if not is_point_in_image(point, image.shape[1], image.shape[0]):
                break
            luma = sample_luminance(image, point)
            hsv = sample_hsv(image, point)
            if side == "right":
                if luma < 150 or hsv[1] > 80:
                    best_x = candidate_x - search_direction * (search_distance / 24) * 2
                    break
            elif luma < 120:
                best_x = candidate_x
                break
        edge_positions.append(best_x)

    return float(np.median(edge_positions))


def is_point_in_image(point: np.ndarray, width: int, height: int) -> bool:
    return 0 <= point[0] < width and 0 <= point[1] < height


def sample_hsv(image: np.ndarray, point: np.ndarray) -> tuple[float, float, float]:
    x = int(np.clip(point[0], 0, image.shape[1] - 1))
    y = int(np.clip(point[1], 0, image.shape[0] - 1))
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    value = hsv[y, x]
    return float(value[0]), float(value[1]), float(value[2])


def refine_corners_with_color(
    image: np.ndarray,
    corners: np.ndarray,
    angle: float,
) -> np.ndarray:
    origin, left, right, top, bottom, width, height = corners_to_bounds(corners, angle)
    refined_right = refine_vertical_edge(image, corners, angle, "right")
    refined_left = refine_vertical_edge(image, corners, angle, "left")

    refined_right = min(refined_right, right)
    refined_left = max(refined_left, left)
    if refined_right - refined_left < width * 0.5:
        refined_right = right
        refined_left = left

    margin_y = max(height * 0.015, 10.0)
    refined_corners = build_corners(
        origin,
        angle,
        refined_left,
        refined_right,
        top + margin_y,
        bottom - margin_y,
    )
    return order_corners(np.array(refined_corners, dtype=np.float64))


def detect_page_region(
    image: np.ndarray,
    ocr_items: list[Any],
    margin_ratio: float = 0.08,
    min_width_ratio: float = 2.5,
    min_chars: int = 4,
) -> PageRegion | None:
    image_height, image_width = image.shape[:2]
    horizontal_lines = collect_horizontal_lines(
        ocr_items,
        image_width,
        min_width_ratio,
        min_chars,
    )

    color_corners = detect_corners_from_color(image)
    if color_corners is None and not horizontal_lines:
        return None

    if horizontal_lines:
        ocr_angle, reference_index = estimate_document_angle(horizontal_lines)
    else:
        ocr_angle, reference_index = 0.0, None

    if color_corners is not None:
        color_angle = angle_from_corners(color_corners)
        angle = weighted_angle(
            [align_angle(color_angle, ocr_angle), ocr_angle],
            [2.0, 1.0],
        ) if horizontal_lines else color_angle
        corners = order_corners(color_corners)
        corners = refine_corners_with_color(image, corners, angle)
        method = "color+ocr"
    else:
        angle = ocr_angle
        origin = np.median(
            np.array([geometry.center for _, geometry, _ in horizontal_lines], dtype=np.float64),
            axis=0,
        )
        ranked_widths = sorted(
            ((index, geometry.width) for index, geometry, _ in horizontal_lines),
            key=lambda item: item[1],
            reverse=True,
        )
        max_line_width = float(np.median([width for _, width in ranked_widths[:3]]))
        margin_x = max(max_line_width * margin_ratio, 16.0)
        margin_y = max(max_line_width * margin_ratio * 2, 20.0)
        line_centers_x = [
            float(to_document_coords(geometry.center, origin, angle)[0])
            for _, geometry, _ in horizontal_lines
        ]
        page_center_x = float(np.median(line_centers_x))
        left_bound = page_center_x - max_line_width / 2 - margin_x
        right_bound = page_center_x + max_line_width / 2 + margin_x
        tops: list[float] = []
        bottoms: list[float] = []
        for item in ocr_items:
            points = [to_document_coords(np.array(point, dtype=np.float64), origin, angle) for point in item.box]
            tops.append(min(point[1] for point in points))
            bottoms.append(max(point[1] for point in points))
        top_bound = float(np.percentile(tops, 2)) - margin_y
        bottom_bound = float(np.percentile(bottoms, 98)) + margin_y
        corners = np.array(
            build_corners(origin, angle, left_bound, right_bound, top_bound, bottom_bound),
            dtype=np.float64,
        )
        method = "ocr"

    origin, left, right, top, bottom, max_line_width, page_height = corners_to_bounds(corners, angle)
    corners = clip_corners(corners, image_width, image_height)
    origin, left, right, top, bottom, max_line_width, page_height = corners_to_bounds(corners, angle)
    margin_x = max(max_line_width * margin_ratio, 16.0)
    margin_y = max(page_height * margin_ratio, 20.0)

    return PageRegion(
        angle_deg=math.degrees(angle),
        angle_rad=angle,
        max_line_width=max_line_width,
        margin_x=margin_x,
        margin_y=margin_y,
        left_bound=left,
        right_bound=right,
        top_bound=top,
        bottom_bound=bottom,
        origin=(float(origin[0]), float(origin[1])),
        corners=[[float(point[0]), float(point[1])] for point in corners],
        reference_index=reference_index,
        horizontal_line_count=len(horizontal_lines),
        detection_method=method,
    )


def region_polygon(region: PageRegion) -> np.ndarray:
    return np.array(region.corners, dtype=np.int32)


def box_center(box: list[list[float]]) -> np.ndarray:
    return np.array(box, dtype=np.float64).mean(axis=0)


def is_inside_page_region(box: list[list[float]], region: PageRegion) -> bool:
    center = box_center(box)
    distance = cv2.pointPolygonTest(
        region_polygon(region),
        (float(center[0]), float(center[1])),
        False,
    )
    return distance >= 0


def split_by_page_region(
    ocr_items: list[Any],
    region: PageRegion | None,
) -> tuple[list[Any], list[Any]]:
    if region is None:
        return ocr_items, []

    in_page: list[Any] = []
    out_page: list[Any] = []
    for item in ocr_items:
        if is_inside_page_region(item.box, region):
            in_page.append(item)
        else:
            out_page.append(item)
    return in_page, out_page


def extract_page_image(image: np.ndarray, region: PageRegion) -> np.ndarray:
    corners = np.array(region.corners, dtype=np.float32)
    width_top = float(np.linalg.norm(corners[1] - corners[0]))
    width_bottom = float(np.linalg.norm(corners[2] - corners[3]))
    height_left = float(np.linalg.norm(corners[3] - corners[0]))
    height_right = float(np.linalg.norm(corners[2] - corners[1]))

    output_width = int(max(width_top, width_bottom))
    output_height = int(max(height_left, height_right))
    output_width = max(output_width, 1)
    output_height = max(output_height, 1)

    destination = np.array(
        [
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(image, transform, (output_width, output_height))


def draw_page_region(
    image: np.ndarray,
    region: PageRegion,
    in_page_items: list[Any],
    out_page_items: list[Any],
) -> np.ndarray:
    overlay = image.copy()
    height, width = image.shape[:2]
    polygon = region_polygon(region)

    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [polygon], 255)
    excluded = mask == 0
    overlay[excluded] = (overlay[excluded] * 0.45 + np.array([0, 0, 180]) * 0.55).astype(
        np.uint8
    )

    color_mask = detect_page_mask(image)
    color_overlay = cv2.cvtColor(color_mask, cv2.COLOR_GRAY2BGR)
    color_overlay[:, :, 0] = 0
    color_overlay[:, :, 1] = 0
    overlay = cv2.addWeighted(overlay, 1.0, color_overlay, 0.15, 0)

    for item in in_page_items:
        box = np.array(item.box, dtype=np.int32)
        cv2.polylines(overlay, [box], True, (0, 180, 0), 2)

    for item in out_page_items:
        box = np.array(item.box, dtype=np.int32)
        cv2.polylines(overlay, [box], True, (0, 140, 255), 2)

    cv2.polylines(overlay, [polygon], True, (255, 0, 255), 3, cv2.LINE_AA)

    origin = np.array(region.origin, dtype=np.float64)
    axis_length = region.max_line_width * 0.35
    axis_start = from_document_coords(
        np.array([-axis_length, 0.0], dtype=np.float64),
        origin,
        region.angle_rad,
    )
    axis_end = from_document_coords(
        np.array([axis_length, 0.0], dtype=np.float64),
        origin,
        region.angle_rad,
    )
    cv2.arrowedLine(
        overlay,
        (int(axis_start[0]), int(axis_start[1])),
        (int(axis_end[0]), int(axis_end[1])),
        (0, 255, 255),
        3,
        tipLength=0.03,
    )

    for corner_index, corner in enumerate(region.corners):
        point = (int(corner[0]), int(corner[1]))
        cv2.circle(overlay, point, 8, (0, 255, 255), -1)
        cv2.putText(
            overlay,
            str(corner_index),
            (point[0] + 8, point[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

    label_y = 40
    cv2.putText(
        overlay,
        f"{region.detection_method} angle={region.angle_deg:.1f}deg",
        (20, label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 0, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        overlay,
        f"in={len(in_page_items)} out={len(out_page_items)}",
        (20, label_y + 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 0, 255),
        2,
        cv2.LINE_AA,
    )
    return overlay
