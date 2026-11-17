"""Typed game asset records and the moderation routing decision."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AssetKind(StrEnum):
    AVATAR = "avatar"
    EVENT_BANNER = "event_banner"


class ModerationState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"


class UploadTicketRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=80)
    event_id: str | None = Field(default=None, max_length=80)
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    content_type: str = Field(pattern=r"^image/(png|jpeg|webp)$")
    bytes: int = Field(gt=0, le=8_000_000)
    kind: AssetKind


class ProcessAssetRequest(BaseModel):
    asset_id: str = Field(min_length=1, max_length=80)
    player_id: str = Field(min_length=1, max_length=80)
    event_id: str | None = Field(default=None, max_length=80)
    object_key: str = Field(min_length=1, max_length=300)
    kind: AssetKind


class UploadTicket(BaseModel):
    asset_id: str
    object_key: str
    upload_url: str
    method: str = "PUT"


class ProcessedAsset(BaseModel):
    asset_id: str
    moderation_state: ModerationState
    queue: str | None
    variants: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class VariantPlan:
    name: str
    width: int
    height: int


VARIANTS = {
    AssetKind.AVATAR: (VariantPlan("profile", 256, 256),),
    AssetKind.EVENT_BANNER: (
        VariantPlan("lobby", 1280, 720),
        VariantPlan("event_list", 640, 360),
    ),
}


def moderation_route(kind: AssetKind, event_id: str | None) -> tuple[ModerationState, str | None]:
    """Live-event art waits for review; regular player avatars publish immediately."""
    if kind is AssetKind.EVENT_BANNER or event_id is not None:
        return ModerationState.PENDING, "live-event-art"
    return ModerationState.APPROVED, None


async def process_asset(
    request: ProcessAssetRequest,
    client: Any,
    bucket: str,
) -> ProcessedAsset:
    source = await client.presign_object(
        bucket,
        request.object_key,
        op="get",
        idempotency_key=f"{request.asset_id}:source",
    )
    variants: dict[str, dict[str, Any]] = {}
    for plan in VARIANTS[request.kind]:
        resized = await client.resize(
            source["url"],
            width=plan.width,
            height=plan.height,
            idempotency_key=f"{request.asset_id}:{plan.name}:resize",
        )
        image = str(resized.get("url") or resized.get("image") or resized["id"])
        variants[plan.name] = await client.compress(
            image,
            idempotency_key=f"{request.asset_id}:{plan.name}:compress",
        )
    state, queue = moderation_route(request.kind, request.event_id)
    return ProcessedAsset(
        asset_id=request.asset_id,
        moderation_state=state,
        queue=queue,
        variants=variants,
    )
