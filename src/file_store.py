"""File-based JSON database management system for Variant 22."""

import json
import os
import threading
import time

from src.constants import (
    DEFAULT_STORAGE_PATH,
    ENCODING,
    ONE,
    QUERY_TIME_WINDOW_SECONDS,
    TASK_STATUS_OK,
)


def _matches_filters(record, filters, cast_map):
    """Return True if record matches every provided filter value."""
    if not filters:
        return True
    for key, val in filters.items():
        if record.get(key) != cast_map[key](val):
            return False
    return True


class FileDataStore:
    """Thread-safe disk-backed JSON file DBMS for Session/Request/Answer."""

    def __init__(self, storage_path=DEFAULT_STORAGE_PATH):
        """Initialize file store path and lock."""
        self.storage_path = storage_path
        self._lock = threading.Lock()
        self._ensure_file()

    def _empty_state(self):
        """Return empty database dictionary structure."""
        return {"sessions": {}, "requests": {}, "answers": {}}

    def _ensure_file(self):
        """Create storage JSON file if it does not yet exist."""
        with self._lock:
            if not os.path.exists(self.storage_path):
                self._write_state(self._empty_state())

    def _read_state(self):
        """Load complete database state from JSON file on disk."""
        if not os.path.exists(self.storage_path):
            return self._empty_state()
        with open(self.storage_path, "r", encoding=ENCODING) as file_obj:
            return json.load(file_obj)

    def _write_state(self, state):
        """Persist complete database state atomically to JSON file."""
        parent = os.path.dirname(self.storage_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = f"{self.storage_path}.tmp"
        with open(tmp_path, "w", encoding=ENCODING) as file_obj:
            json.dump(state, file_obj, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.storage_path)

    def clear_all(self):
        """Remove all records from all tables on disk."""
        with self._lock:
            self._write_state(self._empty_state())

    def create_session(self, uid, timestamp, locale, user_agent):
        """Create and persist a new Session record."""
        key = str(int(uid))
        with self._lock:
            state = self._read_state()
            if key in state["sessions"]:
                raise ValueError(f"Session {key} already exists")
            record = {
                "uid": int(uid),
                "timestamp": int(timestamp),
                "locale": str(locale),
                "user_agent": str(user_agent),
            }
            state["sessions"][key] = record
            self._write_state(state)
            return dict(record)

    def remove_session(self, uid):
        """Delete Session by uid if not referenced by any Request."""
        key = str(int(uid))
        int_uid = int(uid)
        with self._lock:
            state = self._read_state()
            if key not in state["sessions"]:
                raise KeyError(f"Session {key} not found")
            for req in state["requests"].values():
                if req["session"] == int_uid:
                    raise ValueError(f"Session {key} referenced by request")
            del state["sessions"][key]
            self._write_state(state)
            return True

    def query_session(self, filters=None):
        """Return Session records matching optional field filters."""
        cast_map = {
            "uid": int,
            "timestamp": int,
            "locale": str,
            "user_agent": str,
        }
        with self._lock:
            state = self._read_state()
            rows = [
                dict(rec)
                for rec in state["sessions"].values()
                if _matches_filters(rec, filters, cast_map)
            ]
            return sorted(rows, key=lambda item: item["uid"])

    def correct_session(self, uid, updates=None):
        """Update fields of an existing Session record."""
        key = str(int(uid))
        changes = updates or {}
        with self._lock:
            state = self._read_state()
            if key not in state["sessions"]:
                raise KeyError(f"Session {key} not found")
            cur = dict(state["sessions"][key])
            if changes.get("timestamp") is not None:
                cur["timestamp"] = int(changes["timestamp"])
            if changes.get("locale") is not None:
                cur["locale"] = str(changes["locale"])
            if changes.get("user_agent") is not None:
                cur["user_agent"] = str(changes["user_agent"])
            state["sessions"][key] = cur
            self._write_state(state)
            return dict(cur)

    def create_request(self, uid, timestamp, content, session, triggered):
        """Create and persist a new Request record."""
        key = str(int(uid))
        sess_key = str(int(session))
        with self._lock:
            state = self._read_state()
            if key in state["requests"]:
                raise ValueError(f"Request {key} already exists")
            if sess_key not in state["sessions"]:
                raise ValueError(f"Session {sess_key} does not exist")
            record = {
                "uid": int(uid),
                "timestamp": int(timestamp),
                "content": str(content),
                "session": int(session),
                "triggered": int(triggered),
            }
            state["requests"][key] = record
            self._write_state(state)
            return dict(record)

    def remove_request(self, uid):
        """Delete Request by uid and cascade-remove linked Answers."""
        key = str(int(uid))
        int_uid = int(uid)
        with self._lock:
            state = self._read_state()
            if key not in state["requests"]:
                raise KeyError(f"Request {key} not found")
            ans_keys = [
                a_key
                for a_key, ans in state["answers"].items()
                if ans["request"] == int_uid
            ]
            for a_key in ans_keys:
                del state["answers"][a_key]
            del state["requests"][key]
            self._write_state(state)
            return True

    def query_request(self, session, filters=None):
        """Return Request records for session matching optional filters."""
        sess_id = int(session)
        cast_map = {
            "uid": int,
            "timestamp": int,
            "content": str,
            "triggered": int,
        }
        with self._lock:
            state = self._read_state()
            rows = [
                dict(rec)
                for rec in state["requests"].values()
                if rec["session"] == sess_id
                and _matches_filters(rec, filters, cast_map)
            ]
            return sorted(rows, key=lambda item: item["uid"])

    def correct_request(self, uid, updates=None):
        """Update fields of an existing Request record."""
        key = str(int(uid))
        changes = updates or {}
        with self._lock:
            state = self._read_state()
            if key not in state["requests"]:
                raise KeyError(f"Request {key} not found")
            cur = dict(state["requests"][key])
            if changes.get("session") is not None:
                new_sess = int(changes["session"])
                if str(new_sess) not in state["sessions"]:
                    raise ValueError(f"Session {new_sess} does not exist")
                cur["session"] = new_sess
            if changes.get("timestamp") is not None:
                cur["timestamp"] = int(changes["timestamp"])
            if changes.get("content") is not None:
                cur["content"] = str(changes["content"])
            if changes.get("triggered") is not None:
                cur["triggered"] = int(changes["triggered"])
            state["requests"][key] = cur
            self._write_state(state)
            return dict(cur)

    def next_answer_uid(self):
        """Return next available integer primary key for Answer."""
        with self._lock:
            state = self._read_state()
            if not state["answers"]:
                return ONE
            return max(int(k) for k in state["answers"]) + ONE

    def find_cached_answer(self, content):
        """Return a prior successful Answer for matching request content."""
        with self._lock:
            state = self._read_state()
            req_map = {
                req["uid"]: req["content"]
                for req in state["requests"].values()
            }
            for ans in sorted(
                state["answers"].values(), key=lambda item: item["uid"]
            ):
                if (
                    ans["status"] == TASK_STATUS_OK
                    and req_map.get(ans["request"]) == str(content)
                ):
                    return dict(ans)
            return None

    def create_answer(self, payload):
        """Create and persist a new Answer record from payload dictionary."""
        key = str(int(payload["uid"]))
        req_key = str(int(payload["request"]))
        with self._lock:
            state = self._read_state()
            if key in state["answers"]:
                raise ValueError(f"Answer {key} already exists")
            if req_key not in state["requests"]:
                raise ValueError(f"Request {req_key} does not exist")
            record = {
                "uid": int(payload["uid"]),
                "timestamp": int(payload["timestamp"]),
                "output": str(payload["output"]),
                "status": str(payload["status"]),
                "exception": str(payload["exception"]),
                "request": int(payload["request"]),
                "cache_hit": int(payload["cache_hit"]),
            }
            state["answers"][key] = record
            self._write_state(state)
            return dict(record)

    def query_answer(self, request_uid, filters=None):
        """Return Answer records for request_uid matching optional filters."""
        req_id = int(request_uid)
        cast_map = {
            "uid": int,
            "timestamp": int,
            "output": str,
            "status": str,
            "exception": str,
            "cache_hit": int,
        }
        with self._lock:
            state = self._read_state()
            rows = [
                dict(rec)
                for rec in state["answers"].values()
                if rec["request"] == req_id
                and _matches_filters(rec, filters, cast_map)
            ]
            return sorted(rows, key=lambda item: item["uid"])

    def query_report(self, now=None):
        """Execute relational algebra report query (formula 22)."""
        ref_time = int(time.time()) if now is None else int(now)
        threshold = ref_time - QUERY_TIME_WINDOW_SECONDS
        with self._lock:
            state = self._read_state()
            recent_sessions = {
                s["uid"]: s
                for s in state["sessions"].values()
                if s["timestamp"] >= threshold
            }
            rows = []
            reqs = sorted(
                state["requests"].values(), key=lambda item: item["uid"]
            )
            for req in reqs:
                matched = recent_sessions.get(req["session"])
                locale_val = None if matched is None else matched["locale"]
                rows.append({"content": req["content"], "locale": locale_val})
            return rows
