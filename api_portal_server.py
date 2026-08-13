import os

os.environ["NEXGATE_APP_MODE"] = "api_portal"
os.environ.setdefault("FLASK_PORT", "5001")
os.environ.setdefault("API_INTERNAL_URL", "http://127.0.0.1:5002")
os.environ.setdefault("API_PORTAL_BASE_URL", "http://127.0.0.1:5001")
os.environ.setdefault("FRONTEND_BASE_URL", "http://127.0.0.1:5000")

from app import _env_bool, app

if __name__ == "__main__":
    debug = _env_bool("FLASK_DEBUG", True)
    use_reloader = _env_bool("FLASK_USE_RELOADER", False)
    app.run(
        debug=debug,
        use_reloader=use_reloader,
        threaded=True,
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5001")),
    )
