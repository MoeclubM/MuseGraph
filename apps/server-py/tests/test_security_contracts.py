import base64
from pathlib import Path

import pytest

from app.config import settings
from app.services.auth import hash_password, verify_password
from app.services.project_files import validate_project_upload
from app.services.provider_models import build_provider_model_ref, parse_provider_model_ref
from app.services.provider_security import validate_provider_base_url
from app.services.secret_crypto import decrypt_secret, encrypt_secret


def test_password_hash_is_argon2id():
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)


def test_secret_encryption_never_stores_plaintext(monkeypatch):
    key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    monkeypatch.setattr(settings, "SECRET_ENCRYPTION_KEY", key)
    encrypted = encrypt_secret("provider-secret")
    assert "provider-secret" not in encrypted
    assert decrypt_secret(encrypted) == "provider-secret"


def test_provider_model_reference_preserves_exact_provider_and_model():
    provider_id = "00000000-0000-0000-0000-000000000001"
    reference = build_provider_model_ref(provider_id, "vendor/model:latest")
    assert reference == f"{provider_id}::vendor/model:latest"
    assert parse_provider_model_ref(reference) == (provider_id, "vendor/model:latest")
    with pytest.raises(ValueError, match="specific provider"):
        parse_provider_model_ref("vendor/model:latest")


@pytest.mark.asyncio
async def test_provider_url_rejects_credentials_http_and_private_network(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_PRIVATE_PROVIDER_URLS", False)
    with pytest.raises(ValueError, match="credentials"):
        await validate_provider_base_url("https://user:pass@example.com")
    with pytest.raises(ValueError, match="HTTPS"):
        await validate_provider_base_url("http://example.com")
    with pytest.raises(ValueError, match="private or reserved"):
        await validate_provider_base_url("https://127.0.0.1")


def test_upload_magic_archive_paths_and_compression_are_checked(tmp_path: Path):
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"not a PDF")
    with pytest.raises(ValueError, match="PDF signature"):
        validate_project_upload(fake_pdf.name, fake_pdf)

    fake_webp = tmp_path / "fake.webp"
    fake_webp.write_bytes(b"RIFF\x00\x00\x00\x00NOPE")
    with pytest.raises(ValueError, match="WEBP signature"):
        validate_project_upload(fake_webp.name, fake_webp)

    svg = tmp_path / "unsafe.svg"
    svg.write_text("<svg><script>alert(1)</script></svg>", encoding="utf-8")
    with pytest.raises(ValueError, match="SVG upload is not allowed"):
        validate_project_upload(svg.name, svg)
