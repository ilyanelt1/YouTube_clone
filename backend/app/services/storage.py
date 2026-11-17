from functools import lru_cache

import boto3
from botocore.client import Config

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
    except client.exceptions.ClientError as exc:
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


def create_playback_url(object_key: str) -> str:
    ensure_video_bucket()
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": VIDEO_BUCKET, "Key": object_key},
        ExpiresIn=3600,
    )
