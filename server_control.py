from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from server_health import OPERATION_MODE_COMBINED, SERVICE_IDS, normalize_deployment
from server_split import (
    SERVER_MODE_API,
    SERVER_MODE_API_PORTAL,
    SERVER_MODE_COMBINED,
    SERVER_MODE_FRONTEND,
    get_server_mode,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / "data" / "server_processes.json"
RESTART_QUEUE_FILE = ROOT / "data" / "server_restart_queue.json"

SERVICE_SCRIPTS = {
    "frontend": "frontend_server.py",
    "api_portal": "api_portal_server.py",
    "api": "api_server.py",
}

SERVICE_LABELS = {
    "frontend": "フロントサーバー",
    "api_portal": "APIフロントサーバー",
    "api": "APIサーバー",
}


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default
    return data


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def write_process_registry(processes: dict) -> None:
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "managed_by": "run_servers",
        "services": {},
    }
    for service_id, entry in processes.items():
        if service_id not in SERVICE_IDS or not isinstance(entry, dict):
            continue
        proc = entry.get("process")
        pid = proc.pid if proc and proc.poll() is None else None
        payload["services"][service_id] = {
            "pid": pid,
            "script": entry.get("script") or SERVICE_SCRIPTS.get(service_id, ""),
            "port": entry.get("port"),
        }
    _save_json(PID_FILE, payload)


def _load_restart_queue() -> dict:
    data = _load_json(RESTART_QUEUE_FILE, {"requests": []})
    if not isinstance(data, dict):
        return {"requests": []}
    requests = data.get("requests")
    if not isinstance(requests, list):
        requests = []
    return {"requests": requests}


def _save_restart_queue(queue: dict) -> None:
    _save_json(RESTART_QUEUE_FILE, queue)


def _find_request(queue: dict, request_id: str) -> dict | None:
    for entry in queue.get("requests") or []:
        if isinstance(entry, dict) and entry.get("id") == request_id:
            return entry
    return None


def _service_roles_for_runtime() -> set[str]:
    mode = get_server_mode()
    if mode == SERVER_MODE_COMBINED:
        return set(SERVICE_IDS)
    if mode == SERVER_MODE_FRONTEND:
        return {"frontend"}
    if mode == SERVER_MODE_API_PORTAL:
        return {"api_portal"}
    if mode == SERVER_MODE_API:
        return {"api"}
    return set()


def _can_restart_locally(service_id: str, operation_mode: str) -> bool:
    if service_id not in SERVICE_IDS:
        return False
    if operation_mode == OPERATION_MODE_COMBINED:
        return get_server_mode() == SERVER_MODE_COMBINED
    return service_id in _service_roles_for_runtime() or PID_FILE.exists()


