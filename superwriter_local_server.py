from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import cast
from wsgiref.simple_server import make_server

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.web import BookCommandCenterWSGIApp
from apps.web.command_center import FrontendMode
from core.runtime import SuperwriterApplicationService


def _server_port() -> int:
    raw_port = os.environ.get("SUPERWRITER_PORT", "18080").strip()
    try:
        port = int(raw_port)
    except ValueError as error:
        raise RuntimeError(f"Invalid SUPERWRITER_PORT: {raw_port}") from error
    if port <= 0 or port > 65535:
        raise RuntimeError(f"SUPERWRITER_PORT must be between 1 and 65535, got {port}")
    return port


def _db_path() -> Path:
    configured = os.environ.get("SUPERWRITER_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (REPO_ROOT / ".superwriter" / "canonical.sqlite3").resolve()


def _frontend_mode() -> str:
    configured = os.environ.get("SUPERWRITER_FRONTEND_MODE", "legacy").strip().lower()
    supported = {"legacy", "hybrid", "spa"}
    if configured not in supported:
        choices = "|".join(sorted(supported))
        raise RuntimeError(f"SUPERWRITER_FRONTEND_MODE must be one of {choices}, got {configured}")
    return configured


def _frontend_dist_path() -> Path:
    return (REPO_ROOT / "apps" / "frontend" / "dist").resolve()


def _preferred_command_center_url(service: SuperwriterApplicationService, base_url: str) -> str | None:
    contexts = service.list_workspace_contexts()
    if len(contexts) != 1:
        return None
    context = contexts[0]
    query = f"?project_id={context.project_id}"
    if context.novel_id is not None:
        query = f"{query}&novel_id={context.novel_id}"
    return f"{base_url}/command-center{query}"


def main() -> None:
    host = "127.0.0.1"
    port = _server_port()
    db_path = _db_path()
    frontend_mode = _frontend_mode()
    frontend_dist_path = _frontend_dist_path()
    service = SuperwriterApplicationService.for_sqlite(db_path)
    app = BookCommandCenterWSGIApp(
        service,
        frontend_mode=cast(FrontendMode, frontend_mode),
        frontend_dist_dir=frontend_dist_path,
    )
    base_url = f"http://{host}:{port}"
    preferred_url = _preferred_command_center_url(service, base_url)

    print("Superwriter local server", flush=True)
    print(f"Database: {db_path}", flush=True)
    print(f"Frontend mode: {frontend_mode}", flush=True)
    if frontend_mode != "legacy":
        print(f"Frontend dist: {frontend_dist_path}", flush=True)
        print(f"Legacy shell: {base_url}/legacy/", flush=True)
    print(f"Open: {base_url}/", flush=True)
    if preferred_url is not None:
        print(f"Command Center: {preferred_url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    try:
        with make_server(host, port, app) as server:
            server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping Superwriter local server.", flush=True)


if __name__ == "__main__":
    main()
