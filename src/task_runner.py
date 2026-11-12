"""Subprocess task runner for WebM to GIF computational jobs."""

import base64
import subprocess
import sys

from src.constants import (
    CLI_TIMEOUT_SECONDS,
    ENCODING,
    ONE,
    TASK_STATUS_ERROR,
    TASK_STATUS_OK,
    ZERO,
)


def _build_answer_payload(answer_uid, req_uid, req_ts, output,
                          status, exception, cache_hit):
    """Assemble standardized Answer record dictionary."""
    return {
        "uid": answer_uid,
        "timestamp": req_ts,
        "output": output,
        "status": status,
        "exception": exception,
        "request": req_uid,
        "cache_hit": cache_hit,
    }


def _run_subprocess_converter(content):
    """Invoke CLI WebM->GIF converter subprocess and decode outcome."""
    proc = subprocess.run(
        [sys.executable, "-m", "src.converter", content],
        capture_output=True,
        timeout=CLI_TIMEOUT_SECONDS,
        check=False,
    )
    if proc.returncode == ZERO:
        return (
            base64.b64encode(proc.stdout).decode("ascii"),
            TASK_STATUS_OK,
            "",
        )
    return (
        "",
        TASK_STATUS_ERROR,
        proc.stderr.decode(ENCODING, errors="replace").strip(),
    )


def execute_conversion_task(store, request_record, test_mode=False):
    """Run or simulate WebM->GIF conversion and persist Answer record."""
    answer_uid = store.next_answer_uid()
    req_uid = request_record["uid"]
    req_ts = request_record["timestamp"]
    content = request_record["content"]
    cached = store.find_cached_answer(content)

    if cached is not None:
        return store.create_answer(_build_answer_payload(
            answer_uid, req_uid, req_ts,
            cached["output"], TASK_STATUS_OK, "", ONE,
        ))
    if test_mode:
        return store.create_answer(_build_answer_payload(
            answer_uid, req_uid, req_ts,
            f"test-gif:{content}", TASK_STATUS_OK, "", ZERO,
        ))
    output, status, exc = _run_subprocess_converter(content)
    return store.create_answer(_build_answer_payload(
        answer_uid, req_uid, req_ts, output, status, exc, ZERO,
    ))
