from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


DISALLOWED_SCHEMES = {"file", "ftp", "smb", "data", "chrome", "javascript"}


def _is_private_host(host: str) -> bool:
    if not host:
        return True
    lowered = host.lower()
    if lowered in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(lowered)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


class NetworkGuard:
    def validate_url(self, url: str) -> tuple[bool, str]:
        parsed = urlparse(url)
        if parsed.scheme.lower() in DISALLOWED_SCHEMES:
            return False, "DISALLOWED_SCHEME"
        if parsed.scheme.lower() not in {"http", "https"}:
            return False, "UNSUPPORTED_SCHEME"
        if _is_private_host(parsed.hostname or ""):
            return False, "DISALLOWED_TARGET"
        return True, "OK"
