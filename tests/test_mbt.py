"""Model-Based Testing (MBT) for HTTP API using Hypothesis."""

import os
import tempfile
import threading
import time

from hypothesis import given, settings
from hypothesis.stateful import (
    Bundle,
    RuleBasedStateMachine,
    multiple,
    rule,
    run_state_machine_as_test,
)
import hypothesis.strategies as st

from src.client import HTTPAPIClient, HTTPAPIError
from src.constants import (
    DEFAULT_HOST,
    HTTP_NOT_ACCEPTABLE,
    ONE,
    QUERY_TIME_WINDOW_SECONDS,
    REQUIRED_ACCEPT_HEADER,
    TASK_STATUS_ERROR,
    TASK_STATUS_OK,
    ZERO,
)
from src.demo_stage1 import generate_sample_webm
from src.file_store import FileDataStore
from src.server import create_wsgi_server
from src.sqlite_store import SQLiteDataStore
from src.task_runner import execute_conversion_task

_TMP_DIR = None
_STORE = None
_SERVER = None
_THREAD = None
_BASE_URL = ""


def setup_module():
    """Start background Bottle HTTP API server with SQLite for MBT."""
    global _TMP_DIR, _STORE, _SERVER, _THREAD, _BASE_URL
    _TMP_DIR = tempfile.TemporaryDirectory()
    db_file = os.path.join(_TMP_DIR.name, "mbt_sqlite.db")
    _STORE = SQLiteDataStore(f"sqlite:///{db_file}")
    _SERVER = create_wsgi_server(
        _STORE, host=DEFAULT_HOST, port=ZERO, test_mode=True
    )
    port = _SERVER.server_address[ONE]
    _BASE_URL = f"http://{DEFAULT_HOST}:{port}"
    _THREAD = threading.Thread(target=_SERVER.serve_forever, daemon=True)
    _THREAD.start()


def teardown_module():
    """Shut down Bottle server, dispose SQLite engine, clean temp dir."""
    if _SERVER is not None:
        _SERVER.shutdown()
        _SERVER.server_close()
    if _STORE is not None:
        _STORE.dispose()
    if _TMP_DIR is not None:
        _TMP_DIR.cleanup()


def _matches(rec, filters):
    """Return True if record matches every non-None value in filters."""
    for key, val in filters.items():
        if val is not None and rec.get(key) != val:
            return False
    return True


