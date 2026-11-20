"""
Structured Logging Configuration with Secret Redaction & Log-Injection Sanitization.
"""

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

_SENSITIVE_KEY_SUBSTRINGS = ("password", "token", "secret", "authorization", "api_key", "cookie")
_NEWLINE_RE = re.compile(r"[\r\n\t]")


def redact_sensitive_processor(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    for key, value in list(event_dict.items()):
        lower_key = key.lower()
        if any(s in lower_key for s in _SENSITIVE_KEY_SUBSTRINGS):
            event_dict[key] = "[REDACTED]"
        elif isinstance(value, str):
            event_dict[key] = _NEWLINE_RE.sub(" ", value)
    return event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_sensitive_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
