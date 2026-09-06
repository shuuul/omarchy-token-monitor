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

# Local Antigravity language servers listen on 127.0.0.1 with a self-signed
# certificate. This context is only ever used for loopback URLs: hostname and
# certificate verification are disabled because the certificate is generated
# per machine, and the destination host is fixed in loopback_http below.
LOOPBACK_CTX = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
LOOPBACK_CTX.check_hostname = False
LOOPBACK_CTX.verify_mode = ssl.CERT_NONE

LOOPBACK_OPENER = urllib.request.build_opener(
    # Proxies must never see a loopback probe.
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=LOOPBACK_CTX),
    urllib.request.HTTPHandler(),
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


def loopback_http(port: int, path: str, *, max_bytes: int, body: bytes,
                  headers: dict | None = None, timeout: int = 4, tls: bool = True):
    """Bounded POST to a local language-server endpoint on 127.0.0.1 only.

    The destination host is fixed: there is no hostname parameter, so this
    client can never reach a remote provider. The port must be a TCP port,
    the path is bounded and free of control characters, the request body and
    response are size-capped, redirects are never followed, and self-signed
    TLS is accepted because that is what the local server presents.
    """
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("loopback port is not valid")
    if (not path.startswith("/") or len(path) > 256
            or any(character in path for character in " \t\r\n\x00")):
        raise ValueError("loopback path is not valid")
    if not isinstance(body, (bytes, bytearray)) or not body or len(body) > 64 * 1024:
        raise ValueError("loopback request body is not bounded")
    req_headers = {"Content-Type": "application/json", "Connect-Protocol-Version": "1"}
    if headers:
        req_headers.update(headers)
    if sum(len(str(key)) + len(str(value)) for key, value in req_headers.items()) > 32 * 1024:
        raise ValueError("request headers exceed 32768 bytes")
    url = f"{'https' if tls else 'http'}://127.0.0.1:{port}{path}"
    request = urllib.request.Request(url, data=bytes(body), method="POST", headers=req_headers)
    try:
        with LOOPBACK_OPENER.open(request, timeout=timeout) as response:
            return response.status, _read_bounded(response, max_bytes), {}
    except urllib.error.HTTPError as exc:
        try:
            response_body = _read_bounded(exc, max_bytes)
        except ValueError:
            response_body = b"response exceeded configured limit"
        return exc.code, response_body, {}
    except Exception as exc:
        return 0, str(exc)[:256].encode(), {}