class ReferenceModel:
    """Independent reference in-memory model for HTTP API verification."""

    def __init__(self):
        """Initialize empty model tables."""
        self.sessions = {}
        self.requests = {}
        self.answers = {}
        self._ans_seq = ZERO

    def clear(self):
        """Reset all reference model tables."""
        self.sessions.clear()
        self.requests.clear()
        self.answers.clear()
        self._ans_seq = ZERO

    def create_session(self, uid, ts, locale, ua):
        """Model create_session endpoint."""
        if uid in self.sessions:
            raise ValueError(f"Session {uid} exists")
        rec = {
            "uid": int(uid),
            "timestamp": int(ts),
            "locale": str(locale),
            "user_agent": str(ua),
        }
        self.sessions[uid] = rec
        return dict(rec)

    def remove_session(self, uid):
        """Model remove_session endpoint with FK check."""
        if uid not in self.sessions:
            raise KeyError(f"Session {uid} not found")
        for req in self.requests.values():
            if req["session"] == uid:
                raise ValueError("Session referenced")
        del self.sessions[uid]
        return True

    def query_session(self, filters):
        """Model query_session endpoint."""
        rows = [
            dict(rec)
            for rec in self.sessions.values()
            if _matches(rec, filters)
        ]
        return sorted(rows, key=lambda item: item["uid"])

    def correct_session(self, uid, updates):
        """Model correct_session endpoint."""
        if uid not in self.sessions:
            raise KeyError(f"Session {uid} not found")
        cur = dict(self.sessions[uid])
        for field, cast_fn in (
            ("timestamp", int),
            ("locale", str),
            ("user_agent", str),
        ):
            if updates.get(field) is not None:
                cur[field] = cast_fn(updates[field])
        self.sessions[uid] = cur
        return dict(cur)

    def _find_cached_output(self, content):
        """Find cached successful output for matching request content."""
        for ans in sorted(self.answers.values(), key=lambda x: x["uid"]):
            req = self.requests.get(ans["request"])
            if req is not None and req["content"] == content:
                return ans["output"]
        return None

    def create_request(self, uid, ts, content, session, triggered):
        """Model create_request endpoint including test-mode Answer."""
        if uid in self.requests:
            raise ValueError(f"Request {uid} exists")
        if session not in self.sessions:
            raise ValueError(f"Session {session} missing")
        req = {
            "uid": int(uid),
            "timestamp": int(ts),
            "content": str(content),
            "session": int(session),
            "triggered": int(triggered),
        }
        cached_out = self._find_cached_output(req["content"])
        hit = ONE if cached_out is not None else ZERO
        output = cached_out if hit else f"test-gif:{req['content']}"
        self.requests[uid] = req
        self._ans_seq += ONE
        ans = {
            "uid": self._ans_seq,
            "timestamp": req["timestamp"],
            "output": output,
            "status": TASK_STATUS_OK,
            "exception": "",
            "request": req["uid"],
            "cache_hit": hit,
        }
        self.answers[self._ans_seq] = ans
        return {"request": dict(req), "answer": dict(ans)}

    def remove_request(self, uid):
        """Model remove_request endpoint with answer cascade."""
        if uid not in self.requests:
            raise KeyError(f"Request {uid} not found")
        to_del = [
            a_id for a_id, ans in self.answers.items() if ans["request"] == uid
        ]
        for a_id in to_del:
            del self.answers[a_id]
        del self.requests[uid]
        return True

    def query_request(self, session, filters):
        """Model query_request endpoint."""
        rows = [
            dict(rec)
            for rec in self.requests.values()
            if rec["session"] == session and _matches(rec, filters)
        ]
        return sorted(rows, key=lambda item: item["uid"])

    def correct_request(self, uid, updates):
        """Model correct_request endpoint."""
        if uid not in self.requests:
            raise KeyError(f"Request {uid} not found")
        cur = dict(self.requests[uid])
        if updates.get("session") is not None:
            new_sess = int(updates["session"])
            if new_sess not in self.sessions:
                raise ValueError(f"Session {new_sess} missing")
            cur["session"] = new_sess
        for field, cast_fn in (
            ("timestamp", int),
            ("content", str),
            ("triggered", int),
        ):
            if updates.get(field) is not None:
                cur[field] = cast_fn(updates[field])
        self.requests[uid] = cur
        return dict(cur)

    def query_answer(self, request_uid, filters):
        """Model query_answer endpoint."""
        rows = [
            dict(rec)
            for rec in self.answers.values()
            if rec["request"] == request_uid and _matches(rec, filters)
        ]
        return sorted(rows, key=lambda item: item["uid"])

    def query_report(self, now):
        """Model report relational algebra query (formula 22)."""
        thresh = int(now) - QUERY_TIME_WINDOW_SECONDS
        recent = {
            s["uid"]: s
            for s in self.sessions.values()
            if s["timestamp"] >= thresh
        }
        rows = []
        for req in sorted(self.requests.values(), key=lambda x: x["uid"]):
            sess = recent.get(req["session"])
            loc = None if sess is None else sess["locale"]
            rows.append({"content": req["content"], "locale": loc})
        return rows


def _ts_strategy():
    """Return timestamp strategy separated safely around 6-min window."""
    now = int(time.time())
    return st.sampled_from([now - 60, now - 900])


