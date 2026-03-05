from pathlib import Path

from app.config import settings


def _storage_root() -> Path:
    return Path(settings.FILE_STORAGE_ROOT).expanduser()


def _resolve_target_path(file_name: str) -> Path:
    root = _storage_root().resolve()
    normalized = str(file_name or "").strip().replace("\\", "/").lstrip("/")
    if not normalized:
        raise ValueError("file_name cannot be empty")
    target = (root / normalized).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Invalid file_name path") from exc
    return target


def ensure_bucket() -> None:
    _storage_root().mkdir(parents=True, exist_ok=True)


def upload_file(file_name: str, data: bytes, content_type: str) -> str:
    del content_type  # kept for interface compatibility
    ensure_bucket()
    target_path = _resolve_target_path(file_name)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(data)
    return file_name
