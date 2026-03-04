import json
import re
from ast import literal_eval
from typing import Any

CODE_FENCE_RE = re.compile(r"```(?:\s*[\w+-]+)?\s*([\s\S]*?)```", re.IGNORECASE)


def _normalize_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    return (
        text.replace("\ufeff", "")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _unwrap_json_wrappers(text: str) -> str:
    current = (text or "").strip()
    if not current:
        return ""
    # Repeatedly unwrap markdown code fences when the whole payload is fenced.
    for _ in range(3):
        match = re.fullmatch(r"```(?:\s*[\w+-]+)?\s*([\s\S]*?)```", current, re.IGNORECASE)
        if not match:
            break
        current = match.group(1).strip()

    # Some providers return JSON as a quoted string payload.
    if len(current) >= 2 and current[0] == '"' and current[-1] == '"':
        try:
            unquoted = json.loads(current)
            if isinstance(unquoted, str):
                current = unquoted.strip()
        except Exception:
            pass
    return current


def normalize_json_content(raw: str) -> str:
    text = _normalize_text(raw)
    if not text:
        return ""
    return _unwrap_json_wrappers(text)


def _json_loads_loose(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidate = text.strip()
    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
    except Exception:
        pass

    # Remove common JSON errors such as trailing commas.
    candidate_no_trailing = re.sub(r",\s*([}\]])", r"\1", candidate)
    if candidate_no_trailing != candidate:
        try:
            data = json.loads(candidate_no_trailing)
            if isinstance(data, dict):
                return data
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0]
        except Exception:
            pass

    # Fall back to python literal parsing for single-quote JSON-like content.
    try:
        py_like = (
            candidate_no_trailing.replace(": true", ": True")
            .replace(": false", ": False")
            .replace(": null", ": None")
        )
        data = literal_eval(py_like)
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
    except Exception:
        return None
    return None


def _balanced_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    if not text:
        return candidates
    starts = [m.start() for m in re.finditer(r"[{\[]", text)]
    for start in starts[:30]:
        opening = text[start]
        closing = "}" if opening == "{" else "]"
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == opening:
                depth += 1
            elif ch == closing:
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : idx + 1])
                    break
    return candidates


def extract_json_object(raw: str) -> dict[str, Any] | None:
    text = normalize_json_content(raw)
    if not text:
        return None

    direct = _json_loads_loose(text)
    if direct:
        return direct

    for match in CODE_FENCE_RE.finditer(_normalize_text(raw)):
        block = normalize_json_content(match.group(1))
        parsed = _json_loads_loose(block)
        if parsed:
            return parsed

    for candidate in _balanced_json_candidates(text):
        parsed = _json_loads_loose(candidate)
        if parsed:
            return parsed

    raw_text = _normalize_text(raw)
    if raw_text and raw_text != text:
        for candidate in _balanced_json_candidates(raw_text):
            parsed = _json_loads_loose(candidate)
            if parsed:
                return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        parsed = _json_loads_loose(text[start : end + 1])
        if parsed:
            return parsed

    raw_start = raw_text.find("{")
    raw_end = raw_text.rfind("}")
    if raw_start != -1 and raw_end != -1 and raw_end > raw_start:
        parsed = _json_loads_loose(raw_text[raw_start : raw_end + 1])
        if parsed:
            return parsed
    return None
