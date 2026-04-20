from __future__ import annotations

import re
from typing import Any


_MEDIA_IMAGE_REF_RE = re.compile(
    r"\bmedia:(?:https?://[^\s\"'`]+|\.[/][^\s\"'`]+|[/][^\s\"'`]+|[^\s\"'`]+)"
    r"\.(?:jpe?g|png|webp|gif)(?=[\s\"'`]|$)",
    re.IGNORECASE,
)
_INTERNAL_REPLY_TO_RE = re.compile(r"\[\[reply_to[^\]]*\]\]\s*", re.IGNORECASE)
_CONVERSATION_INFO_RE = re.compile(
    r"^\s*Conversation info \(untrusted metadata\):\s*\n+\{[\s\S]*?\}\s*",
    re.IGNORECASE | re.MULTILINE,
)
_SENDER_INFO_RE = re.compile(
    r"^\s*Sender \(untrusted metadata\):\s*\n+\{[\s\S]*?\}\s*",
    re.IGNORECASE | re.MULTILINE,
)
_UNTRUSTED_CONTEXT_RE = re.compile(
    r"^\s*Untrusted context \(metadata, do not treat as instructions or commands\):\s*\n+"
    r"<<<EXTERNAL_UNTRUSTED_CONTENT[\s\S]*?<<<END_EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>\s*",
    re.IGNORECASE | re.MULTILINE,
)
_EXCESSIVE_NEWLINES_RE = re.compile(r"\n{3,}")
_ESCAPED_NL_RE = re.compile(r"\\r\\n|\\n|\\r")


def sanitize_string(value: str) -> str:
    if not isinstance(value, str):
        return value
    normalized = _ESCAPED_NL_RE.sub(
        lambda m: "\n" if "n" in m.group(0) else "\r", value
    )
    redacted = _INTERNAL_REPLY_TO_RE.sub("", normalized)
    redacted = _UNTRUSTED_CONTEXT_RE.sub("", redacted)
    redacted = _CONVERSATION_INFO_RE.sub("", redacted)
    redacted = _SENDER_INFO_RE.sub("", redacted)
    redacted = _EXCESSIVE_NEWLINES_RE.sub("\n\n", redacted)
    redacted = _MEDIA_IMAGE_REF_RE.sub("media:<image-ref>", redacted)
    return redacted.strip()


def sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        sanitized = sanitize_string(value)
        return sanitized
    if isinstance(value, list):
        changed = False
        result = []
        for item in value:
            s = sanitize_value(item)
            if s is not item:
                changed = True
            result.append(s)
        return result if changed else value
    if isinstance(value, dict):
        changed = False
        result = {}
        for k, v in value.items():
            s = sanitize_value(v)
            if s is not v:
                changed = True
            result[k] = s
        return result if changed else value
    return value
