import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

CODE_FENCE_RE = re.compile(r"```(?:\s*[\w+-]+)?\s*([\s\S]*?)```", re.IGNORECASE)


class StrictJsonSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def normalize_json_content(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    match = re.fullmatch(r"```(?:\s*[\w+-]+)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _load_json_dict(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def extract_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None

    direct = _load_json_dict(text)
    if direct is not None:
        return direct

    fenced = _load_json_dict(normalize_json_content(text))
    if fenced is not None:
        return fenced

    for match in CODE_FENCE_RE.finditer(text):
        parsed = _load_json_dict(match.group(1).strip())
        if parsed is not None:
            return parsed
    return None