def _spawn_restart_helper(service_id: str, parent_pid: int) -> None:
    helper = ROOT / "restart_service.py"
    subprocess.Popen(
        [sys.executable, str(helper), service_id, str(parent_pid)],
        cwd=str(ROOT),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def request_service_restart(service_id: str, *, operation_mode: str) -> tuple[dict | None, str | None]:
    service_id = (service_id or "").strip().lower()
    if service_id not in SERVICE_IDS:
        return None, "サービス ID が不正です"
    if not _can_restart_locally(service_id, operation_mode):
        return None, "このプロセスから再起動できません。run_servers.py または該当サーバーで実行してください。"

    request_id = uuid.uuid4().hex
    entry = {
        "id": request_id,
        "service_id": service_id,
        "status": "pending",
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "completed_at": "",
        "error": "",
    }
    queue = _load_restart_queue()
    queue["requests"] = [item for item in queue["requests"] if isinstance(item, dict)][-49:]
    queue["requests"].append(entry)
    _save_restart_queue(queue)

    if operation_mode == OPERATION_MODE_COMBINED or get_server_mode() == SERVER_MODE_COMBINED:
        threading.Thread(
            target=_spawn_restart_helper,
            args=(service_id, os.getpid()),
            daemon=True,
        ).start()
        entry["status"] = "restarting"
        _save_restart_queue(queue)
        return entry, None

    registry = _load_json(PID_FILE, {})
    if isinstance(registry, dict) and registry.get("managed_by") == "run_servers":
        return entry, None

    services = registry.get("services") if isinstance(registry, dict) else {}
    service_info = services.get(service_id) if isinstance(services, dict) else None
    if not isinstance(service_info, dict) or not service_info.get("pid"):
        return None, "プロセス情報がありません。python run_servers.py で起動してください。"

    threading.Thread(
        target=_restart_detached_process,
        args=(service_id, int(service_info["pid"])),
        daemon=True,
    ).start()
    entry["status"] = "restarting"
    _save_restart_queue(queue)
    return entry, None


def _restart_detached_process(service_id: str, pid: int) -> None:
    script = SERVICE_SCRIPTS.get(service_id)
    if not script:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(0.25)
            else:
                os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    time.sleep(0.5)
    env = os.environ.copy()
    if service_id == "api":
        env["NEXGATE_APP_MODE"] = "api"
        env.setdefault("FLASK_PORT", "5002")
    elif service_id == "api_portal":
        env["NEXGATE_APP_MODE"] = "api_portal"
        env.setdefault("FLASK_PORT", os.getenv("API_PORTAL_PORT", "5001"))
    else:
        env["NEXGATE_APP_MODE"] = "frontend"
        env.setdefault("FLASK_PORT", os.getenv("FRONTEND_PORT", "5000"))
    subprocess.Popen(
        [sys.executable, str(ROOT / script)],
        cwd=str(ROOT),
        env=env,
        start_new_session=True,
    )


def mark_restart_status(request_id: str, status: str, *, error: str = "") -> None:
    queue = _load_restart_queue()
    entry = _find_request(queue, request_id)
    if not entry:
        return
    entry["status"] = status
    if status in ("done", "failed"):
        entry["completed_at"] = datetime.now().isoformat(timespec="seconds")
    if error:
        entry["error"] = error
    _save_restart_queue(queue)


def get_restart_request(request_id: str) -> dict | None:
    queue = _load_restart_queue()
    entry = _find_request(queue, request_id)
    return dict(entry) if entry else None


def sync_restart_status(request_id: str, service_probe: dict | None) -> dict | None:
    queue = _load_restart_queue()
    entry = _find_request(queue, request_id)
    if not entry:
        return None
    if entry.get("status") in ("done", "failed"):
        return dict(entry)

    probe = service_probe if isinstance(service_probe, dict) else {}
    reachable = bool(probe.get("reachable"))
    uptime = int(probe.get("uptime_seconds") or 0)

    if not reachable:
        entry["seen_unreachable"] = True
    elif entry.get("seen_unreachable") or uptime < 90:
        entry["status"] = "done"
        entry["completed_at"] = datetime.now().isoformat(timespec="seconds")
        _save_restart_queue(queue)
        return dict(entry)

    requested_raw = (entry.get("requested_at") or "").strip()
    try:
        requested_at = datetime.fromisoformat(requested_raw)
    except ValueError:
        requested_at = datetime.now()
    if (datetime.now() - requested_at).total_seconds() > 180:
        entry["status"] = "failed"
        entry["error"] = "再起動がタイムアウトしました"
        entry["completed_at"] = datetime.now().isoformat(timespec="seconds")
        _save_restart_queue(queue)
    return dict(entry)


def process_pending_restarts(processes: dict, spawn_fn) -> None:
    queue = _load_restart_queue()
    changed = False
    for entry in queue.get("requests") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != "pending":
            continue
        service_id = entry.get("service_id")
        if service_id not in processes:
            entry["status"] = "failed"
            entry["error"] = "不明なサービスです"
            entry["completed_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            continue
        try:
            spawn_fn(service_id)
            entry["status"] = "restarting"
            changed = True
        except Exception as exc:
            logger.exception("restart failed for %s", service_id)
            entry["status"] = "failed"
            entry["error"] = str(exc)
            entry["completed_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
    if changed:
        _save_restart_queue(queue)


def service_label(service_id: str) -> str:
    return SERVICE_LABELS.get(service_id, service_id)
