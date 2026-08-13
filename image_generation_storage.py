"""Persist FLUX-generated images locally and serve via signed URLs."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GENERATED_IMAGES_DIR = Path(__file__).parent / "data" / "generated_images"
IMAGE_ID_RE = re.compile(r"^[a-f0-9]{32}$")
GENERATED_IMAGE_MARKDOWN_RE = re.compile(
    r"!\[[^\]]*\]\([^)]*/api/generated-images/[a-f0-9]{32}[^)]*\)\s*",
    re.IGNORECASE,
)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
DOWNLOAD_TIMEOUT_SEC = 120

_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _storage_secret():
    return (
        os.getenv("IMAGE_STORAGE_SECRET")
        or os.getenv("FLASK_SECRET_KEY")
        or "nexgate-dev-secret-change-me"
    )


def _safe_owner(username):
    safe = re.sub(r"[^a-z0-9._-]", "", (username or "").strip().lower())
    return safe or "unknown"


def _ensure_dir():
    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def image_signature(image_id):
    digest = hmac.new(
        _storage_secret().encode("utf-8"),
        (image_id or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:32]


def verify_image_signature(image_id, sig):
    if not image_id or not IMAGE_ID_RE.match(image_id):
        return False
    expected = image_signature(image_id)
    return hmac.compare_digest(expected, (sig or "").strip())


def strip_generated_image_markdown(text):
    if not isinstance(text, str) or not text:
        return text
    out = GENERATED_IMAGE_MARKDOWN_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def build_generated_image_url(image_id, *, base_url=""):
    sig = image_signature(image_id)
    path = f"/api/generated-images/{image_id}?sig={sig}"
    base = (base_url or "").rstrip("/")
    return f"{base}{path}" if base else path


def _meta_path(image_id):
    return GENERATED_IMAGES_DIR / f"{image_id}.json"


def _image_path(image_id, ext):
    return GENERATED_IMAGES_DIR / f"{image_id}{ext}"


def _guess_ext(content_type, data):
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _EXT_BY_TYPE:
        return _EXT_BY_TYPE[ct]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def _download_bytes(url):
    req = Request(url, headers={"User-Agent": "NexgateAI/1.0", "Accept": "image/*"})
    try:
        with urlopen(req, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
            content_type = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0]
            data = resp.read()
    except HTTPError as exc:
        raise RuntimeError(f"生成画像の取得に失敗しました: HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"生成画像の取得に失敗しました: {exc}") from exc
    if not data:
        raise RuntimeError("生成画像のデータが空です")
    if len(data) > MAX_IMAGE_BYTES:
        raise RuntimeError("生成画像が大きすぎて保存できません")
    return data, content_type


def load_image_record(image_id):
    if not image_id or not IMAGE_ID_RE.match(image_id):
        return None
    path = _meta_path(image_id)
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(record, dict):
        return None
    ext = record.get("ext") or ".jpg"
    file_path = _image_path(image_id, ext)
    if not file_path.is_file():
        return None
    record["path"] = file_path
    return record


def persist_generated_image_from_url(
    username,
    provider_url,
    *,
    prompt="",
    model_id="",
    api_model="",
    width=0,
    height=0,
    base_url="",
):
    if not (provider_url or "").strip().startswith("http"):
        raise RuntimeError("プロバイダ画像URLが不正です")
    _ensure_dir()
    data, content_type = _download_bytes(provider_url.strip())
    ext = _guess_ext(content_type, data)
    image_id = uuid.uuid4().hex
    file_path = _image_path(image_id, ext)
    meta = {
        "id": image_id,
        "owner": _safe_owner(username),
        "prompt": (prompt or "")[:4000],
        "model_id": (model_id or "")[:120],
        "api_model": (api_model or "")[:120],
        "width": int(width or 0),
        "height": int(height or 0),
        "content_type": (content_type or "image/jpeg").split(";")[0],
        "ext": ext,
        "created_at": _now_iso(),
        "bytes": len(data),
    }
    file_path.write_bytes(data)
    _meta_path(image_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "id": image_id,
        "url": build_generated_image_url(image_id, base_url=base_url),
        "content_type": meta["content_type"],
        "bytes": len(data),
    }


def can_access_image(image_id, *, sig="", session_user=""):
    record = load_image_record(image_id)
    if not record:
        return None
    owner = (record.get("owner") or "").lower()
    user = (session_user or "").strip().lower()
    if user and user == owner:
        return record
    if verify_image_signature(image_id, sig):
        return record
    return None
