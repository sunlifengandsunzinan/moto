import os
from collections.abc import Mapping
from typing import Any


def get_runtime_info(config: Mapping[str, Any]) -> dict[str, Any]:
    host = config["HOST"]
    port = config["PORT"]
    local_host = "127.0.0.1" if host == "0.0.0.0" else host

    return {
        "app_name": "Flask App",
        "environment": os.getenv("APP_ENV", "development").strip().lower(),
        "host": host,
        "port": port,
        "debug": bool(config["DEBUG"]),
        "status": "ok",
        "local_url": f"http://{local_host}:{port}",
        "network_url": f"http://{host}:{port}",
        "endpoints": [
            {"label": "Landing Page", "path": "/", "kind": "page"},
            {"label": "Status Panel", "path": "/status", "kind": "page"},
            {"label": "Status API", "path": "/api/status", "kind": "json"},
        ],
    }