class HTTPAPIStateMachine(RuleBasedStateMachine):
    """Hypothesis RuleBasedStateMachine comparing Bottle API to model."""

    sessions = Bundle("sessions")
    requests = Bundle("requests")

    def __init__(self):
        """Initialize client and reset store and reference model."""
        super().__init__()
        self.model = ReferenceModel()
        self.client = HTTPAPIClient(_BASE_URL)
        _STORE.clear_all()
        self.model.clear()

    def teardown(self):
        """Close HTTP client session after machine run."""
        self.client.close()

    @rule(
        target=sessions,
        uid=st.integers(min_value=1, max_value=6),
        ts=_ts_strategy(),
        locale=st.sampled_from(["ru", "en", "de"]),
        ua=st.sampled_from(["Chrome", "Firefox"]),
    )
    def r_create_session(self, uid, ts, locale, ua):
        """Test 1.1 POST /public/api/create/session."""
        expected_err = False
        try:
            exp = self.model.create_session(uid, ts, locale, ua)
        except (ValueError, KeyError):
            expected_err = True
            exp = None
        try:
            act = self.client.public_api_create_session(uid, ts, locale, ua)
            assert not expected_err
            assert act == exp
            return uid
        except HTTPAPIError:
            assert expected_err
            return multiple()

    @rule(uid=st.integers(min_value=1, max_value=6))
    def r_remove_session(self, uid):
        """Test 1.2 DELETE /public/api/remove/session/:uid."""
        expected_err = False
        try:
            self.model.remove_session(uid)
        except (ValueError, KeyError):
            expected_err = True
        try:
            act = self.client.public_api_remove_session(uid)
            assert not expected_err
            assert act is True
        except HTTPAPIError:
            assert expected_err

    @rule(
        uid=st.one_of(st.none(), st.integers(min_value=1, max_value=6)),
        locale=st.one_of(st.none(), st.sampled_from(["ru", "en", "de"])),
    )
    def r_query_session(self, uid, locale):
        """Test 1.3 GET /public/api/query/session."""
        filters = {"uid": uid, "locale": locale}
        exp = self.model.query_session(filters)
        act = self.client.public_api_query_session(**filters)
        assert act == exp

    @rule(
        uid=st.integers(min_value=1, max_value=6),
        ts=st.one_of(st.none(), _ts_strategy()),
        locale=st.one_of(st.none(), st.sampled_from(["ru", "en", "fr"])),
        ua=st.one_of(st.none(), st.sampled_from(["Safari", "Edge"])),
    )
    def r_correct_session(self, uid, ts, locale, ua):
        """Test 1.4 POST /public/api/correct/session."""
        updates = {"timestamp": ts, "locale": locale, "user_agent": ua}
        expected_err = False
        try:
            exp = self.model.correct_session(uid, updates)
        except (ValueError, KeyError):
            expected_err = True
            exp = None
        try:
            act = self.client.public_api_correct_session(uid, **updates)
            assert not expected_err
            assert act == exp
        except HTTPAPIError:
            assert expected_err

    @rule(
        target=requests,
        uid=st.integers(min_value=1, max_value=6),
        ts=_ts_strategy(),
        content=st.sampled_from(["clip1.webm", "clip2.webm"]),
        session=st.integers(min_value=1, max_value=6),
        triggered=st.integers(min_value=0, max_value=1),
    )
    def r_create_request(self, uid, ts, content, session, triggered):
        """Test 2.1 POST /public/api/create/request."""
        expected_err = False
        try:
            exp = self.model.create_request(
                uid, ts, content, session, triggered
            )
        except (ValueError, KeyError):
            expected_err = True
            exp = None
        try:
            act = self.client.public_api_create_request(
                uid, ts, content, session, triggered
            )
            assert not expected_err
            assert act["request"] == exp["request"]
            assert act["answer"]["output"] == exp["answer"]["output"]
            assert act["answer"]["cache_hit"] == exp["answer"]["cache_hit"]
            return uid
        except HTTPAPIError:
            assert expected_err
            return multiple()

    @rule(uid=st.integers(min_value=1, max_value=6))
    def r_remove_request(self, uid):
        """Test 2.2 DELETE /public/api/remove/request/:uid."""
        expected_err = False
        try:
            self.model.remove_request(uid)
        except (ValueError, KeyError):
            expected_err = True
        try:
            act = self.client.public_api_remove_request(uid)
            assert not expected_err
            assert act is True
        except HTTPAPIError:
            assert expected_err

    @rule(
        session=st.integers(min_value=1, max_value=6),
        uid=st.one_of(st.none(), st.integers(min_value=1, max_value=6)),
        content=st.one_of(
            st.none(), st.sampled_from(["clip1.webm", "clip2.webm"])
        ),
    )
    def r_query_request(self, session, uid, content):
        """Test 2.3 GET /public/api/query/request/:session."""
        filters = {"uid": uid, "content": content}
        exp = self.model.query_request(session, filters)
        act = self.client.public_api_query_request(session, **filters)
        assert act == exp

    @rule(
        uid=st.integers(min_value=1, max_value=6),
        ts=st.one_of(st.none(), _ts_strategy()),
        content=st.one_of(
            st.none(), st.sampled_from(["clip1.webm", "clip3.webm"])
        ),
        session=st.one_of(st.none(), st.integers(min_value=1, max_value=6)),
        triggered=st.one_of(st.none(), st.integers(min_value=0, max_value=1)),
    )
    def r_correct_request(self, uid, ts, content, session, triggered):
        """Test 2.4 POST /public/api/correct/request."""
        updates = {
            "timestamp": ts,
            "content": content,
            "session": session,
            "triggered": triggered,
        }
        expected_err = False
        try:
            exp = self.model.correct_request(uid, updates)
        except (ValueError, KeyError):
            expected_err = True
            exp = None
        try:
            act = self.client.public_api_correct_request(uid, **updates)
            assert not expected_err
            assert act == exp
        except HTTPAPIError:
            assert expected_err

    @rule(
        req_uid=st.integers(min_value=1, max_value=6),
        cache_hit=st.one_of(st.none(), st.integers(min_value=0, max_value=1)),
    )
    def r_query_answer(self, req_uid, cache_hit):
        """Test 3.1 GET /public/api/query/answer/:request."""
        filters = {"cache_hit": cache_hit}
        exp = self.model.query_answer(req_uid, filters)
        act = self.client.public_api_query_answer(req_uid, **filters)
        assert len(act) == len(exp)
        for act_row, exp_row in zip(act, exp):
            assert act_row["request"] == exp_row["request"]
            assert act_row["output"] == exp_row["output"]
            assert act_row["cache_hit"] == exp_row["cache_hit"]

    @rule()
    def r_query_report(self):
        """Test 4.1 GET /public/api/query/report."""
        exp = self.model.query_report(int(time.time()))
        act = self.client.public_api_query_report()
        assert act == exp

    @rule(
        accept=st.sampled_from(
            ["", "application/json", REQUIRED_ACCEPT_HEADER]
        ),
        lang=st.sampled_from(["", "ru", "en"]),
    )
    def r_header_validation(self, accept, lang):
        """Test mandatory Accept and Accept-Language 406 handling."""
        headers = {}
        if accept:
            headers["Accept"] = accept
        if lang:
            headers["Accept-Language"] = lang
        resp = self.client.raw_request(
            "GET", "/public/api/query/session", headers=headers
        )
        if accept != REQUIRED_ACCEPT_HEADER or lang != "en":
            assert resp.status_code == HTTP_NOT_ACCEPTABLE
        else:
            assert resp.status_code != HTTP_NOT_ACCEPTABLE


