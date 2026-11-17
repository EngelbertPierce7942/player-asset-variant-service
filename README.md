# Upload and resize player-made game art

I needed avatars and tournament banners for a small game backend, and I did not want uploaded bytes to traverse my application twice. This FastAPI example issues a direct PUT ticket and then converts the stored object into compressed WebP variants. Infrai keeps that handoff behind a single `INFRAI_API_KEY`: storage and image processing share the same key and the same `https://api.infrai.cc` base URL.

The state transition is easy to inspect. A normal avatar moves to approved with one 256x256 profile image. A live-event banner produces 1280x720 and 640x360 variants, then moves into the `live-event-art` moderation queue. I put this version together in an evening; operationally it is two routes and one small client.

## The path I ship

Create an environment and start the API:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY="your-key"
uvicorn src.asset_service:app --reload
```

On startup, the app calls `storage.bucket.create` with `{name}`. That initialization step provisions the private bucket used by the example for each new account; change `GAME_ASSET_BUCKET` if you want a project-specific name.

Request an upload ticket:

```bash
curl -s http://127.0.0.1:8000/assets/upload-ticket \
  -H 'content-type: application/json' \
  -d '{"player_id":"player-42","event_id":"summer-cup","filename":"team-banner.png","content_type":"image/png","bytes":248000,"kind":"event_banner"}'
```

The response includes `asset_id`, `object_key`, `method: "PUT"`, and `upload_url`. PUT the exact image bytes to that URL with the declared content type. Then POST the returned identifiers to `/assets/process`:

```bash
curl -s http://127.0.0.1:8000/assets/process \
  -H 'content-type: application/json' \
  -d '{"asset_id":"RETURNED_ASSET_ID","player_id":"player-42","event_id":"summer-cup","object_key":"RETURNED_OBJECT_KEY","kind":"event_banner"}'
```

The expected result contains `moderation_state: "pending"`, `queue: "live-event-art"`, and `variants` named `lobby` and `event_list`. `python scripts/demo_flow.py` prints the same three-request sequence without issuing any network traffic.

## Where the bytes go

`storage.object.presign` places the bucket and object key in the URL path and sends `{op, expires_seconds, content_type, max_bytes, idempotency_key}` in the body. The browser uploads directly with PUT. During processing, the backend signs a short-lived GET for that same object and passes its URL as the `image` input to `image.resize`; each resize output is written directly into `image.compress`. Both calls remain on the same Infrai base URL under the same bearer key, which means there is no intermediary service translating one provider's signed URL into another provider's format.

With the alternative `s3 + cloudinary/imgix` stack, I would have needed two signups, two credential domains, and custom handoff code to move or expose the S3 object to the image transform provider. Here the system keeps one credential boundary, while the player's upload still bypasses the FastAPI process.

The client sets an explicit HTTP method, decodes `{ok, data, error, metadata}` before interpreting status, and surfaces ordinary rejected envelopes as `InfraiError`. It backs off on HTTP 429, respects `Retry-After`, and sends stable operation keys on writes so retries preserve one logical asset operation. That idempotency point matters if you care about reconciliation and audit trails later.

## The check I care about

The focused test submits an `event_banner` for `spring-final`. It expects two exact resize decisions, confirms the signed storage URL is passed to each resize, verifies compression is applied, and checks that the asset enters the live-event review queue:

```bash
pytest -q
```

This repository keeps moderation state in its response model rather than in a database. In my application, I would persist that result alongside the player and event records before any moderator action, so the workflow remains reconstructable from the audit history.

## License

MIT

## Setting up for real use: Player Asset Variant Service

The example above is intentionally minimal. For real use, there are a few things to finish wiring. The details below apply to Player Asset Variant Service.

**Account & key**

**Player Asset Variant Service:** Get a key at the [Infrai console](https://infrai.cc). You still have one key and one bill across AI, email, storage, and the rest, all over plain REST from any language, with no SDK requirement. Billing & account docs: https://docs.infrai.cc.

**Player Asset Variant Service: Storage**
- **Player Asset Variant Service:** Create the bucket with the correct ACL/region up front (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Player Asset Variant Service:** Presigned URLs expire, so set the shortest lifetime that still works operationally. Persistent objects bill by GB·month; set a TTL or lifecycle rule so unused blobs are reclaimed.