import json
import logging
import os
import threading
from pathlib import Path
from urllib.parse import urlparse

import httpx
from flask import Response, jsonify, request, stream_with_context

logger = logging.getLogger(__name__)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}

SERVER_MODE_COMBINED = "combined"
SERVER_MODE_API = "api"
SERVER_MODE_FRONTEND = "frontend"
SERVER_MODE_API_PORTAL = "api_portal"

INTERNAL_API_KEY_HEADER = "X-Nexgate-Internal-Key"
SYSTEM_HEALTH_PATH = "/api/system/health"


def get_server_mode() -> str:
    mode = (os.getenv("NEXGATE_APP_MODE") or SERVER_MODE_COMBINED).strip().lower()
    if mode in (
        SERVER_MODE_API,
        SERVER_MODE_FRONTEND,
        SERVER_MODE_API_PORTAL,
    ):
        return mode
    return SERVER_MODE_COMBINED


def internal_api_key() -> str:
    return (os.getenv("NEXGATE_INTERNAL_API_KEY") or "").strip()


def _service_urls_from_config() -> dict[str, str]:
    path = Path(__file__).parent / "data" / "system_config.json"
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    raw = data.get("service_urls") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}

    def clean(value: object) -> str:
        return str(value or "").strip().rstrip("/")

    return {
        "frontend": clean(raw.get("frontend_base_url")),
        "api_portal": clean(raw.get("api_portal_base_url")),
        "api": clean(raw.get("api_base_url")),
    }


def public_base_url() -> str:
    configured = _service_urls_from_config().get("frontend", "")
    if not configured:
        configured = (
            os.getenv("PUBLIC_BASE_URL") or os.getenv("FRONTEND_BASE_URL") or ""
        ).strip().rstrip("/")
    if configured:
        return configured
    try:
        return (request.url_root or "http://127.0.0.1:5000").rstrip("/")
    except RuntimeError:
        return "http://127.0.0.1:5000"


