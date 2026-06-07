import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def from_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)
