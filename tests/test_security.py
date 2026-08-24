#!/usr/bin/env python3
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.cookies import cookie_value
from collector.http import _read_bounded, http
from collector.security import MAX_CREDENTIAL_BYTES, bounded_secret, run_bounded


assert _read_bounded(io.BytesIO(b"abc"), 3) == b"abc"
try:
    _read_bounded(io.BytesIO(b"abcd"), 3)
    raise AssertionError("oversized HTTP body was accepted")
except ValueError:
    pass

try:
    http("https://example.invalid/data", max_bytes=16)
    raise AssertionError("unlisted provider destination was accepted")
except ValueError:
    pass

assert bounded_secret("x" * MAX_CREDENTIAL_BYTES) == "x" * MAX_CREDENTIAL_BYTES
assert bounded_secret("x" * (MAX_CREDENTIAL_BYTES + 1)) is None
assert cookie_value({"session": {"evilcursor.com": "bad"}}, "session", ["cursor.com"]) is None
assert cookie_value({"session": {"auth.cursor.com": "good"}}, "session", ["cursor.com"]) == "good"

process = run_bounded(
    [sys.executable, "-c", "import sys; sys.stdout.write('x' * 1048576)"],
    timeout=5,
    max_bytes=4096,
)
assert len(process.stdout) <= 4096
assert len(process.stderr) <= 4096

print("security boundary tests passed")
