"""Print the two requests a game backend makes around the direct upload."""
import json


ticket_request = {
    "player_id": "player-42",
    "event_id": "summer-cup",
    "filename": "team-banner.png",
    "content_type": "image/png",
    "bytes": 248000,
    "kind": "event_banner",
}

print("1. POST /assets/upload-ticket")
print(json.dumps(ticket_request, indent=2))
print("2. PUT the image bytes to upload_url from that response")
print("3. POST /assets/process with asset_id, object_key, player_id, event_id, and kind")

