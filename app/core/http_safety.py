"""HTTP boundary helpers shared by the OSS and hosted applications."""
from __future__ import annotations

import ipaddress
import logging
import os
import re
from typing import Any

from starlette.requests import Request


_TRUE_VALUES = {"1", "true", "yes", "on"}
_SENSITIVE_PATH_TOKEN = re.compile(
    r"(?P<prefix>/(?:api/v1/)?(?:hosted/)?(?:external-room/invitations|view)/)"
    r"[^/?\s]+",
    flags=re.IGNORECASE,
)
_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?P<prefix>[?&](?:"
    r"recipient_email|recipient_display_name|allowed_emails|email|"
    r"challenge_token|challenge_id|code|token"
    r")=)[^&\s]*",
    flags=re.IGNORECASE,
)


def _normalized_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def client_ip_from_request(request: Request) -> str | None:
    """Return the caller IP, honoring proxy headers only when explicitly enabled.

    ``HEXSHARE_TRUST_PROXY_HEADERS`` must only be enabled when the application
    cannot be reached except through a trusted reverse proxy. Cloudflare's
    connecting-IP header is preferred; the left-most X-Forwarded-For address is
    the fallback.
    """
    peer_ip = _normalized_ip(request.client.host if request.client else None)
    trust_proxy = os.getenv("HEXSHARE_TRUST_PROXY_HEADERS", "").strip().lower()
    if trust_proxy not in _TRUE_VALUES:
        return peer_ip

    cloudflare_ip = _normalized_ip(request.headers.get("cf-connecting-ip"))
    if cloudflare_ip:
        return cloudflare_ip

    forwarded_for = request.headers.get("x-forwarded-for", "")
    forwarded_ip = _normalized_ip(forwarded_for.split(",", 1)[0])
    return forwarded_ip or peer_ip


def redact_access_log_target(target: str) -> str:
    """Remove bearer tokens and recipient PII from an access-log URL."""
    redacted = _SENSITIVE_PATH_TOKEN.sub(r"\g<prefix>[REDACTED]", target)
    return _SENSITIVE_QUERY_VALUE.sub(r"\g<prefix>[REDACTED]", redacted)


class SensitiveAccessLogFilter(logging.Filter):
    """Redact sensitive URL components from Uvicorn access-log records."""

    _hexshare_sensitive_url_filter = True

    def filter(self, record: logging.LogRecord) -> bool:
        args: Any = record.args
        if isinstance(args, (tuple, list)) and len(args) >= 3:
            sanitized = list(args)
            sanitized[2] = redact_access_log_target(str(sanitized[2]))
            record.args = tuple(sanitized) if isinstance(args, tuple) else sanitized
        return True


def install_sensitive_access_log_filter() -> None:
    """Install one redaction filter on the process-wide Uvicorn access logger."""
    logger = logging.getLogger("uvicorn.access")
    if any(
        getattr(existing, "_hexshare_sensitive_url_filter", False)
        for existing in logger.filters
    ):
        return
    logger.addFilter(SensitiveAccessLogFilter())
