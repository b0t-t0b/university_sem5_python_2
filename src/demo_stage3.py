"""Stage 3 demonstration: Bottle HTTP API backed by SQLite + SQLAlchemy."""

import os
import tempfile
import threading
import time

from src.client import HTTPAPIClient
from src.constants import DEFAULT_HOST, ONE, ZERO
from src.demo_stage1 import generate_sample_webm
from src.server import create_wsgi_server
from src.sqlite_store import SQLiteDataStore


def _execute_sqlite_demo_calls(client, webm_path):
    """Create sessions, execute cached requests, and print Formula 22."""
    now_ts = int(time.time())
    s1 = client.public_api_create_session(
        1, now_ts - 20, "en", "SQLAlchemy-Demo"
    )
    print(f"Created Session in SQLite: {s1}")
    s2 = client.public_api_create_session(2, now_ts - 800, "ru", "Old-Client")
    print(f"Created Old Session in SQLite: {s2}")

    r1 = client.public_api_create_request(10, now_ts - 10, webm_path, 1, 1)
    print(
        f"Created Request 10 -> status={r1['answer']['status']}, "
        f"cache_hit={r1['answer']['cache_hit']}"
    )
    r2 = client.public_api_create_request(11, now_ts - 5, webm_path, 2, 1)
    print(
        f"Created Request 11 -> status={r2['answer']['status']}, "
        f"cache_hit={r2['answer']['cache_hit']}"
    )
    report = client.public_api_query_report()
    print(f"Formula (22) Report from SQLite: {report}")


def run_demo():
    """Demonstrate HTTP API with SQLiteDataStore and real WebM->GIF CLI."""
    print("Stage 3 Demonstration: Bottle HTTP API + SQLite (SQLAlchemy)")
    print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_url = f"sqlite:///{os.path.join(tmp_dir, 'demo.db')}"
        webm_path = os.path.join(tmp_dir, "stage3_clip.webm")
        generate_sample_webm(webm_path, 64, 48, 5, 10, "pulse")
        store = SQLiteDataStore(db_url)
        srv = create_wsgi_server(
            store, host=DEFAULT_HOST, port=ZERO, test_mode=False
        )
        port = srv.server_address[ONE]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with HTTPAPIClient(f"http://{DEFAULT_HOST}:{port}") as client:
                _execute_sqlite_demo_calls(client, webm_path)
        finally:
            srv.shutdown()
            srv.server_close()
            store.dispose()
    print("=" * 60)
    print("Stage 3 Demonstration Completed Successfully.")


if __name__ == "__main__":
    run_demo()
