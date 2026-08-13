"""OCR / scanner 用 Python 依存パッケージの検出と自動インストール。"""

from __future__ import annotations

import importlib
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent

OCR_PACKAGES: tuple[tuple[str, str], ...] = (
    ("numpy", "numpy>=1.24.0"),
    ("cv2", "opencv-python>=4.8.0"),
    ("PIL", "Pillow>=10.0.0"),
    ("fitz", "pymupdf>=1.24.0"),
    ("onnxruntime", "onnxruntime>=1.16.0"),
    ("rapidocr", "rapidocr>=3.9.0"),
)

_ensured = False


def _skip_install() -> bool:
    return os.environ.get("NEXGATE_SKIP_OCR_DEPS_INSTALL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _pip_quiet() -> bool:
    return os.environ.get("NEXGATE_OCR_DEPS_QUIET", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _auto_install_on_startup() -> bool:
    if _skip_install():
        return False
    return os.environ.get("NEXGATE_OCR_AUTO_INSTALL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _import_probe(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False
    except Exception as exc:
        logger.warning("OCR dependency probe failed for %s: %s", module, exc)
        return False


def missing_ocr_dependencies() -> list[str]:
    missing: list[str] = []
    for module, spec in OCR_PACKAGES:
        if not _import_probe(module):
            missing.append(spec)
    return missing


def _pip_extra_args() -> list[str]:
    return ["--break-system-packages"]


def _pip_install(specs: list[str]) -> int:
    if not specs:
        return 0
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--upgrade",
        *_pip_extra_args(),
    ]
    if _pip_quiet():
        cmd.append("-q")
    cmd.extend(specs)
    result = subprocess.run(cmd, cwd=str(ROOT), check=False)
    return int(result.returncode or 0)


def ensure_ocr_dependencies(*, install: bool = True, force: bool = False) -> list[str]:
    global _ensured
    if _ensured and not force:
        return []

    missing = missing_ocr_dependencies()
    if not missing:
        _ensured = True
        return []

    if not install or _skip_install():
        return missing

    specs = list(dict.fromkeys(missing))
    logger.info("Installing OCR dependencies: %s", ", ".join(specs))
    print(f"[ocr_deps] 不足ライブラリをインストール中: {', '.join(specs)}", flush=True)
    _pip_install(specs)

    missing = missing_ocr_dependencies()
    if missing:
        req = ROOT / "requirements.txt"
        if req.exists():
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                *_pip_extra_args(),
                "-r",
                str(req),
            ]
            if _pip_quiet():
                cmd.append("-q")
            subprocess.run(cmd, cwd=str(ROOT), check=False)
        missing = missing_ocr_dependencies()

    _ensured = not missing
    if missing:
        logger.error("OCR dependencies still missing: %s", ", ".join(missing))
        print(
            f"[ocr_deps] インストール後も不足: {', '.join(missing)}",
            flush=True,
        )
    else:
        print("[ocr_deps] OCRライブラリの準備が完了しました", flush=True)
    return missing


def ensure_ocr_dependencies_on_startup() -> None:
    try:
        ensure_ocr_dependencies(install=_auto_install_on_startup())
    except Exception as exc:
        logger.exception("OCR dependency setup failed")
        print(f"[ocr_deps] 依存関係セットアップ失敗: {exc}", flush=True)
