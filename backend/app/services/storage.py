from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

VIDEO_BUCKET = "youtube-videos"


@lru_cache
def get_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_video_bucket() -> None:
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=VIDEO_BUCKET)
    except ClientError as exc:
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        error_code = exc.response.get("Error", {}).get("Code")
        if status_code != 404 and error_code not in {"NoSuchBucket", "NotFound"}:
            raise
        client.create_bucket(Bucket=VIDEO_BUCKET)


def upload_video(file_obj, object_key: str, content_type: str) -> None:
    ensure_video_bucket()
    get_s3_client().upload_fileobj(
        file_obj,
        VIDEO_BUCKET,
        object_key,
        ExtraArgs={"ContentType": content_type},
    )


def upload_thumbnail(file_obj, object_key: str, content_type: str) -> None:
    ensure_video_bucket()
    get_s3_client().upload_fileobj(
        file_obj,
        VIDEO_BUCKET,
        object_key,
        ExtraArgs={"ContentType": content_type, "CacheControl": "public, max-age=86400"},
    )


def delete_object(object_key: str) -> None:
    ensure_video_bucket()
    get_s3_client().delete_object(Bucket=VIDEO_BUCKET, Key=object_key)


def get_video_object(object_key: str, byte_range: str | None = None) -> dict:
    ensure_video_bucket()
    client = get_s3_client()
    metadata = client.head_object(Bucket=VIDEO_BUCKET, Key=object_key)
    params = {"Bucket": VIDEO_BUCKET, "Key": object_key}
    if byte_range:
        params["Range"] = byte_range
    result = client.get_object(**params)
    result["TotalLength"] = metadata["ContentLength"]
    return result
