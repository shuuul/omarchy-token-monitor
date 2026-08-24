#!/usr/bin/env python3
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers import amp
from collector.providers.amp import parse_amp_api_payload, parse_amp_text, visible_cli_error


text = """
Signed in as user@example.com (example)
**Amp Free:** 99% remaining today (resets daily)
**Amp Megawatt Subscription:** 95% other usage and 97% orb usage remaining - resets upon renewal in 6 days
**Individual credits:** $3.23 remaining
"""
parsed = parse_amp_text(text)
assert parsed["provider"] == "amp"
assert parsed["usage"]["primary"]["usedPercent"] == 1
assert parsed["usage"]["secondary"]["usedPercent"] == 5
assert parsed["usage"]["secondary"]["label"] == "Token Usage"
assert parsed["usage"]["tertiary"]["usedPercent"] == 3
assert parsed["credits"]["remaining"] == 3.23

alt = parse_amp_text("Subscription Megawatt: 80% other usage and 90% orb usage remaining - resets upon renewal in 1 month")
assert alt["usage"]["loginMethod"] == "Megawatt"
assert alt["usage"]["secondary"]["usedPercent"] == 20
assert alt["usage"]["tertiary"]["usedPercent"] == 10

display, error = parse_amp_api_payload(b'{"ok":true,"result":{"displayText":"Amp Free: 40% remaining today"}}')
assert error is None
assert "Amp Free" in display
assert parse_amp_api_payload(b'{"ok":false,"error":{"code":"auth-required"}}')[1] == "Amp access token is invalid or expired."
assert parse_amp_api_payload(b'{"ok":true,"result":{}}')[1] == "Amp usage API returned no usage text."

garbled = "Error: Unexpected error inside Amp CLI.\n\x1b[=0u\x1b[<u\x1b[?25h"
assert visible_cli_error(garbled, "", 1) == "Error: Unexpected error inside Amp CLI."
assert "\x1b" not in visible_cli_error(garbled, "", 1)

originals = {
    "which": amp.shutil.which,
    "run_bounded": amp.run_bounded,
    "amp_api_token": amp.amp_api_token,
    "fetch_amp_display": amp.fetch_amp_display,
    "cookie_header": amp.cookie_header,
}
try:
    amp.shutil.which = lambda _: "/usr/bin/amp"
    amp.run_bounded = lambda *args, **kwargs: SimpleNamespace(
        returncode=1,
        stdout="",
        stderr=garbled,
    )
    amp.amp_api_token = lambda: "sgamp_test"
    amp.fetch_amp_display = lambda headers: (text, None)
    amp.cookie_header = lambda *args, **kwargs: ""
    fallback = amp.fetch_amp({})
    assert fallback["source"] == "api"
    assert fallback["error"] is None
    assert fallback["usage"]["secondary"]["usedPercent"] == 5

    amp.fetch_amp_display = lambda headers: (None, "Amp access token is invalid or expired.")
    failed = amp.fetch_amp({})
    assert failed["source"] == "api"
    assert failed["error"]["message"] == "amp usage failed: Error: Unexpected error inside Amp CLI."
finally:
    amp.shutil.which = originals["which"]
    amp.run_bounded = originals["run_bounded"]
    amp.amp_api_token = originals["amp_api_token"]
    amp.fetch_amp_display = originals["fetch_amp_display"]
    amp.cookie_header = originals["cookie_header"]
print("amp collector tests passed")
