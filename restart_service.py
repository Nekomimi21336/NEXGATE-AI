import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _terminate(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
            return
        os.kill(pid, signal.SIGTERM)
        for _ in range(40):
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.25)
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def main() -> int:
    service_id = (sys.argv[1] if len(sys.argv) > 1 else "combined").strip().lower()
    parent_pid = int(sys.argv[2]) if len(sys.argv) > 2 else os.getppid()
    time.sleep(1.0)
    _terminate(parent_pid)
    time.sleep(0.5)

    env = os.environ.copy()
    env["NEXGATE_APP_MODE"] = "combined"
    env.setdefault("FLASK_PORT", os.getenv("FLASK_PORT", "5000"))

    entry = ROOT / "app.py"
    if not entry.exists():
        return 1
    subprocess.Popen(
        [sys.executable, str(entry)],
        cwd=str(ROOT),
        env=env,
        start_new_session=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
