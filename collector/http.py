from __future__ import annotations

import ssl
import urllib.error
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)

CTX = ssl.create_default_context()

ALLOWED_HTTPS_HOSTS = frozenset({
    "accounts.x.ai",
    "ampcode.com",
    "api.factory.ai",
    "api.kimi.ai",
    "api.kimi.com",
    "app.factory.ai",
    "app.notion.com",
    "auth.kimi.ai",
    "auth.kimi.com",
    "chatgpt.com",
    "cli-chat-proxy.grok.com",
    "cloud.zed.dev",
    "cursor.com",
    "grok.com",
})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=CTX),
    _NoRedirect(),
)


def _read_bounded(stream, max_bytes: int) -> bytes:
    chunks = []
    remaining = max_bytes + 1
    while remaining > 0:
        chunk = stream.read(min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    body = b"".join(chunks)
    if len(body) > max_bytes:
        raise ValueError(f"response exceeded {max_bytes} bytes")
    return body


def http(url: str, *, max_bytes: int, method: str = "GET", headers: dict | None = None,
         body: bytes | None = None, timeout: int = 20):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HTTPS_HOSTS:
        raise ValueError("provider destination is not allowed")
    req_headers = {"User-Agent": UA}
    if headers:
        req_headers.update(headers)
    if sum(len(str(key)) + len(str(value)) for key, value in req_headers.items()) > 32 * 1024:
        raise ValueError("request headers exceed 32768 bytes")
    if body is not None and len(body) > 64 * 1024:
        raise ValueError("request body exceeds 65536 bytes")
    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            return resp.status, _read_bounded(resp, max_bytes), {}
    except urllib.error.HTTPError as exc:
        try:
            response_body = _read_bounded(exc, max_bytes)
        except ValueError:
            response_body = b"response exceeded configured limit"
        return exc.code, response_body, {}
    except Exception as exc:
        return 0, str(exc)[:256].encode(), {}
