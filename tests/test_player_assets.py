import asyncio
from typing import Any

from src.player_assets import AssetKind, ModerationState, ProcessAssetRequest, process_asset


class RecordingClient:
    def __init__(self) -> None:
        self.resize_calls: list[dict[str, Any]] = []
        self.compress_calls: list[str] = []

    async def presign_object(self, bucket: str, key: str, **kwargs: Any) -> dict[str, Any]:
        assert bucket == "game-assets"
        assert key == "players/p7/event.png"
        assert kwargs["op"] == "get"
        return {"url": "https://signed.example/source"}

    async def resize(self, image: str, **kwargs: Any) -> dict[str, Any]:
        self.resize_calls.append({"image": image, **kwargs})
        return {"id": f"resized-{kwargs['width']}"}

    async def compress(self, image: str, **kwargs: Any) -> dict[str, Any]:
        self.compress_calls.append(image)
        return {"id": f"compressed-{image}", "format": "webp"}


def test_live_event_banner_gets_two_variants_and_enters_review_queue() -> None:
    result, client = asyncio.run(run_live_event_workflow())

    assert [(call["width"], call["height"]) for call in client.resize_calls] == [
        (1280, 720),
        (640, 360),
    ]
    assert all(call["image"] == "https://signed.example/source" for call in client.resize_calls)
    assert client.compress_calls == ["resized-1280", "resized-640"]
    assert result.moderation_state is ModerationState.PENDING
    assert result.queue == "live-event-art"
    assert set(result.variants) == {"lobby", "event_list"}


async def run_live_event_workflow():
    client = RecordingClient()
    request = ProcessAssetRequest(
        asset_id="asset-9",
        player_id="p7",
        event_id="spring-final",
        object_key="players/p7/event.png",
        kind=AssetKind.EVENT_BANNER,
    )

    return await process_asset(request, client, "game-assets"), client
