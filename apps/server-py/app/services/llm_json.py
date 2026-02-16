import json
import re
from typing import Any


def extract_json_object(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        try:
            data = json.loads(fenced.group(1).strip())
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            return None
    return None
