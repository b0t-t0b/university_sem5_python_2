"""Bottle HTTP API server implementing Table 22 specification."""

import argparse
import json
from wsgiref.simple_server import WSGIRequestHandler, make_server

from bottle import Bottle, HTTPResponse, request

from src.constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SQLITE_URL,
    DEFAULT_STORAGE_PATH,
    ENCODING,
    HTTP_NOT_ACCEPTABLE,
    HTTP_OK,
    JSON_CONTENT_TYPE,
    MODE_FILE,
    MODE_SQLITE,
    REQUIRED_ACCEPT_HEADER,
    REQUIRED_ACCEPT_LANGUAGE,
    STATUS_ERROR,
    STATUS_SUCCESS,
)
from src.file_store import FileDataStore
from src.task_runner import execute_conversion_task


class QuietWSGIHandler(WSGIRequestHandler):
    """WSGI handler suppressing noisy console request logs."""

    def log_message(self, format_str, *args):
        """Override default stderr logging."""
        return None


def _json_response(status_code, payload):
    """Build Bottle HTTPResponse with JSON body and status code."""
    return HTTPResponse(
        body=json.dumps(payload, ensure_ascii=False),
        status=status_code,
        headers={"Content-Type": JSON_CONTENT_TYPE},
    )


def _check_required_headers():
    """Validate mandatory Accept and Accept-Language request headers."""
    if request.headers.get("Accept") != REQUIRED_ACCEPT_HEADER:
        return _json_response(
            HTTP_NOT_ACCEPTABLE,
            {"status": STATUS_ERROR, "error": "Accept must be text/json"},
        )
    if request.headers.get("Accept-Language") != REQUIRED_ACCEPT_LANGUAGE:
        return _json_response(
            HTTP_NOT_ACCEPTABLE,
            {"status": STATUS_ERROR, "error": "Accept-Language must be en"},
        )
    return None


def _execute_handler(action):
    """Validate headers, run endpoint action, and return JSON response."""
    header_err = _check_required_headers()
    if header_err is not None:
        return header_err
    try:
        result = action()
        return _json_response(
            HTTP_OK,
            {"status": STATUS_SUCCESS, "result": result},
        )
    except Exception as exc:
        return _json_response(
            HTTP_OK,
            {"status": STATUS_ERROR, "error": str(exc)},
        )


def _read_json_body():
    """Parse JSON request body as a dictionary."""
    raw = request.body.read()
    if not raw:
        raise ValueError("Empty JSON request body")
    data = json.loads(raw.decode(ENCODING))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _extract_query_filters(allowed_keys):
    """Extract optional query string parameters into a dictionary."""
    filters = {}
    for key in allowed_keys:
        if key in request.query:
            filters[key] = request.query[key]
    return filters


def _register_session_routes(app, store):
    """Register Session API endpoints (1.1 - 1.4)."""

    @app.post("/public/api/create/session")
    def handle_create_session():
        def action():
            q = request.query
            return store.create_session(
                q["uid"], q["timestamp"], q["locale"], q["user_agent"]
            )
        return _execute_handler(action)

    @app.delete("/public/api/remove/session/<uid>")
    def handle_remove_session(uid):
        return _execute_handler(lambda: store.remove_session(uid))

    @app.get("/public/api/query/session")
    def handle_query_session():
        def action():
            keys = ("uid", "timestamp", "locale", "user_agent")
            return store.query_session(_extract_query_filters(keys))
        return _execute_handler(action)

    @app.post("/public/api/correct/session")
    def handle_correct_session():
        def action():
            body = _read_json_body()
            return store.correct_session(body["uid"], body)
        return _execute_handler(action)


def _register_request_routes(app, store, test_mode):
    """Register Request API endpoints (2.1 - 2.4)."""

    @app.post("/public/api/create/request")
    def handle_create_request():
        def action():
            q = request.query
            req_rec = store.create_request(
                q["uid"], q["timestamp"], q["content"],
                q["session"], q["triggered"]
            )
            ans_rec = execute_conversion_task(
                store, req_rec, test_mode=test_mode
            )
            return {"request": req_rec, "answer": ans_rec}
        return _execute_handler(action)

    @app.delete("/public/api/remove/request/<uid>")
    def handle_remove_request(uid):
        return _execute_handler(lambda: store.remove_request(uid))

    @app.get("/public/api/query/request/<session>")
    def handle_query_request(session):
        def action():
            keys = ("uid", "timestamp", "content", "triggered")
            return store.query_request(
                session, _extract_query_filters(keys)
            )
        return _execute_handler(action)

    @app.post("/public/api/correct/request")
    def handle_correct_request():
        def action():
            body = _read_json_body()
            return store.correct_request(body["uid"], body)
        return _execute_handler(action)


def _register_answer_and_report_routes(app, store):
    """Register Answer and Report API endpoints (3.1, 4.1)."""

    @app.get("/public/api/query/answer/<req_uid>")
    def handle_query_answer(req_uid):
        def action():
            keys = (
                "uid", "timestamp", "output",
                "status", "exception", "cache_hit",
            )
            return store.query_answer(
                req_uid, _extract_query_filters(keys)
            )
        return _execute_handler(action)

    @app.get("/public/api/query/report")
    def handle_query_report():
        return _execute_handler(store.query_report)


def create_app(store, test_mode=False):
    """Create configured Bottle application with all Table 22 routes."""
    app = Bottle()
    _register_session_routes(app, store)
    _register_request_routes(app, store, test_mode)
    _register_answer_and_report_routes(app, store)
    return app


def create_wsgi_server(store, host=DEFAULT_HOST, port=DEFAULT_PORT,
                       test_mode=False):
    """Create WSGIRef server wrapping the Bottle HTTP API application."""
    app = create_app(store, test_mode=test_mode)
    return make_server(host, port, app, handler_class=QuietWSGIHandler)


def build_store(db_mode, db_path=None):
    """Instantiate configured data store backend (file or sqlite)."""
    if db_mode == MODE_SQLITE:
        from src.sqlite_store import SQLiteDataStore
        target = db_path or DEFAULT_SQLITE_URL
        return SQLiteDataStore(target)
    target = db_path or DEFAULT_STORAGE_PATH
    return FileDataStore(target)


def parse_args(argv=None):
    """Parse server CLI configuration arguments."""
    parser = argparse.ArgumentParser(
        description="Run Bottle HTTP API server for Variant 22."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--db-mode",
        choices=(MODE_FILE, MODE_SQLITE),
        default=MODE_SQLITE,
    )
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--test-mode", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    """Run standalone Bottle HTTP API server until interrupted."""
    args = parse_args(argv)
    store = build_store(args.db_mode, args.db_path)
    server = create_wsgi_server(
        store, host=args.host, port=args.port, test_mode=args.test_mode
    )
    print(
        f"Bottle HTTP API listening on http://{args.host}:{args.port} "
        f"(db={args.db_mode}, test_mode={args.test_mode})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down HTTP API server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
