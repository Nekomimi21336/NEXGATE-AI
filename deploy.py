#!/usr/bin/env python3
"""
NEXGATE AI 本番デプロイ（低ダウンタイム）

1. ローカルで配布アーカイブを作成
2. 稼働中のままアーカイブを本番へアップロード（ダウンタイムなし）
3. 短時間のカットオーバー: 停止 → tar 展開 → 起動
4. 本番 data/ をローカルへ同期（本番稼働後・任意）

事前準備:
  pip install paramiko
  copy .deploy.env.example .deploy.env
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import shutil
import sys
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent

EXCLUDE_DIR_NAMES = {
    "data",
    ".git",
    "__pycache__",
    ".cursor",
    "venv",
    ".venv",
    "node_modules",
    ".idea",
    ".vscode",
    "data_backup",
}

EXCLUDE_FILE_NAMES = {
    ".env",
    ".deploy.env",
    "deploy.config.json",
    "deploy.config.example.json",
    ".deploy.env.example",
}

EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

PROCESS_SCRIPTS = (
    "run_servers.py",
    "api_server.py",
    "frontend_server.py",
    "api_portal_server.py",
    "app.py",
)


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def safe_console(text: str) -> str:
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(enc, errors="replace").decode(enc)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_config() -> dict:
    _load_dotenv(ROOT / ".deploy.env")

    cfg = {
        "host": os.getenv("DEPLOY_HOST", "210.131.212.59"),
        "user": os.getenv("DEPLOY_USER", "root"),
        "password": os.getenv("DEPLOY_PASSWORD", ""),
        "remote_dir": os.getenv("DEPLOY_REMOTE_DIR", "/root/NEXGATE"),
        "screen_session": os.getenv("DEPLOY_SCREEN_SESSION", "nexgate"),
        "start_script": os.getenv("DEPLOY_START_SCRIPT", "run_servers.py"),
        "python": os.getenv("DEPLOY_PYTHON", "python3"),
        "port": int(os.getenv("DEPLOY_PORT", "22")),
        "compress_level": int(os.getenv("DEPLOY_COMPRESS_LEVEL", "1")),
        "stop_wait_sec": float(os.getenv("DEPLOY_STOP_WAIT_SEC", "1")),
    }

    config_path = ROOT / "deploy.config.json"
    if config_path.exists():
        file_cfg = json.loads(config_path.read_text(encoding="utf-8"))
        for key, value in file_cfg.items():
            if value not in (None, "", "CHANGE_ME"):
                cfg[key] = value

    return cfg


def require_paramiko():
    try:
        import paramiko  # noqa: F401
    except ImportError as exc:
        raise SystemExit("paramiko が必要です: pip install paramiko") from exc


def connect(cfg: dict):
    require_paramiko()
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=cfg["host"],
        port=cfg["port"],
        username=cfg["user"],
        password=cfg["password"],
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def run_remote(client, command: str, *, timeout: int = 120) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    del stdin
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def log_step(title: str) -> None:
    print(f"\n=== {title} ===")


def elapsed_since(start: float) -> str:
    return f"{time.time() - start:.1f}s"


def should_upload(rel: Path) -> bool:
    if not rel.parts:
        return False
    first = rel.parts[0]
    if first in EXCLUDE_DIR_NAMES or first.startswith("data_backup_"):
        return False
    if any(part in EXCLUDE_DIR_NAMES for part in rel.parts):
        return False
    if rel.name in EXCLUDE_FILE_NAMES:
        return False
    if rel.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    return True


def iter_local_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if should_upload(rel):
            files.append(rel)
    return sorted(files)


def tar_add_file(tar: tarfile.TarFile, local_path: Path, arcname: str) -> None:
    try:
        tar.add(local_path, arcname=arcname, filter="data")
    except TypeError:
        tar.add(local_path, arcname=arcname)


def build_deploy_archive(files: list[Path], dest: Path, *, compress_level: int = 1) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz", compresslevel=compress_level) as tar:
        for rel in files:
            tar_add_file(tar, ROOT / rel, rel.as_posix())
    return dest


def ensure_remote_dir(sftp, remote_path: str) -> None:
    parts = PurePosixPath(remote_path).parts
    current = ""
    for part in parts:
        current = posixpath.join(current, part) if current else part
        if current in ("", "/"):
            continue
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def upload_archive(client, local_archive: Path, remote_tar: str) -> None:
    total = local_archive.stat().st_size
    last_report = {"t": 0.0}

    def progress(done: int, _total: int) -> None:
        now = time.time()
        if done < total and now - last_report["t"] < 1.5:
            return
        last_report["t"] = now
        pct = 100 * done // total if total else 100
        print(f"  {done // 1024} / {total // 1024} KB ({pct}%)")

    sftp = client.open_sftp()
    try:
        sftp.put(str(local_archive), remote_tar, callback=progress, confirm=True)
    finally:
        sftp.close()


def stop_remote(client, cfg: dict) -> None:
    remote_dir = cfg["remote_dir"].rstrip("/")
    screen_name = cfg["screen_session"]
    wait_sec = cfg.get("stop_wait_sec", 1)
    script_names = " ".join(PROCESS_SCRIPTS)
    script = (
        f"remote_dir={sh_quote(remote_dir)}; "
        f"screen_name={sh_quote(screen_name)}; "
        f"for name in {script_names}; do "
        f"pkill -TERM -f \"$remote_dir/$name\" 2>/dev/null || true; "
        f"done; "
        f"sleep {wait_sec}; "
        f"for name in {script_names}; do "
        f"pkill -KILL -f \"$remote_dir/$name\" 2>/dev/null || true; "
        f"done; "
        f"screen -S \"$screen_name\" -X quit 2>/dev/null || true; "
        f"for sid in $(screen -ls 2>/dev/null | awk '/\\.(pts-|nexgate|NEXGATE)/ {{print $1}}' | cut -d. -f1); do "
        f"screen -S \"$sid\" -X quit 2>/dev/null || true; "
        f"done"
    )
    run_remote(client, f"bash -lc {sh_quote(script)}", timeout=45)


def start_remote(client, cfg: dict) -> None:
    remote_dir = cfg["remote_dir"].rstrip("/")
    screen_name = cfg["screen_session"]
    python_bin = cfg["python"]
    start_script = cfg["start_script"]

    pip_cmd = (
        f"cd {sh_quote(remote_dir)} && "
        f"{sh_quote(python_bin)} -m pip install -q --disable-pip-version-check --break-system-packages -r requirements.txt"
    )
    log_step("依存パッケージインストール")
    t0 = time.time()
    code, out, err = run_remote(client, f"bash -lc {sh_quote(pip_cmd)}", timeout=600)
    pip_log = (out or err or "").strip()
    if pip_log:
        print(f"  {safe_console(pip_log[:500])}")
    if code != 0:
        raise RuntimeError(f"pip install に失敗しました: {err or out}")
    print(f"  完了 ({elapsed_since(t0)})")

    inner = (
        f"cd {sh_quote(remote_dir)} && "
        f"mkdir -p logs && "
        f"exec {sh_quote(python_bin)} {sh_quote(start_script)} >> logs/run.log 2>&1"
    )
    command = f"screen -dmS {sh_quote(screen_name)} bash -lc {sh_quote(inner)}"
    code, out, err = run_remote(client, command, timeout=30)
    if code != 0:
        raise RuntimeError(f"起動に失敗しました: {err or out}")
    print("  screen セッションを開始しました")


def extract_remote_archive(client, cfg: dict, remote_tar: str) -> None:
    remote_dir = cfg["remote_dir"].rstrip("/")
    sftp = client.open_sftp()
    try:
        ensure_remote_dir(sftp, remote_dir)
    finally:
        sftp.close()
    command = f"cd {sh_quote(remote_dir)} && tar -xzf {sh_quote(remote_tar)}"
    code, out, err = run_remote(client, command, timeout=180)
    if code != 0:
        raise RuntimeError(f"展開に失敗しました: {err or out}")


def deploy_project(client, cfg: dict, *, dry_run: bool = False) -> None:
    files = iter_local_files()
    log_step(f"配布パッケージ作成 ({len(files)} ファイル, data/ と .env は除外)")
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="nexgate-deploy-") as tmp:
        archive = build_deploy_archive(
            files,
            Path(tmp) / "nexgate-release.tar.gz",
            compress_level=int(cfg.get("compress_level", 1)),
        )
        size_mb = archive.stat().st_size / (1024 * 1024)
        print(f"  サイズ: {size_mb:.2f} MB ({elapsed_since(t0)})")

        if dry_run:
            print("  (dry-run: 転送・カットオーバーは省略)")
            return

        remote_tar = f"/tmp/nexgate-deploy-{int(time.time())}.tar.gz"

        log_step("アップロード（本番稼働中）")
        t1 = time.time()
        upload_archive(client, archive, remote_tar)
        print(f"  完了 ({elapsed_since(t1)})")

        log_step("カットオーバー（停止 → 展開 → 起動）")
        t2 = time.time()
        stop_remote(client, cfg)
        print(f"  停止 ({elapsed_since(t2)})")
        t3 = time.time()
        extract_remote_archive(client, cfg, remote_tar)
        run_remote(client, f"rm -f {sh_quote(remote_tar)}", timeout=30)
        print(f"  展開 ({elapsed_since(t3)})")
        t4 = time.time()
        start_remote(client, cfg)
        print(f"  起動 ({elapsed_since(t4)})")
        print(f"  ダウンタイム目安: {elapsed_since(t2)}")


def backup_local_data() -> Path | None:
    local_data = ROOT / "data"
    if not local_data.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / f"data_backup_{stamp}"
    shutil.copytree(local_data, backup_dir)
    return backup_dir


def pull_remote_data(client, cfg: dict, *, dry_run: bool = False) -> None:
    log_step("本番 data/ をローカルへ同期")
    remote_dir = cfg["remote_dir"].rstrip("/")
    remote_tar = f"/tmp/nexgate-data-sync-{int(time.time())}.tar.gz"
    pack_cmd = f"cd {json.dumps(remote_dir)} && tar -czf {json.dumps(remote_tar)} data"
    code, out, err = run_remote(client, pack_cmd, timeout=600)
    if code != 0:
        raise RuntimeError(f"本番 data のアーカイブに失敗: {err or out}")

    if dry_run:
        print(f"  取得予定: {remote_tar}")
        run_remote(client, f"rm -f {json.dumps(remote_tar)}", timeout=30)
        return

    backup = backup_local_data()
    if backup:
        print(f"  ローカル data をバックアップ: {backup.name}")

    local_data = ROOT / "data"
    if local_data.exists():
        shutil.rmtree(local_data)

    with tempfile.TemporaryDirectory() as tmp:
        local_tar = Path(tmp) / "data.tar.gz"
        sftp = client.open_sftp()
        try:
            sftp.get(remote_tar, str(local_tar))
        finally:
            sftp.close()
        run_remote(client, f"rm -f {json.dumps(remote_tar)}", timeout=30)

        with tarfile.open(local_tar, "r:gz") as archive:
            try:
                archive.extractall(ROOT, filter="data")
            except TypeError:
                archive.extractall(ROOT)

    print("  ローカル data/ を本番データで上書きしました")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NEXGATE AI 本番デプロイ")
    parser.add_argument("--dry-run", action="store_true", help="実行内容のみ表示")
    parser.add_argument("--skip-upload", action="store_true", help="コード配布を省略")
    parser.add_argument("--skip-pull-data", action="store_true", help="本番 data のローカル同期を省略")
    parser.add_argument("--pull-data-only", action="store_true", help="data 同期のみ実行")
    parser.add_argument("--password", help="SSH パスワード（未指定時は設定ファイル）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config()
    if args.password:
        cfg["password"] = args.password
    if not cfg.get("password") or cfg["password"] == "CHANGE_ME":
        print(
            "デプロイ用パスワードが未設定です。\n"
            "  .deploy.env に DEPLOY_PASSWORD=... を設定するか\n"
            "  deploy.config.json を作成するか\n"
            "  --password を指定してください。",
            file=sys.stderr,
        )
        return 1

    print(f"接続先: {cfg['user']}@{cfg['host']}:{cfg['remote_dir']}")

    if args.dry_run and args.pull_data_only:
        print("  (dry-run: data 同期のみの確認)")
        return 0

    if args.dry_run and not args.pull_data_only:
        deploy_project(None, cfg, dry_run=True)
        log_step("完了 (dry-run)")
        print("  実デプロイ時のダウンタイムは「カットオーバー」段階のみ（通常数秒〜十数秒）")
        return 0

    client = connect(cfg)
    try:
        if args.pull_data_only:
            pull_remote_data(client, cfg, dry_run=False)
            return 0

        if not args.skip_upload:
            deploy_project(client, cfg, dry_run=False)
        else:
            log_step("コード配布を省略")
            t0 = time.time()
            stop_remote(client, cfg)
            start_remote(client, cfg)
            print(f"  再起動のみ ({elapsed_since(t0)})")

        if not args.skip_pull_data:
            pull_remote_data(client, cfg, dry_run=False)

        log_step("完了")
        print("  本番ログ: ssh 後に tail -f /root/NEXGATE/logs/run.log")
        print(f"  screen 確認: screen -r {cfg['screen_session']}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
