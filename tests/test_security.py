#!/usr/bin/env python3
import io
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.cookies import cookie_value
from collector.http import ALLOWED_HTTPS_HOSTS, _read_bounded, http
from collector.security import MAX_CREDENTIAL_BYTES, bounded_secret, read_bytes, run_bounded


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
assert "ampcode.com" in ALLOWED_HTTPS_HOSTS

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

COLLECTOR_SOURCES = Path(__file__).resolve().parent.parent / "collector"
FORBIDDEN_SOURCE_PATTERNS = (
    (r"(?<!os)(?<!NER)\.open\(", "pathlib-style file open"),
    (r"(?<![\w.])open\(", "builtin file open"),
    (r"\.read_bytes\(", "unbounded pathlib read_bytes"),
    (r"\.read_text\(", "unbounded pathlib read_text"),
)


def test_collector_reads_are_descriptor_bound():
    """Collector sources must read credentials only through security.read_bytes."""
    violations = []
    for path in sorted(COLLECTOR_SOURCES.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines):
            for pattern, reason in FORBIDDEN_SOURCE_PATTERNS:
                if re.search(pattern, line):
                    violations.append(f"{path.name}:{number + 1} {reason}")
            if ".exists()" in line:
                for follower in lines[number + 1 : number + 3]:
                    if re.search(r"read_(?:json|text|bytes)\(", follower):
                        violations.append(
                            f"{path.name}:{number + 1} exists() before a credential read"
                        )
    assert not violations, "\n".join(violations)


test_collector_reads_are_descriptor_bound()

with tempfile.TemporaryDirectory() as scratch:
    base = Path(scratch)

    credential = base / "creds.json"
    credential.write_bytes(b'{"token": "bounded"}')
    credential.chmod(0o600)
    assert read_bytes(credential, 32) == b'{"token": "bounded"}'

    loose = base / "loose.json"
    loose.write_bytes(b"{}")
    loose.chmod(0o644)
    try:
        read_bytes(loose, 16)
        raise AssertionError("group/other-accessible credential was accepted")
    except ValueError:
        pass

    swapped = base / "swapped.json"
    swapped.symlink_to(credential)
    try:
        read_bytes(swapped, 16)
        raise AssertionError("symlinked credential path was followed")
    except OSError:
        pass

    fifo = base / "fifo"
    os.mkfifo(fifo)
    try:
        read_bytes(fifo, 16)
        raise AssertionError("FIFO credential path was accepted")
    except ValueError:
        pass

    real_geteuid_fn = os.geteuid
    real_geteuid = real_geteuid_fn()
    os.geteuid = lambda: real_geteuid + 1
    try:
        try:
            read_bytes(credential, 32)
            raise AssertionError("foreign-owned credential was accepted")
        except ValueError:
            pass
    finally:
        os.geteuid = real_geteuid_fn

    try:
        read_bytes(credential, 0)
        raise AssertionError("oversized credential was accepted")
    except ValueError:
        pass

print("security boundary tests passed")
