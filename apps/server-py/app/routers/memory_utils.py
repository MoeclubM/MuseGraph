import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.schemas.memory import (
    MemoryBuildRequest,
    MemoryOntologyGenerateRequest,
    MemoryTextIngestRequest,
)

MEMORY_BUILD_REBUILD = "rebuild"
MEMORY_BUILD_INCREMENTAL = "incremental"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_chapter_ids(chapter_ids: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in chapter_ids or []:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _normalize_int_list(values: list[Any] | None) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw in values or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_json_payload(payload: Any) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        encoded = str(payload)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text_hash_or_empty(text: str | None) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    return _hash_text(normalized)


def _normalize_memory_build_mode(mode: str | None) -> str:
    value = str(mode or "").strip().lower()
    if value == MEMORY_BUILD_INCREMENTAL:
        return MEMORY_BUILD_INCREMENTAL
    return MEMORY_BUILD_REBUILD


def _build_task_idempotency_key(*, task_type: str, project_id: str, payload: dict[str, Any]) -> str:
    task = str(task_type or "").strip().lower() or "task"
    fingerprint = _hash_json_payload(
        {
            "task_type": task,
            "project_id": str(project_id or "").strip(),
            "payload": payload,
        }
    )
    return f"{task}:{fingerprint[:24]}"


def _build_memory_task_idempotency_key(project_id: str, body: MemoryBuildRequest) -> str:
    return _build_task_idempotency_key(
        task_type="memory_build",
        project_id=project_id,
        payload={
            "chapter_ids": _normalize_chapter_ids(body.chapter_ids),
            "build_mode": _normalize_memory_build_mode(body.build_mode),
            "text_hash": _text_hash_or_empty(body.text),
            "ontology_hash": _hash_json_payload(body.ontology) if isinstance(body.ontology, dict) else "",
        },
    )


def _build_ontology_task_idempotency_key(project_id: str, body: MemoryOntologyGenerateRequest) -> str:
    return _build_task_idempotency_key(
        task_type="ontology_generate",
        project_id=project_id,
        payload={
            "chapter_ids": _normalize_chapter_ids(body.chapter_ids),
            "text_hash": _text_hash_or_empty(body.text),
            "model": str(body.model or "").strip(),
            "requirement": str(body.requirement or "").strip(),
        },
    )


def _build_text_ingest_task_idempotency_key(project_id: str, body: MemoryTextIngestRequest) -> str:
    return _build_task_idempotency_key(
        task_type="text_ingest",
        project_id=project_id,
        payload={
            "text_hash": _text_hash_or_empty(body.text),
            "source_title": str(body.source_title or "").strip(),
            "requirement": str(body.requirement or "").strip(),
            "ontology_model": str(body.ontology_model or "").strip(),
            "build_mode": _normalize_memory_build_mode(body.build_mode),
        },
    )


def _build_provenance(*, source_chapter_ids: list[str], text: str) -> dict[str, Any]:
    return {
        "source_chapter_ids": source_chapter_ids,
        "content_hash": _hash_text(text),
        "generated_at": _now_iso(),
    }


def _inject_provenance(payload: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    payload["source_chapter_ids"] = list(provenance.get("source_chapter_ids") or [])
    payload["content_hash"] = str(provenance.get("content_hash") or "")
    payload["generated_at"] = str(provenance.get("generated_at") or _now_iso())
    payload["provenance"] = {
        "source_chapter_ids": payload["source_chapter_ids"],
        "content_hash": payload["content_hash"],
        "generated_at": payload["generated_at"],
    }
    return payload


def _read_provenance(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    source_chapter_ids = payload.get("source_chapter_ids")
    content_hash = payload.get("content_hash")
    generated_at = payload.get("generated_at")
    if isinstance(payload.get("provenance"), dict):
        nested = payload["provenance"]
        if source_chapter_ids is None:
            source_chapter_ids = nested.get("source_chapter_ids")
        if not content_hash:
            content_hash = nested.get("content_hash")
        if not generated_at:
            generated_at = nested.get("generated_at")

    normalized_ids = _normalize_chapter_ids(source_chapter_ids if isinstance(source_chapter_ids, list) else None)
    hash_value = str(content_hash or "").strip()
    generated = str(generated_at or "").strip() or _now_iso()
    if not hash_value:
        return None
    return {
        "source_chapter_ids": normalized_ids,
        "content_hash": hash_value,
        "generated_at": generated,
    }


def _ontology_text_profile(ontology: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(ontology, dict):
        return {}
    text_type = str(ontology.get("text_type") or "").strip()
    out: dict[str, Any] = {}
    if text_type:
        out["text_type"] = text_type
    confidence = ontology.get("text_type_confidence")
    if isinstance(confidence, (int, float)):
        out["text_type_confidence"] = float(confidence)
    reason = str(ontology.get("text_type_reason") or "").strip()
    if reason:
        out["text_type_reason"] = reason
    return out
