import io

from minio import Minio

from app.config import settings

minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_USE_SSL,
)


def ensure_bucket():
    if not minio_client.bucket_exists(settings.MINIO_BUCKET):
        minio_client.make_bucket(settings.MINIO_BUCKET)


def upload_file(file_name: str, data: bytes, content_type: str) -> str:
    ensure_bucket()
    minio_client.put_object(
        settings.MINIO_BUCKET,
        file_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return file_name
