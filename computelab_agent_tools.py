import json
import logging

from computelab_services import (
    COMPUTELAB_API_BASE,
    add_port,
    create_instance,
    exec_command,
    fetch_balance,
    fetch_catalog,
    format_tool_result,
    get_instance,
    get_instance_connection,
    instance_action,
    list_data_files,
    list_instances,
    mkdir_data,
    read_data_text,
    wait_instance_running,
    write_data_text,
)

logger = logging.getLogger(__name__)

COMPUTELAB_BETA_PREFIX = "[Beta]"
COMPUTELAB_DASHBOARD_URL = "https://dash.cl.nextvps.online"


def computelab_tool_display_name(api_name):
    return f"{COMPUTELAB_BETA_PREFIX} {api_name}"


def _wrap_computelab_tool(tool_def):
    fn = dict(tool_def["function"])
    api_name = fn["name"]
    display = computelab_tool_display_name(api_name)
    desc = (fn.get("description") or "").replace(
        "【ComputeLab】", "【ComputeLab Beta】"
    )
    if not desc.startswith(COMPUTELAB_BETA_PREFIX):
        fn["description"] = f"{display}\n{desc}"
    return {"type": "function", "function": fn}


COMPUTELAB_CATALOG_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_catalog",
        "description": (
            "【ComputeLab】GET /api/catalog — 作成可能スペック・OS イメージ・placementNodes（node_id）と料金。"
            "使う: インスタンス作成前。creationMax で cpu/memoryMb/diskGb の上限を確認。"
            "使わない: 既存 VM の操作。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

COMPUTELAB_BALANCE_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_balance",
        "description": (
            "【ComputeLab】GET /api/billing/balance — クレジット残高。"
            "使う: 作成前の残高確認。402 Insufficient credits 時は required/balance をユーザーに伝える。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

COMPUTELAB_LIST_INSTANCES_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_list_instances",
        "description": (
            "【ComputeLab】GET /api/instances — 自分のインスタンス一覧。"
            "各要素の id が instance_id。status は PROVISIONING|RUNNING|STOPPED|ERROR|DELETED。"
            "404 時は必ずこのツールで id を再取得（推測禁止）。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

COMPUTELAB_GET_INSTANCE_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_get_instance",
        "description": (
            "【ComputeLab】GET /api/instances/:id または GET …/connection。"
            "詳細: ports[]・publicHostIp・rootPassword・PROVISIONING 判定。"
            "connection_only=true で SSH 情報のみ（address, sshPort, sshCommand）。"
            "PROVISIONING 中は sshPort/sshCommand が null のことがある。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {
                    "type": "string",
                    "description": "一覧/作成応答の id（clx… 等）",
                },
                "connection_only": {
                    "type": "boolean",
                    "description": "true で /connection のみ",
                },
            },
            "required": ["instance_id"],
        },
    },
}

COMPUTELAB_WAIT_RUNNING_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_wait_running",
        "description": (
            "【ComputeLab】create 直後に PROVISIONING のとき、RUNNING になるまでポーリング。"
            "使う: exec / add_port / write_file の前。使わない: 既に RUNNING。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string"},
                "max_wait_sec": {
                    "type": "integer",
                    "description": "最大待機秒（既定180）",
                },
            },
            "required": ["instance_id"],
        },
    },
}

COMPUTELAB_CREATE_INSTANCE_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_create_instance",
        "description": (
            "【ComputeLab】POST /api/instances — 新規作成（課金）。"
            "必須: cpu, memory_mb, disk_gb。任意: image_key（例 ubuntu-24.04）, node_id, ttl_hours, name。"
            "応答 id を以降ずっと使用。rootPassword は作成応答でのみ平文。"
            "status は PROVISIONING → 続けて computelab_wait_running。"
            "402 は残高不足（required/balance を表示）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cpu": {"type": "integer", "description": "vCPU"},
                "memory_mb": {"type": "integer", "description": "メモリ MB"},
                "disk_gb": {"type": "integer", "description": "ディスク GB"},
                "ttl_hours": {"type": "integer"},
                "image_key": {"type": "string", "description": "例 ubuntu-24.04"},
                "node_id": {
                    "type": "string",
                    "description": "catalog.placementNodes[].id",
                },
                "name": {"type": "string"},
            },
            "required": ["cpu", "memory_mb", "disk_gb"],
        },
    },
}

COMPUTELAB_ADD_PORT_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_add_port",
        "description": (
            "【ComputeLab】POST /api/instances/:id/ports — container_port をホストに公開。"
            "応答: hostPort, publicHostIp, publicTcpEndpoint（マイクラ接続は IP:hostPort）。"
            "Web は suggestedPublicUrl。409 は既にマップ済み。"
            "追加後は computelab_exec でアプリ/サーバー再起動。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string"},
                "container_port": {
                    "type": "integer",
                    "description": "コンテナ内ポート（Web 8080、MC 25565）",
                },
                "protocol": {"type": "string", "description": "tcp（既定）"},
                "label": {"type": "string"},
            },
            "required": ["instance_id", "container_port"],
        },
    },
}

