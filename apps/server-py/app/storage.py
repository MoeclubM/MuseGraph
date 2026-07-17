from pathlib import Path

from app.config import settings


def _storage_root() -> Path:
    return Path(settings.FILE_STORAGE_ROOT).expanduser()


def ensure_bucket() -> None:
    _storage_root().mkdir(parents=True, exist_ok=True)
