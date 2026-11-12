"""Stage 2 demonstration: Bottle HTTP API with FileDataStore and real CLI."""

import os
import tempfile
import threading
import time

from src.client import HTTPAPIClient, HTTPAPIError
from src.constants import DEFAULT_HOST, HTTP_NOT_ACCEPTABLE, ONE, ZERO
from src.demo_stage1 import generate_sample_webm
from src.file_store import FileDataStore
from src.server import create_wsgi_server


def _start_server(store, test_mode=False):
    """Start background Bottle WSGI server on an ephemeral local port."""
    srv = create_wsgi_server(
        store, host=DEFAULT_HOST, port=ZERO, test_mode=test_mode
    )
    port = srv.server_address[ONE]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, port


def _demo_header_checks(client):
    """Demonstrate 406 Not Acceptable responses on missing headers."""
    resp1 = client.raw_request("GET", "/public/api/query/session", headers={})
    resp2 = client.raw_request(
        "GET",
        "/public/api/query/session",
        headers={"Accept": "text/json"},
    )
    print(f"Missing Accept -> HTTP {resp1.status_code}")
    print(f"Missing Accept-Language -> HTTP {resp2.status_code}")
    assert resp1.status_code == HTTP_NOT_ACCEPTABLE
    assert resp2.status_code == HTTP_NOT_ACCEPTABLE


def run_demo():
    """Run end-to-end demonstration of all 10 Bottle HTTP API handlers."""
    print("Stage 2 Demonstration: Bottle HTTP API + FileDataStore")
    print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = os.path.join(tmp_dir, "file_db.json")
        webm_path = os.path.join(tmp_dir, "input_demo.webm")
        generate_sample_webm(webm_path, 64, 48, 4, 8, "bars")

        store = FileDataStore(db_file)
        srv, port = _start_server(store, test_mode=False)
        base_url = f"http://{DEFAULT_HOST}:{port}"
        try:
            with HTTPAPIClient(base_url) as client:
                _demo_header_checks(client)
                now_ts = int(time.time())
                s1 = client.public_api_create_session(
                    1, now_ts - 30, "en", "Mozilla/5.0"
                )
                print(f"1.1 create/session -> {s1}")
                s_all = client.public_api_query_session(locale="en")
                print(f"1.3 query/session -> {s_all}")
                s1_upd = client.public_api_correct_session(
                    1, user_agent="Chrome/130"
                )
                print(f"1.4 correct/session -> {s1_upd}")

                res1 = client.public_api_create_request(
                    10, now_ts - 20, webm_path, 1, 1
                )
                ans1 = res1["answer"]
                print(
                    f"2.1 create/request (real CLI) -> status={ans1['status']}"
                    f", cache_hit={ans1['cache_hit']}, "
                    f"b64_len={len(ans1['output'])}"
                )
                res2 = client.public_api_create_request(
                    11, now_ts - 10, webm_path, 1, 1
                )
                print(
                    f"2.1 create/request (cached) -> "
                    f"cache_hit={res2['answer']['cache_hit']}"
                )
                reqs = client.public_api_query_request(1, uid=10)
                print(f"2.3 query/request -> {reqs}")
                req_upd = client.public_api_correct_request(11, triggered=0)
                print(f"2.4 correct/request -> {req_upd}")
                ans_q = client.public_api_query_answer(10)
                print(f"3.1 query/answer -> count={len(ans_q)}")
                report = client.public_api_query_report()
                print(f"4.1 query/report -> count={len(report)}")

                client.public_api_remove_request(11)
                client.public_api_remove_request(10)
                client.public_api_remove_session(1)
                print("1.2 & 2.2 remove/request & remove/session -> OK")
                try:
                    client.public_api_remove_session(999)
                except HTTPAPIError as exc:
                    print(f"Expected error handling -> {exc}")
        finally:
            srv.shutdown()
            srv.server_close()
    print("=" * 60)
    print("Stage 2 Demonstration Completed Successfully.")


if __name__ == "__main__":
    run_demo()