COMPUTELAB_INSTANCE_ACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_instance_action",
        "description": (
            "【ComputeLab】POST …/start|stop|restart または DELETE …/instances/:id。"
            "409: Already running/stopped、非 RUNNING で exec 不可。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["start", "stop", "restart", "delete"],
                },
            },
            "required": ["instance_id", "action"],
        },
    },
}

COMPUTELAB_LIST_FILES_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_list_files",
        "description": (
            "【ComputeLab】GET …/data/files — /data 配下一覧（mountInContainer=/data）。"
            "path は相対（例 mc, app）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["instance_id"],
        },
    },
}

COMPUTELAB_READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_read_file",
        "description": (
            "【ComputeLab】GET …/data/text — UTF-8 読取（ops.json 確認等）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string"},
                "path": {"type": "string", "description": "相対パス（例 mc/ops.json）"},
            },
            "required": ["instance_id", "path"],
        },
    },
}

COMPUTELAB_WRITE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_write_file",
        "description": (
            "【ComputeLab】PUT …/data/text — /data 配下に UTF-8 保存。"
            "長いセットアップは .sh を書いて computelab_exec で実行（タイムアウト回避）。"
            "heredoc・/opt 直書き禁止。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string"},
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["instance_id", "path", "content"],
        },
    },
}

COMPUTELAB_MKDIR_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_mkdir",
        "description": "【ComputeLab】POST …/data/mkdir — /data 配下にディレクトリ作成。",
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string"},
                "parent": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["instance_id", "name"],
        },
    },
}

COMPUTELAB_EXEC_TOOL = {
    "type": "function",
    "function": {
        "name": "computelab_exec",
        "description": (
            "【ComputeLab】POST …/exec — RUNNING コンテナ内で実行。"
            "command（argv 配列）か shell の一方。cwd は /data 相対（例 mc）。"
            "timeout_ms 1000〜600000。500/details はコマンドを短く分割して再試行。"
            "常駐: nohup … & または screen -dmS。応答 stdout/stderr/exitCode を根拠に報告。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string"},
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "shell": {"type": "string"},
                "cwd": {
                    "type": "string",
                    "description": "作業ディレクトリ（/data からの相対、例 mc）",
                },
                "timeout_ms": {"type": "integer"},
            },
            "required": ["instance_id"],
        },
    },
}

COMPUTELAB_TOOL_NAMES = frozenset(
    {
        "computelab_catalog",
        "computelab_balance",
        "computelab_list_instances",
        "computelab_get_instance",
        "computelab_wait_running",
        "computelab_create_instance",
        "computelab_add_port",
        "computelab_instance_action",
        "computelab_list_files",
        "computelab_read_file",
        "computelab_write_file",
        "computelab_mkdir",
        "computelab_exec",
    }
)


def build_computelab_tool_list():
    tools = [
        COMPUTELAB_CATALOG_TOOL,
        COMPUTELAB_BALANCE_TOOL,
        COMPUTELAB_LIST_INSTANCES_TOOL,
        COMPUTELAB_GET_INSTANCE_TOOL,
        COMPUTELAB_WAIT_RUNNING_TOOL,
        COMPUTELAB_CREATE_INSTANCE_TOOL,
        COMPUTELAB_ADD_PORT_TOOL,
        COMPUTELAB_INSTANCE_ACTION_TOOL,
        COMPUTELAB_LIST_FILES_TOOL,
        COMPUTELAB_READ_FILE_TOOL,
        COMPUTELAB_WRITE_FILE_TOOL,
        COMPUTELAB_MKDIR_TOOL,
        COMPUTELAB_EXEC_TOOL,
    ]
    return [_wrap_computelab_tool(t) for t in tools]


