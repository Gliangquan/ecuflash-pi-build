from datetime import timedelta
from io import BytesIO
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from app.settings import settings


def get_minio_client() -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=bool(settings.minio_secure),
    )


def ensure_bucket_exists() -> None:
    client = get_minio_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def build_object_url(object_key: str) -> str:
    if settings.minio_public_base_url:
        return f"{settings.minio_public_base_url.rstrip('/')}/{settings.minio_bucket}/{object_key}"
    scheme = "https" if settings.minio_secure else "http"
    return f"{scheme}://{settings.minio_endpoint}/{settings.minio_bucket}/{object_key}"


def upload_bytes(content: bytes, object_name: str, content_type: str) -> dict:
    ensure_bucket_exists()
    client = get_minio_client()
    safe_name = object_name.rsplit("/", 1)[-1].strip() or "file.bin"
    object_key = f"wiring-guides/{uuid4().hex}-{safe_name}"
    data = BytesIO(content)
    client.put_object(
        settings.minio_bucket,
        object_key,
        data,
        length=len(content),
        content_type=content_type or "application/octet-stream",
    )
    return {
        "object_key": object_key,
        "url": build_object_url(object_key),
    }


def remove_object(object_key: str) -> None:
    if not object_key:
        return
    client = get_minio_client()
    try:
        client.remove_object(settings.minio_bucket, object_key)
    except S3Error:
        return


def get_presigned_url(object_key: str, expires_hours: int = 24) -> str:
    client = get_minio_client()
    return client.presigned_get_object(
        settings.minio_bucket,
        object_key,
        expires=timedelta(hours=expires_hours),
    )


def get_object_content(object_key: str) -> tuple[bytes, str]:
    client = get_minio_client()
    response = client.get_object(settings.minio_bucket, object_key)
    try:
        content = response.read()
        content_type = response.headers.get("Content-Type") or "application/octet-stream"
        return content, content_type
    finally:
        response.close()
        response.release_conn()
