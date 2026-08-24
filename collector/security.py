from __future__ import annotations

import json
import os
import selectors
import subprocess
import tempfile
import time
from pathlib import Path

MAX_CREDENTIAL_BYTES = 16 * 1024
MAX_AUTH_FILE_BYTES = 256 * 1024
MAX_SUBPROCESS_BYTES = 256 * 1024
MAX_TEXT_CHARS = 512
MAX_SNAPSHOT_BYTES = 64 * 1024
MAX_COLLECTION_ITEMS = 64
MAX_NESTING_DEPTH = 8


def bounded_secret(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text.encode("utf-8")) > MAX_CREDENTIAL_BYTES:
        return None
    return text


def read_bytes(path: Path, max_bytes: int = MAX_AUTH_FILE_BYTES) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"{path.name} exceeds {max_bytes} bytes")
    return data


def read_text(path: Path, max_bytes: int = MAX_AUTH_FILE_BYTES) -> str:
    return read_bytes(path, max_bytes).decode("utf-8")


def read_json(path: Path, max_bytes: int = MAX_AUTH_FILE_BYTES):
    return json.loads(read_text(path, max_bytes))


def run_bounded(
    command: list[str],
    *,
    input: bytes | None = None,
    timeout: int,
    max_bytes: int = MAX_SUBPROCESS_BYTES,
    text: bool = False,
) -> subprocess.CompletedProcess:
    """Run a local command without retaining more than max_bytes per stream."""
    with tempfile.TemporaryFile() as stdin:
        if input:
            stdin.write(input)
            stdin.seek(0)
        process = subprocess.Popen(
            command,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        streams = {process.stdout: bytearray(), process.stderr: bytearray()}
        selector = selectors.DefaultSelector()
        for stream in streams:
            selector.register(stream, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        exceeded = False
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                raise subprocess.TimeoutExpired(command, timeout)
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                target = streams[key.fileobj]
                available = max_bytes - len(target)
                if available > 0:
                    target.extend(chunk[:available])
                if len(chunk) > available:
                    exceeded = True
                    process.kill()
        returncode = process.wait()
        if exceeded and returncode == 0:
            returncode = -9
        out = bytes(streams[process.stdout])
        err = bytes(streams[process.stderr])
    if text:
        out = out.decode("utf-8", errors="replace")
        err = err.decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(command, returncode, out, err)


def bounded_value(value, depth: int = 0):
    """Keep provider-controlled display data small before it reaches QML."""
    if depth >= MAX_NESTING_DEPTH:
        return None
    if isinstance(value, str):
        return value[:MAX_TEXT_CHARS]
    if isinstance(value, dict):
        return {
            str(key)[:MAX_TEXT_CHARS]: bounded_value(item, depth + 1)
            for key, item in list(value.items())[:MAX_COLLECTION_ITEMS]
        }
    if isinstance(value, (list, tuple)):
        return [bounded_value(item, depth + 1) for item in value[:MAX_COLLECTION_ITEMS]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_TEXT_CHARS]


def snapshot_json(rows: list[dict]) -> str:
    payload = json.dumps(bounded_value(rows), separators=(",", ":"))
    if len(payload.encode("utf-8")) <= MAX_SNAPSHOT_BYTES:
        return payload
    return '[{"provider":"collector","source":"local","error":{"message":"Collector snapshot exceeded 65536 bytes."}}]'
