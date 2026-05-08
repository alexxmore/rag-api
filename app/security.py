import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

SUSPICIOUS_INPUT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"reveal\s+(the\s+)?system\s+prompt",
        r"\bsystem\s*:",
        r"<\|im_start\|>",
        r"</s>",
        r"developer\s+message",
        r"act\s+as\s+system",
    ]
]

SENSITIVE_OUTPUT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"system prompt",
        r"developer message",
        r"<system>",
        r"ignore previous instructions",
    ]
]


def _append_jsonl(path: str, payload: dict) -> None:
    record = {"created_at": datetime.now(timezone.utc).isoformat(), **payload}
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def validate_user_input(api_key: str, message: str) -> None:
    for pattern in SUSPICIOUS_INPUT_PATTERNS:
        if pattern.search(message):
            _append_jsonl("suspicious_requests.log", {"api_key": api_key, "pattern": pattern.pattern, "message": message[:500]})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Suspicious prompt-injection pattern detected",
            )


def output_needs_filtering(text: str) -> bool:
    return any(pattern.search(text) for pattern in SENSITIVE_OUTPUT_PATTERNS)
