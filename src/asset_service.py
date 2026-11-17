"""FastAPI entry point for player-generated image assets."""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .infrai_client import InfraiClient, InfraiError
from .player_assets import (
    ProcessAssetRequest,
    ProcessedAsset,
    UploadTicket,
    UploadTicketRequest,
    process_asset,
)

BUCKET = os.environ.get("GAME_ASSET_BUCKET", "player-generated-assets")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise RuntimeError("INFRAI_API_KEY is required")
    client = InfraiClient(key)
    try:
        await client.create_bucket(BUCKET)
    except InfraiError as error:
        if error.status_code != 409:
            raise
    app.state.infrai = client
    yield
    await client.close()


app = FastAPI(title="Player asset variants", lifespan=lifespan)


def get_client(request: Request) -> InfraiClient:
    return request.app.state.infrai


@app.exception_handler(InfraiError)
async def infrai_error_handler(_: Request, error: InfraiError):
    status = error.status_code if 400 <= error.status_code < 500 else 502
    return JSONResponse(
        status_code=status,
        content={"error": {"code": error.code, "message": str(error)}},
    )


@app.post("/assets/upload-ticket", response_model=UploadTicket, status_code=201)
async def create_upload_ticket(
    body: UploadTicketRequest,
    client: InfraiClient = Depends(get_client),
) -> UploadTicket:
    asset_id = uuid.uuid4().hex
    object_key = f"players/{body.player_id}/{asset_id}/{body.filename}"
    signed = await client.presign_object(
        BUCKET,
        object_key,
        op="put",
        content_type=body.content_type,
        max_bytes=body.bytes,
        idempotency_key=f"{asset_id}:upload",
    )
    if "url" not in signed:
        raise HTTPException(status_code=502, detail="Upload ticket is missing its URL")
    return UploadTicket(asset_id=asset_id, object_key=object_key, upload_url=signed["url"])


@app.post("/assets/process", response_model=ProcessedAsset)
async def create_variants(
    body: ProcessAssetRequest,
    client: InfraiClient = Depends(get_client),
) -> ProcessedAsset:
    return await process_asset(body, client, BUCKET)
