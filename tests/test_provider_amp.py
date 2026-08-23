#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.amp import parse_amp_text


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
print("amp collector tests passed")