def test_http_api_model_based():
    """Execute Hypothesis RuleBasedStateMachine against Bottle HTTP API."""
    run_state_machine_as_test(
        HTTPAPIStateMachine,
        settings=settings(
            max_examples=80,
            stateful_step_count=30,
            deadline=None,
        ),
    )


@given(should_succeed=st.booleans(), use_sqlite=st.booleans())
@settings(max_examples=8, deadline=None)
def test_real_subprocess_conversion_hypothesis(should_succeed, use_sqlite):
    """Verify real subprocess WebM->GIF task execution on both stores."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        if use_sqlite:
            db_file = os.path.join(tmp_dir, "real.db")
            store = SQLiteDataStore(f"sqlite:///{db_file}")
        else:
            store = FileDataStore(os.path.join(tmp_dir, "real_db.json"))
        try:
            store.create_session(1, 1000, "en", "TestAgent")
            if should_succeed:
                webm_path = os.path.join(tmp_dir, "real.webm")
                generate_sample_webm(webm_path, 32, 24, 2, 5, "bars")
                req1 = store.create_request(1, 1001, webm_path, 1, 1)
                ans1 = execute_conversion_task(store, req1, test_mode=False)
                assert ans1["status"] == TASK_STATUS_OK
                assert ans1["cache_hit"] == ZERO
                req2 = store.create_request(2, 1002, webm_path, 1, 1)
                ans2 = execute_conversion_task(store, req2, test_mode=False)
                assert ans2["cache_hit"] == ONE
            else:
                bad_file = os.path.join(tmp_dir, "missing.webm")
                req_bad = store.create_request(3, 1003, bad_file, 1, 1)
                ans_bad = execute_conversion_task(
                    store, req_bad, test_mode=False
                )
                assert ans_bad["status"] == TASK_STATUS_ERROR
                assert ans_bad["exception"] != ""
        finally:
            if hasattr(store, "dispose"):
                store.dispose()
