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


def execute_conversion_task(store, request_record, test_mode=False):
    """Run or simulate WebM->GIF conversion and persist Answer record."""
    answer_uid = store.next_answer_uid()
    req_uid = request_record["uid"]
    req_ts = request_record["timestamp"]
    content = request_record["content"]

    if test_mode:
        cached = store.find_cached_answer(content)
        hit = ONE if cached is not None else ZERO
        output = cached["output"] if hit else f"test-gif:{content}"
        return store.create_answer({
            "uid": answer_uid,
            "timestamp": req_ts,
            "output": output,
            "status": TASK_STATUS_OK,
            "exception": "",
            "request": req_uid,
            "cache_hit": hit,
        })

    cached = store.find_cached_answer(content)
    if cached is not None:
        return store.create_answer({
            "uid": answer_uid,
            "timestamp": req_ts,
            "output": cached["output"],
            "status": TASK_STATUS_OK,
            "exception": "",
            "request": req_uid,
            "cache_hit": ONE,
        })

    proc = subprocess.run(
        [sys.executable, "-m", "src.converter", content],
        capture_output=True,
        timeout=CLI_TIMEOUT_SECONDS,
        check=False,
    )
    if proc.returncode == ZERO:
        encoded = base64.b64encode(proc.stdout).decode("ascii")
        status = TASK_STATUS_OK
        exception = ""
    else:
        encoded = ""
        status = TASK_STATUS_ERROR
        exception = proc.stderr.decode(ENCODING, errors="replace").strip()

    return store.create_answer({
        "uid": answer_uid,
        "timestamp": req_ts,
        "output": encoded,
        "status": status,
        "exception": exception,
        "request": req_uid,
        "cache_hit": ZERO,
    })
