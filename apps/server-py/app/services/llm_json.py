import json
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictJsonSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _load_json_dict(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None

def extract_json_object(raw: str) -> dict[str, Any] | None:
    return _load_json_dict(str(raw or "").strip())
