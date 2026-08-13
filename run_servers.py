import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from server_control import process_pending_restarts, write_process_registry

ROOT = Path(__file__).resolve().parent


def _build_env(base_env, *, mode, port):
    env = dict(base_env)
    env["NEXGATE_APP_MODE"] = mode
    env["FLASK_PORT"] = str(port)
    return env


def _spawn_service(service_id, script_name, env):
    return subprocess.Popen(
        [sys.executable, str(ROOT / script_name)],
        cwd=str(ROOT),
        env=env,
    )


def main() -> int:
    from ocr_dependencies import ensure_ocr_dependencies_on_startup

    ensure_ocr_dependencies_on_startup()
    # リアルタイム要約をバックグラウンドで開始
    try:
        from realtime_summary import start_realtime_summary
        start_realtime_summary()
    except Exception:
        pass
    env = os.environ.copy()
    env["NEXGATE_APP_MODE"] = "api"
    env.setdefault("FLASK_PORT", "5002")
    env.setdefault("FRONTEND_BASE_URL", "http://127.0.0.1:5000")
    env.setdefault("API_PORTAL_BASE_URL", "http://127.0.0.1:5001")
    env.setdefault("API_INTERNAL_URL", "http://127.0.0.1:5002")

    api_port = env.get("FLASK_PORT", "5002")
    portal_port = os.getenv("API_PORTAL_PORT", "5001")
    frontend_port = os.getenv("FRONTEND_PORT", "5000")

    processes = {
        "api": {
            "process": _spawn_service("api", "api_server.py", _build_env(env, mode="api", port=api_port)),
            "script": "api_server.py",
            "port": api_port,
        }
    }
    time.sleep(1.0)

    processes["api_portal"] = {
        "process": _spawn_service(
            "api_portal",
            "api_portal_server.py",
            _build_env(env, mode="api_portal", port=portal_port),
        ),
        "script": "api_portal_server.py",
        "port": portal_port,
    }
    time.sleep(0.5)

    frontend_env = _build_env(env, mode="frontend", port=frontend_port)
    frontend_env["API_INTERNAL_URL"] = os.getenv("API_INTERNAL_URL", "http://127.0.0.1:5002")
    processes["frontend"] = {
        "process": _spawn_service("frontend", "frontend_server.py", frontend_env),
        "script": "frontend_server.py",
        "port": frontend_port,
    }

    def restart_service(service_id: str) -> None:
        entry = processes.get(service_id)
        if not entry:
            return
        proc = entry["process"]
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if service_id == "api":
            new_env = _build_env(env, mode="api", port=api_port)
        elif service_id == "api_portal":
            new_env = _build_env(env, mode="api_portal", port=portal_port)
        else:
            new_env = dict(frontend_env)
        entry["process"] = _spawn_service(service_id, entry["script"], new_env)
        write_process_registry(processes)

    def shutdown(*_args):
        for entry in processes.values():
            proc = entry.get("process")
            if proc and proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    print("Frontend:   http://127.0.0.1:%s" % frontend_port)
    print("API Portal: http://127.0.0.1:%s" % portal_port)
    print("API Server: http://127.0.0.1:%s" % api_port)
    print("Press Ctrl+C to stop all servers.")

    write_process_registry(processes)

    try:
        while True:
            process_pending_restarts(processes, restart_service)
            write_process_registry(processes)

            for service_id, entry in processes.items():
                proc = entry["process"]
                if proc.poll() is not None:
                    shutdown()
                    return proc.returncode or 0

            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
