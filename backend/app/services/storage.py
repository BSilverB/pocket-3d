import mimetypes
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

import boto3
from botocore.config import Config as BotoConfig

from ..config import settings, PRODUCTS_STORAGE_DIR


class StorageService:
    """
    Hybrid Storage Manager (NFR-04):
    - 'local': Stores files in backend/storage/products/{product_id} and serves via /static/products/
    - 's3': Uploads to AWS S3 or Cloudflare R2 with public read URLs & presigned upload URLs.
    """

    def __init__(self) -> None:
        self.backend = settings.STORAGE_BACKEND.lower()
        self._s3_client = None
        if self.backend == "s3" and settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY:
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
                region_name=settings.S3_REGION or "auto",
                config=BotoConfig(signature_version="s3v4"),
            )

    def get_product_dir(self, product_id: str) -> Path:
        p_dir = PRODUCTS_STORAGE_DIR / product_id
        p_dir.mkdir(parents=True, exist_ok=True)
        return p_dir

    def save_bytes(self, product_id: str, relative_path: str, data: bytes, content_type: Optional[str] = None) -> str:
        local_path = self.get_product_dir(product_id) / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)

        if self._s3_client:
            key = f"products/{product_id}/{relative_path.replace(chr(92), '/')}"
            ctype = content_type or mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
            self._s3_client.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=key,
                Body=data,
                ContentType=ctype,
            )
            if settings.S3_PUBLIC_DOMAIN:
                return f"{settings.S3_PUBLIC_DOMAIN.rstrip('/')}/{key}"
            return f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{settings.S3_BUCKET_NAME}/{key}"

        clean_rel = relative_path.replace("\\", "/")
        return f"/storage/products/{product_id}/{clean_rel}"

    def get_public_url(self, product_id: str, relative_path: str) -> str:
        clean_rel = relative_path.replace("\\", "/")
        if self._s3_client and settings.S3_PUBLIC_DOMAIN:
            return f"{settings.S3_PUBLIC_DOMAIN.rstrip('/')}/products/{product_id}/{clean_rel}"
        return f"/storage/products/{product_id}/{clean_rel}"

    def generate_presigned_upload(self, product_id: str, filename: str, content_type: str = "image/jpeg") -> Dict[str, Any]:
        """Generates a Presigned URL for direct S3/R2 upload or fallback local upload endpoint (FR-03)."""
        clean_name = Path(filename).name
        if self._s3_client:
            key = f"uploads/{product_id}/{clean_name}"
            url = self._s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": settings.S3_BUCKET_NAME,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=3600,
            )
            return {
                "mode": "s3_presigned",
                "upload_url": url,
                "key": key,
                "method": "PUT",
            }
        return {
            "mode": "local_multipart",
            "upload_url": f"{settings.PUBLIC_BASE_URL}/api/products/{product_id}/upload",
            "key": f"uploads/{product_id}/{clean_name}",
            "method": "POST",
        }

    def delete_product_files(self, product_id: str) -> None:
        p_dir = PRODUCTS_STORAGE_DIR / product_id
        if p_dir.exists():
            shutil.rmtree(p_dir, ignore_errors=True)


storage_service = StorageService()