def api_portal_base_url() -> str:
    configured = _service_urls_from_config().get("api_portal", "")
    if not configured:
        configured = (os.getenv("API_PORTAL_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return "http://127.0.0.1:5001"


def public_api_base_url() -> str:
    configured = _service_urls_from_config().get("api", "")
    if not configured:
        configured = (os.getenv("PUBLIC_API_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return api_internal_base_url()


def public_page_url(path: str) -> str:
    base = public_base_url()
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def api_internal_base_url() -> str:
    return (os.getenv("API_INTERNAL_URL") or "http://127.0.0.1:5002").strip().rstrip("/")


def api_internal_ws_base_url() -> str:
    configured = (os.getenv("API_INTERNAL_WS_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    parsed = urlparse(api_internal_base_url())
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc or "127.0.0.1:5002"
    return f"{scheme}://{host}"


def _api_proxy_target(path: str) -> str:
    suffix = path[5:] if path.startswith("/api/") else ""
    target = f"{api_internal_base_url()}/api"
    if suffix:
        target = f"{target}/{suffix}"
    if request.query_string:
        target = f"{target}?{request.query_string.decode('latin-1')}"
    return target


def _forward_request_headers(*, attach_internal_key: bool = False) -> dict[str, str]:
    headers = {}
    for key in (
        "Cookie",
        "Content-Type",
        "Accept",
        "Accept-Language",
        "Authorization",
        "X-Requested-With",
        "Range",
    ):
        value = request.headers.get(key)
        if value:
            headers[key] = value
    if attach_internal_key:
        key = internal_api_key()
        if key:
            headers[INTERNAL_API_KEY_HEADER] = key
    return headers


def _filtered_response_headers(response: httpx.Response) -> list[tuple[str, str]]:
    out = []
    for key, value in response.headers.multi_items():
        if key.lower() in HOP_BY_HOP_HEADERS:
            continue
        out.append((key, value))
    return out


def _needs_streaming_proxy() -> bool:
    if request.method != "POST":
        return False
    path = (request.path or "").rstrip("/")
    return path in ("/api/chat", "/api/projects/chat")


def _proxy_http(target_url: str, *, attach_internal_key: bool = False) -> Response:
    headers = _forward_request_headers(attach_internal_key=attach_internal_key)
    timeout = httpx.Timeout(None, connect=30.0)
    body = request.get_data()

    try:
        if not _needs_streaming_proxy():
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                upstream = client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                )
                return Response(
                    upstream.content,
                    status=upstream.status_code,
                    headers=_filtered_response_headers(upstream),
                )

        client = httpx.Client(timeout=timeout, follow_redirects=False)
        try:
            upstream_request = client.build_request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )
            upstream = client.send(upstream_request, stream=True)

            @stream_with_context
            def generate():
                try:
                    for chunk in upstream.iter_bytes():
                        if chunk:
                            yield chunk
                finally:
                    upstream.close()
                    client.close()

            return Response(
                generate(),
                status=upstream.status_code,
                headers=_filtered_response_headers(upstream),
            )
        except Exception:
            client.close()
            raise
    except httpx.RequestError as exc:
        logger.warning("API proxy failed for %s: %s", target_url, exc)
        return Response(
            '{"error":"APIサーバーに接続できません"}',
            status=502,
            mimetype="application/json",
        )


def _bridge_websocket(client_ws, backend_path: str) -> None:
    from simple_websocket import Client as WSClient

    cookie = client_ws.environ.get("HTTP_COOKIE", "")
    headers = [("Cookie", cookie)] if cookie else None
    backend_url = f"{api_internal_ws_base_url()}{backend_path}"
    try:
        backend = WSClient(backend_url, headers=headers)
    except Exception as exc:
        logger.warning("WebSocket proxy connect failed for %s: %s", backend_url, exc)
        client_ws.close(1011, "Backend unavailable")
        return

    closed = threading.Event()

    def relay(source, destination):
        try:
            while not closed.is_set():
                message = source.receive()
                if message is None:
                    break
                destination.send(message)
        except Exception:
            pass
        finally:
            closed.set()
            try:
                destination.close()
            except Exception:
                pass

    client_to_backend = threading.Thread(
        target=relay, args=(client_ws, backend), daemon=True
    )
    backend_to_client = threading.Thread(
        target=relay, args=(backend, client_ws), daemon=True
    )
    client_to_backend.start()
    backend_to_client.start()
    client_to_backend.join()
    backend_to_client.join()
    try:
        backend.close()
    except Exception:
        pass


def register_ws_proxy(app, *, projects: bool = True, admin_sessions: bool = False, chat: bool = False) -> None:
    from flask_sock import Sock

    sock = Sock(app)

    if projects:

        @sock.route("/ws/projects")
        def proxy_projects_ws(ws):
            _bridge_websocket(ws, "/ws/projects")

    if chat:

        @sock.route("/ws/chat")
        def proxy_chat_ws(ws):
            _bridge_websocket(ws, "/ws/chat")

    if admin_sessions:

        @sock.route("/ws/admin/sessions")
        def proxy_admin_sessions_ws(ws):
            _bridge_websocket(ws, "/ws/admin/sessions")


def _is_api_portal_page(path: str) -> bool:
    if path.startswith("/static"):
        return True
    if path in ("/", "/login"):
        return True
    if path == "/auth/sso":
        return True
    if path == "/dash" or path.startswith("/dash/"):
        return True
    if path == "/portal" or path.startswith("/portal/"):
        return True
    return False


def _is_api_portal_proxy_path(path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if path.startswith("/api/auth/") or path == "/api/auth/login":
        return True
    if path.startswith("/api/developer/"):
        return True
    return path in (
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/logout",
        "/api/auth/me",
        "/api/auth/check-username",
    )


def apply_server_mode(app) -> None:
    mode = get_server_mode()
    if mode == SERVER_MODE_COMBINED:
        return

    if mode == SERVER_MODE_API:

        @app.before_request
        def api_mode_guard():
            path = request.path or ""
            if (
                path.startswith("/api")
                or path.startswith("/ws")
                or path.startswith("/v1")
                or path.startswith("/static")
            ):
                return None
            return jsonify({"error": "Not found"}), 404

        @app.after_request
        def api_v1_cors(response):
            path = request.path or ""
            if not path.startswith("/v1"):
                return response
            origin = (os.getenv("PUBLIC_API_CORS_ORIGIN") or "*").strip()
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type"
            )
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            return response

        return

    if mode == SERVER_MODE_API_PORTAL:

        @app.before_request
        def api_portal_guard():
            path = request.path or ""
            if path == SYSTEM_HEALTH_PATH:
                return None
            if path.startswith("/api/"):
                if _is_api_portal_proxy_path(path):
                    return _proxy_http(_api_proxy_target(path))
                return jsonify({"error": "Not found"}), 404
            if _is_api_portal_page(path):
                return None
            return jsonify({"error": "Not found"}), 404

        return

    @app.before_request
    def frontend_api_proxy():
        path = request.path or ""
        if path.startswith("/portal") or path.startswith("/dash") or path.startswith("/auth/sso"):
            return jsonify({"error": "Not found"}), 404
        if path == SYSTEM_HEALTH_PATH:
            return None
        if not path.startswith("/api"):
            return None
        return _proxy_http(_api_proxy_target(path), attach_internal_key=True)
