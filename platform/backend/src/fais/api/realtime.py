from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from fais.auth import AuthService

router = APIRouter()


def _visible(websocket: WebSocket, user: dict, payload: dict) -> bool:
    if user["role"] in {"ANALYST", "ADMIN"}:
        return True
    match_id = payload.get("match_id")
    if match_id is None and isinstance(payload.get("result"), dict):
        match_id = payload["result"].get("match_id")
    competition_id = payload.get("competition_id")
    with websocket.app.state.database.connect(readonly=True) as conn:
        if match_id is not None:
            return (
                conn.execute(
                    """SELECT 1 FROM matches m
                    JOIN user_competition_permissions p ON p.competition_id=m.competition_id
                    WHERE m.id=? AND p.user_id=?""",
                    (match_id, user["id"]),
                ).fetchone()
                is not None
            )
        if competition_id is not None:
            return (
                conn.execute(
                    """SELECT 1 FROM user_competition_permissions
                    WHERE competition_id=? AND user_id=?""",
                    (competition_id, user["id"]),
                ).fetchone()
                is not None
            )
    return False


@router.websocket("/ws/{topic}")
async def websocket_events(websocket: WebSocket, topic: str) -> None:
    """Bridge a Redis Stream to a socket without retaining events in the API process."""
    token = websocket.query_params.get("token")
    authorization = websocket.headers.get("authorization", "")
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user = (
        AuthService(websocket.app.state.database, websocket.app.state.settings).user_from_token(
            token
        )
        if token
        else None
    )
    if not user:
        await websocket.close(code=4401, reason="Authentication required")
        return
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
                    if not _visible(websocket, user, payload):
                        continue
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
