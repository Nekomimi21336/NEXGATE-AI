import json
import os
import threading
import time

import requests

from computelab_token_store import get_api_key

_HTTP_SESSIONS = {}
_HTTP_SESSION_LOCK = threading.Lock()

INSTANCE_STATUSES_RUNNING = frozenset({"RUNNING"})
INSTANCE_STATUSES_TERMINAL = frozenset({"DELETED", "ERROR"})

COMPUTELAB_API_BASE = (
    os.getenv("COMPUTELAB_API_BASE", "https://dash.cl.nextvps.online").rstrip("/")
)

COMPUTELAB_DATA_DEPLOY_HINT = (
    "アプリ・テンプレート・静的ファイルはデータ領域 /data に配置してください"
    "（API 相対パス例: app/app.py, app/templates/, app/static/）。"
    "ComputeLab ダッシュボードのファイルエクスプローラーから閲覧・編集できます。"
    "コンテナ内の実パスは /data/<相対パス> です。"
)


def _api_error(resp):
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error") or data
            if isinstance(err, str):
                msg = err
            else:
                msg = str(err)
            details = data.get("details")
            if details:
                msg = f"{msg} ({details})"
            extra = []
            if "required" in data:
                extra.append(f"required={data['required']}")
            if "balance" in data:
                extra.append(f"balance={data['balance']}")
            if extra:
                msg = f"{msg} [{', '.join(extra)}]"
            return msg or resp.text[:300]
        return resp.text[:300]
    except Exception:
        return resp.text[:300] or f"HTTP {resp.status_code}"


def _http_session(api_key):
    with _HTTP_SESSION_LOCK:
        session = _HTTP_SESSIONS.get(api_key)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                }
            )
            _HTTP_SESSIONS[api_key] = session
        return session


