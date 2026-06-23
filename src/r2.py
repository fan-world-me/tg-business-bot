"""Cloudflare R2 upload via S3-compatible API (AWS Signature V4)."""
import hashlib
import hmac
import json
import logging
import tempfile
from datetime import datetime, timezone

import httpx

from config import R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL

logger = logging.getLogger(__name__)

_ENDPOINT = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _auth_headers(key: str, content_type: str, payload: bytes) -> dict:
    now = datetime.now(timezone.utc)
    date = now.strftime("%Y%m%d")
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    host = f"{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    ph = hashlib.sha256(payload).hexdigest()

    canonical = (
        f"PUT\n/{R2_BUCKET_NAME}/{key}\n\n"
        f"content-type:{content_type}\nhost:{host}\n"
        f"x-amz-content-sha256:{ph}\nx-amz-date:{ts}\n\n"
        f"content-type;host;x-amz-content-sha256;x-amz-date\n{ph}"
    )
    scope = f"{date}/auto/s3/aws4_request"
    sts = f"AWS4-HMAC-SHA256\n{ts}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"

    k = _sign(_sign(_sign(_sign(f"AWS4{R2_SECRET_ACCESS_KEY}".encode(), date), "auto"), "s3"), "aws4_request")
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()

    return {
        "Authorization": f"AWS4-HMAC-SHA256 Credential={R2_ACCESS_KEY_ID}/{scope},SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date,Signature={sig}",
        "Content-Type": content_type,
        "x-amz-content-sha256": ph,
        "x-amz-date": ts,
    }


_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "gif": "image/gif", "avif": "image/avif",
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
    "ogg": "audio/ogg", "wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4",
    "pdf": "application/pdf", "txt": "text/plain", "log": "text/plain",
    "json": "application/json", "xml": "application/xml", "csv": "text/csv",
    "zip": "application/zip", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


async def upload(file_path: str, key: str) -> str | None:
    """Upload file to R2. Returns public URL or key."""
    if not R2_ACCESS_KEY_ID or not R2_BUCKET_NAME:
        logger.warning("R2 not configured, skipping upload")
        return None

    ext = file_path.rsplit(".", 1)[-1].lower()
    mime = _MIME.get(ext, "application/octet-stream")

    with open(file_path, "rb") as f:
        payload = f.read()

    headers = _auth_headers(key, mime, payload)
    url = f"{_ENDPOINT}/{R2_BUCKET_NAME}/{key}"

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.put(url, headers=headers, content=payload)
            r.raise_for_status()
        result = f"{R2_PUBLIC_URL.rstrip('/')}/{key}" if R2_PUBLIC_URL else key
        logger.info("R2 upload OK: %s", result)
        return result
    except Exception as exc:
        logger.error("R2 upload failed: %s", exc)
        return None
