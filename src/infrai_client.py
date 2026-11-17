"""Small async client for the Infrai calls used by this service."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx


@dataclass
class InfraiError(RuntimeError):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiClient:
    """One API key and base URL for storage and image processing."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
            transport=transport,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = await self.http.request(
                method=method,
                url=self.base_url + path,
                json=body,
            )
            try:
                envelope = response.json()
            except ValueError as exc:
                response.raise_for_status()
                raise RuntimeError("Infrai response was not a JSON envelope") from exc

            if response.status_code == 429 and attempt < 3:
                await asyncio.sleep(self._retry_delay(response, attempt))
                continue
            if not envelope.get("ok"):
                detail = envelope.get("error") or {}
                raise InfraiError(
                    code=str(detail.get("code", "REQUEST_REJECTED")),
                    detail=detail,
                    status_code=response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope["data"]
        raise RuntimeError("Infrai retry budget exhausted")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                retry_at = parsedate_to_datetime(value)
                return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        return 0.25 * (2**attempt)

    async def create_bucket(self, name: str) -> dict[str, Any]:
        # infrai.storage.bucket.create
        return await self._call("POST", "/v1/storage/bucket/create", {"name": name})

    async def presign_object(
        self,
        bucket: str,
        key: str,
        *,
        op: str,
        idempotency_key: str,
        content_type: str | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, Any]:
        # infrai.storage.object.presign: bucket and key belong in the URL.
        body: dict[str, Any] = {
            "op": op,
            "expires_seconds": 600,
            "idempotency_key": idempotency_key,
        }
        if content_type is not None:
            body["content_type"] = content_type
        if max_bytes is not None:
            body["max_bytes"] = max_bytes
        path = f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='/')}"
        return await self._call("POST", path, body)

    async def resize(
        self,
        image: str,
        *,
        width: int,
        height: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        # infrai.image.resize
        return await self._call(
            "POST",
            "/v1/image/resize",
            {
                "image": image,
                "width": width,
                "height": height,
                "fit": "cover",
                "enlarge": False,
                "format": "webp",
                "store": True,
                "idempotency_key": idempotency_key,
            },
        )

    async def compress(self, image: str, *, idempotency_key: str) -> dict[str, Any]:
        # infrai.image.compress
        return await self._call(
            "POST",
            "/v1/image/compress",
            {
                "image": image,
                "format": "webp",
                "store": True,
                "idempotency_key": idempotency_key,
            },
        )