def computelab_request(username, method, path, *, params=None, json_body=None, timeout=60):
    api_key = get_api_key(username)
    if not api_key:
        return None, "ComputeLab API キーが未設定です。設定の連携タブから登録してください。"

    url = f"{COMPUTELAB_API_BASE}{path}"
    headers = {}
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    try:
        resp = _http_session(api_key).request(
            method.upper(),
            url,
            headers=headers or None,
            params=params,
            json=json_body,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return None, f"ComputeLab API 接続エラー: {exc}"

    if resp.status_code >= 400:
        return None, _api_error(resp)

    if resp.status_code == 204 or not resp.content:
        return {"ok": True}, None

    try:
        return resp.json(), None
    except ValueError:
        return {"raw": resp.text[:2000]}, None


def test_connection(username):
    profile, err = computelab_request(username, "GET", "/auth/me")
    if err:
        return None, err
    catalog, err = computelab_request(username, "GET", "/api/catalog")
    if err:
        return {"profile": profile}, err
    return {"profile": profile, "catalog_ok": True}, None


def verify_api_key(api_key):
    key = (api_key or "").strip()
    if not key:
        return None, "API キーを入力してください"
    if not key.startswith("cl_live_"):
        return None, "API キーの形式が正しくありません（cl_live_ で始まるキー）"

    url = f"{COMPUTELAB_API_BASE}/auth/me"
    try:
        resp = _http_session(key).get(url, timeout=30)
    except requests.RequestException as exc:
        return None, f"ComputeLab API 接続エラー: {exc}"

    if resp.status_code == 401:
        return None, "API キーが無効です"
    if resp.status_code >= 400:
        return None, _api_error(resp)

    try:
        return resp.json(), None
    except ValueError:
        return None, "ComputeLab API の応答を解析できませんでした"


def format_tool_result(data, error=None):
    if error:
        return json.dumps({"ok": False, "error": error}, ensure_ascii=False)
    return json.dumps({"ok": True, **(data or {})}, ensure_ascii=False)


def fetch_catalog(username):
    return computelab_request(username, "GET", "/api/catalog")


def fetch_balance(username):
    return computelab_request(username, "GET", "/api/billing/balance")


def list_instances(username):
    data, err = computelab_request(username, "GET", "/api/instances")
    if err:
        return None, err
    if isinstance(data, list):
        instances = []
        for inst in data:
            row = dict(inst) if isinstance(inst, dict) else {}
            if "rootPassword" in row:
                row["rootPassword"] = "(設定済み・詳細取得で表示)"
            row["instanceId"] = row.get("id", "")
            instances.append(row)
        return {
            "instances": instances,
            "count": len(instances),
            "hint": (
                "instance_id には各要素の id をそのまま使う（例 clx… / cmp…）。推測・別ID禁止。"
                " status が PROVISIONING のときは exec 不可。computelab_wait_running を使う。"
            ),
            "deployHint": COMPUTELAB_DATA_DEPLOY_HINT,
        }, None
    return {"instances": [], "count": 0}, None


def get_instance(username, instance_id):
    iid = (instance_id or "").strip()
    if not iid:
        return None, "instance_id が必要です"
    return computelab_request(username, "GET", f"/api/instances/{iid}")


def get_instance_connection(username, instance_id):
    iid = (instance_id or "").strip()
    if not iid:
        return None, "instance_id が必要です"
    return computelab_request(username, "GET", f"/api/instances/{iid}/connection")


def create_instance(
    username,
    *,
    cpu,
    memory_mb,
    disk_gb,
    ttl_hours=None,
    image_key=None,
    node_id=None,
    name=None,
    vpc_id=None,
):
    if cpu is None or memory_mb is None or disk_gb is None:
        return None, "cpu、memory_mb、disk_gb は必須です"
    body = {
        "cpu": int(cpu),
        "memoryMb": int(memory_mb),
        "diskGb": int(disk_gb),
    }
    if ttl_hours is not None:
        body["ttlHours"] = int(ttl_hours)
    if image_key:
        body["imageKey"] = str(image_key).strip()
    if node_id:
        body["nodeId"] = str(node_id).strip()
    if name:
        body["name"] = str(name).strip()
    if vpc_id:
        body["vpcId"] = str(vpc_id).strip()
    return computelab_request(username, "POST", "/api/instances", json_body=body)


def instance_action(username, instance_id, action):
    iid = (instance_id or "").strip()
    act = (action or "").strip().lower()
    if not iid:
        return None, "instance_id が必要です"
    routes = {
        "start": ("POST", f"/api/instances/{iid}/start"),
        "stop": ("POST", f"/api/instances/{iid}/stop"),
        "restart": ("POST", f"/api/instances/{iid}/restart"),
        "delete": ("DELETE", f"/api/instances/{iid}"),
    }
    if act not in routes:
        return None, "action は start / stop / restart / delete のいずれかです"
    method, path = routes[act]
    return computelab_request(username, method, path)


def _public_url_for_instance(instance, host_port):
    if not host_port:
        return ""
    host = ""
    if isinstance(instance, dict):
        host = (
            (instance.get("publicHostIp") or "").strip()
            or (instance.get("hostname") or "").strip()
            or (instance.get("dnsHostname") or "").strip()
        )
    if not host:
        return ""
    return f"http://{host}:{int(host_port)}"


def wait_instance_running(
    username,
    instance_id,
    *,
    max_wait_sec=180,
    poll_interval_sec=5,
):
    iid = (instance_id or "").strip()
    if not iid:
        return None, "instance_id が必要です"
    deadline = time.monotonic() + max(5, int(max_wait_sec))
    poll_interval_sec = max(2, int(poll_interval_sec))
    last_status = ""
    first = True
    while time.monotonic() < deadline:
        data, err = get_instance(username, iid)
        if err:
            return None, err
        status = (data or {}).get("status") or ""
        last_status = status
        if status in INSTANCE_STATUSES_RUNNING:
            return {
                "id": iid,
                "status": status,
                "ready": True,
                "publicHostIp": (data or {}).get("publicHostIp"),
            }, None
        if status in INSTANCE_STATUSES_TERMINAL:
            return None, f"インスタンスは {status} のため続行できません"
        if first:
            first = False
        else:
            time.sleep(poll_interval_sec)
    return None, (
        f"RUNNING になるまで待機しましたがタイムアウトです（最後の status: {last_status or '不明'}）。"
        " computelab_get_instance で再確認してください。"
    )


def _enrich_port_mapping(data, instance):
    if not isinstance(data, dict) or not isinstance(instance, dict):
        return data
    out = dict(data)
    hp = out.get("hostPort")
    pub_ip = (instance.get("publicHostIp") or "").strip()
    hostname = (
        (instance.get("hostname") or "").strip()
        or (instance.get("dnsHostname") or "").strip()
    )
    out["publicHostIp"] = pub_ip or None
    out["dnsHostname"] = hostname or None
    if pub_ip and hp is not None:
        out["publicTcpEndpoint"] = f"{pub_ip}:{int(hp)}"
        proto = (out.get("protocol") or "TCP").upper()
        if proto == "TCP" and int(out.get("containerPort") or 0) != 443:
            out["suggestedPublicUrl"] = f"http://{pub_ip}:{int(hp)}"
    elif hostname and hp is not None:
        out["publicTcpEndpoint"] = f"{hostname}:{int(hp)}"
    out["note"] = (
        "Web は suggestedPublicUrl、マイクラ等の raw TCP は publicTcpEndpoint（IP:hostPort）を提示。"
        " ポート追加後はプロセスが落ちることがあるため computelab_exec で再起動。"
    )
    return out


def add_port(
    username,
    instance_id,
    *,
    container_port,
    protocol="tcp",
    label=None,
):
    iid = (instance_id or "").strip()
    if not iid:
        return None, "instance_id が必要です"
    if container_port is None:
        return None, "container_port が必要です"
    body = {
        "containerPort": int(container_port),
        "protocol": (protocol or "tcp").strip().lower(),
    }
    if label:
        body["label"] = str(label).strip()
    data, err = computelab_request(
        username,
        "POST",
        f"/api/instances/{iid}/ports",
        json_body=body,
        timeout=120,
    )
    if err:
        return data, err
    if isinstance(data, dict):
        inst, inst_err = get_instance(username, iid)
        if not inst_err and isinstance(inst, dict):
            data = _enrich_port_mapping(data, inst)
    return data, err


def _normalize_data_path(path):
    p = (path or "").strip().replace("\\", "/")
    while p.startswith("/"):
        p = p[1:]
    parts = [x for x in p.split("/") if x and x != "."]
    if ".." in parts:
        return None, "path に .. は使えません"
    return "/".join(parts), None


def list_data_files(username, instance_id, *, path=""):
    iid = (instance_id or "").strip()
    if not iid:
        return None, "instance_id が必要です"
    rel, err = _normalize_data_path(path)
    if err:
        return None, err
    params = {"path": rel} if rel else None
    data, err = computelab_request(
        username,
        "GET",
        f"/api/instances/{iid}/data/files",
        params=params,
    )
    if err:
        return data, err
    if isinstance(data, dict):
        data = dict(data)
        data.setdefault("mountInContainer", "/data")
        data.setdefault("deployHint", COMPUTELAB_DATA_DEPLOY_HINT)
    return data, err


def read_data_text(username, instance_id, *, path):
    iid = (instance_id or "").strip()
    if not iid:
        return None, "instance_id が必要です"
    rel, err = _normalize_data_path(path)
    if err:
        return None, err
    if not rel:
        return None, "path が必要です"
    data, err = computelab_request(
        username,
        "GET",
        f"/api/instances/{iid}/data/text",
        params={"path": rel},
        timeout=120,
    )
    if err:
        return data, err
    if isinstance(data, dict):
        content = data.get("content") or ""
        if len(content) > 120_000:
            data = dict(data)
            data["content"] = content[:120_000]
            data["truncated"] = True
            data["note"] = "content は先頭 120000 文字に切り詰めています"
    return data, err


def write_data_text(username, instance_id, *, path, content):
    iid = (instance_id or "").strip()
    if not iid:
        return None, "instance_id が必要です"
    rel, err = _normalize_data_path(path)
    if err:
        return None, err
    if not rel:
        return None, "path が必要です"
    if content is None:
        return None, "content が必要です"
    text = str(content)
    if len(text) > 512_000:
        return None, "content は 512000 文字以内にしてください"
    data, err = computelab_request(
        username,
        "PUT",
        f"/api/instances/{iid}/data/text",
        json_body={"path": rel, "content": text},
        timeout=120,
    )
    if err:
        return data, err
    if isinstance(data, dict):
        data = dict(data)
        data["path"] = rel
        data["mountInContainer"] = "/data"
        data["containerPath"] = f"/data/{rel}"
        data["deployHint"] = COMPUTELAB_DATA_DEPLOY_HINT
        data["note"] = (
            "コンテナ内の /data に保存しました（ダッシュボードのエクスプローラーでも編集可）。"
            " Flask 等を更新した場合は computelab_exec で再起動してください。"
        )
    return data, err


def mkdir_data(username, instance_id, *, parent="", name):
    iid = (instance_id or "").strip()
    if not iid:
        return None, "instance_id が必要です"
    parent_rel, err = _normalize_data_path(parent)
    if err:
        return None, err
    dir_name = (name or "").strip().replace("\\", "/").strip("/")
    if not dir_name or "/" in dir_name or dir_name in (".", ".."):
        return None, "name が不正です"
    return computelab_request(
        username,
        "POST",
        f"/api/instances/{iid}/data/mkdir",
        json_body={"parent": parent_rel or "", "name": dir_name},
    )


def exec_command(
    username,
    instance_id,
    *,
    command=None,
    shell=None,
    cwd=None,
    timeout_ms=None,
):
    iid = (instance_id or "").strip()
    if not iid:
        return None, "instance_id が必要です"
    if command and shell:
        return None, "command と shell は同時に指定できません"
    if command:
        if not isinstance(command, list):
            return None, "command は文字列の配列です"
        body = {"command": [str(c) for c in command]}
    elif shell:
        body = {"shell": str(shell).strip()}
    else:
        return None, "command または shell を指定してください"
    if cwd:
        rel, err = _normalize_data_path(cwd)
        if err:
            return None, err
        body["cwd"] = f"/data/{rel}" if rel else "/data"
    if timeout_ms is not None:
        body["timeoutMs"] = max(1000, min(int(timeout_ms), 600_000))
    http_timeout = 120
    if body.get("timeoutMs"):
        http_timeout = min(600, max(120, int(body["timeoutMs"]) // 1000 + 30))
    return computelab_request(
        username,
        "POST",
        f"/api/instances/{iid}/exec",
        json_body=body,
        timeout=http_timeout,
    )
