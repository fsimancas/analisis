from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

router = APIRouter()


@router.websocket("/ws/{topic}")
async def websocket_events(websocket: WebSocket, topic: str) -> None:
    """Bridge a Redis Stream to a socket without retaining events in the API process."""
    await websocket.accept()
    redis_url: str = websocket.app.state.settings.redis_url
    client = Redis.from_url(redis_url, decode_responses=True)
    stream = f"fais:{topic}"
    last_id = "$"
    try:
        while True:
            entries = await client.xread({stream: last_id}, block=10_000, count=100)
            if not entries:
                await websocket.send_json({"topic": "heartbeat"})
                continue
            for _, messages in entries:
                for event_id, fields in messages:
                    last_id = event_id
                    payload = json.loads(fields.get("payload", "{}"))
                    await websocket.send_json(
                        {"id": event_id, "topic": fields.get("topic", topic), "payload": payload}
                    )
    except WebSocketDisconnect:
        pass
    except Exception as error:
        await websocket.send_json({"topic": "system", "error": f"Event bus unavailable: {error}"})
        await websocket.close(code=1013)
    finally:
        await client.aclose()