def computelab_system_prompt_append():
    return (
        "\n\n## ComputeLab [Beta]（Nexgate AI 統合・スポット Docker）\n"
        f"ダッシュボード・API キー発行: {COMPUTELAB_DASHBOARD_URL} （cl_live_…）\n"
        f"API ベース: {COMPUTELAB_API_BASE} （Bearer または X-API-Key）\n"
        "ComputeLab は本サービス内蔵の VPS です。外部ホスティングを web_search しない。\n"
        "「作業を継続」「続きから」は会話内の instance_id で list_instances → 続行。\n\n"
        "### 状態・エラー\n"
        "- status: PROVISIONING → RUNNING（exec 前に wait_running または get_instance で確認）\n"
        "- 402 Insufficient credits → balance/required をそのまま伝える\n"
        "- 409 非 RUNNING / Already running → get_instance で状態確認\n"
        "- 500 Exec failed + details → コマンド短縮・write_file+短い exec・restart 後に再試行\n\n"
        "### 接続情報の書き方（ツール JSON のみ根拠・推測禁止）\n"
        "- instance_id: ツール応答の id をそのまま（clx… / cmp…）\n"
        "- マイクラ TCP: add_port 後の publicTcpEndpoint（publicHostIp:hostPort）\n"
        "- Web: suggestedPublicUrl または publicHostIp:hostPort\n"
        "- SSH: get_instance(connection_only=true) の sshCommand\n\n"
        "### 典型フロー\n"
        "1. catalog（+ balance）→ create_instance → wait_running\n"
        "2. mkdir / write_file（/data/app や /data/mc）→ exec（cwd 指定・短いコマンド）\n"
        "3. add_port(container_port) → exec で再起動・ss/curl で確認\n"
        "4. 完了報告前に exec で ls/cat/screen -ls 等で実測\n\n"
        "### マイクラ（Paper）\n"
        "/data/mc に配置。Java 21。Paper jar + ViaVersion/ViaBackwards。"
        "container_port=25565 → publicTcpEndpoint を接続先に提示。"
        "screen -dmS mc java -jar … nogui。OP は起動後 ops.json または op コマンド。\n\n"
        "### Web アプリ\n"
        "/data/app（templates/static）。Flask は nohup で再起動。"
        "container_port=8080 等 → suggestedPublicUrl。\n\n"
        "「書き込みます」だけで止めない。ツール未実行の「完成しました」禁止。"
        "URL・IP・バージョンにスペースを挿入しない。"
    )


def _parse_json_args(arguments_str):
    try:
        data = json.loads(arguments_str or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _summarize_tool_result(context):
    try:
        data = json.loads(context or "{}")
    except json.JSONDecodeError:
        return (context or "")[:160]
    if data.get("ok"):
        return "ok"
    return str(data.get("error") or "error")[:160]


def execute_computelab_tool(username, tool_name, arguments_str):
    data = _parse_json_args(arguments_str)
    if data is None:
        result = format_tool_result(None, "Invalid tool arguments JSON")
        logger.info(
            "computelab tool user=%s name=%s status=invalid_args",
            username,
            tool_name,
        )
        return result

    if tool_name == "computelab_catalog":
        payload, err = fetch_catalog(username)
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_balance":
        payload, err = fetch_balance(username)
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_list_instances":
        payload, err = list_instances(username)
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_get_instance":
        iid = data.get("instance_id")
        if data.get("connection_only"):
            payload, err = get_instance_connection(username, iid)
        else:
            payload, err = get_instance(username, iid)
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_wait_running":
        payload, err = wait_instance_running(
            username,
            data.get("instance_id"),
            max_wait_sec=data.get("max_wait_sec") or 180,
        )
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_create_instance":
        payload, err = create_instance(
            username,
            cpu=data.get("cpu"),
            memory_mb=data.get("memory_mb"),
            disk_gb=data.get("disk_gb"),
            ttl_hours=data.get("ttl_hours"),
            image_key=data.get("image_key"),
            node_id=data.get("node_id"),
            name=data.get("name"),
        )
        if isinstance(payload, dict) and payload.get("id"):
            payload = dict(payload)
            payload["useThisInstanceId"] = payload["id"]
            payload["nextStep"] = (
                "status が PROVISIONING なら computelab_wait_running を呼んでから exec する"
            )
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_add_port":
        payload, err = add_port(
            username,
            data.get("instance_id"),
            container_port=data.get("container_port"),
            protocol=data.get("protocol"),
            label=data.get("label"),
        )
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_instance_action":
        payload, err = instance_action(
            username, data.get("instance_id"), data.get("action")
        )
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_list_files":
        payload, err = list_data_files(
            username,
            data.get("instance_id"),
            path=data.get("path") or "",
        )
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_read_file":
        payload, err = read_data_text(
            username,
            data.get("instance_id"),
            path=data.get("path"),
        )
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_write_file":
        payload, err = write_data_text(
            username,
            data.get("instance_id"),
            path=data.get("path"),
            content=data.get("content"),
        )
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_mkdir":
        payload, err = mkdir_data(
            username,
            data.get("instance_id"),
            parent=data.get("parent") or "",
            name=data.get("name"),
        )
        result = format_tool_result(payload, err)
    elif tool_name == "computelab_exec":
        payload, err = exec_command(
            username,
            data.get("instance_id"),
            command=data.get("command"),
            shell=data.get("shell"),
            cwd=data.get("cwd"),
            timeout_ms=data.get("timeout_ms"),
        )
        result = format_tool_result(payload, err)
    else:
        result = format_tool_result(None, f"Unknown tool: {tool_name}")

    logger.info(
        "computelab tool user=%s name=%s summary=%s",
        username,
        tool_name,
        _summarize_tool_result(result),
    )
    return result
