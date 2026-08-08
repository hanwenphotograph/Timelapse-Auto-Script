"""Public JSONL server behavior for the SunsetScore test double."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from fake_sunsetscore_core import (
    Session,
    inventory,
    record,
    scan,
    write_session_score,
)


def serve_jsonl(version: str, interval: int) -> int:
    sessions: dict[str, Session] = {}
    model_started = False
    emit(
        {
            "event": "ready",
            "protocol_version": 1,
            "application_version": version,
        }
    )
    for line in sys.stdin:
        request: dict = {}
        try:
            request = json.loads(line)
            request_id = request["id"]
            command = request["command"]
            if command == "close":
                emit({"id": request_id, "event": "closed"})
                if model_started:
                    record("model-close")
                return 0
            session_id = str(request["session"])
            if command == "scan":
                session = _session_for(sessions, session_id, request)
                if not model_started:
                    model_started = True
                    record("model-start")
                attempted = scan(session, interval)
                emit(_scan_event(request_id, session_id, session, interval, attempted))
                continue
            if command != "finalize" or session_id not in sessions:
                raise ValueError("未知命令或会话")
            session = sessions[session_id]
            scan(session, interval)
            result, path = write_session_score(session, interval, version)
            emit(
                {
                    "id": request_id,
                    "event": "finalized",
                    "session": session_id,
                    "score_file": str(path),
                    "result": result,
                }
            )
        except Exception as exc:
            emit(
                {
                    "id": request.get("id") if isinstance(request, dict) else None,
                    "event": "error",
                    "error": str(exc),
                }
            )
    if model_started:
        record("model-close")
    return 0


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)


def _session_for(
    sessions: dict[str, Session], session_id: str, request: dict
) -> Session:
    directory = Path(request["directory"]).resolve()
    session = sessions.get(session_id)
    if session is None:
        session = Session(directory)
        sessions[session_id] = session
    elif session.directory != directory:
        raise ValueError("会话目录发生变化")
    return session


def _scan_event(
    request_id: int,
    session_id: str,
    session: Session,
    interval: int,
    attempted: int,
) -> dict:
    images, sampled = inventory(session.directory, interval)
    return {
        "id": request_id,
        "event": "scan_complete",
        "session": session_id,
        "image_count": len(images),
        "sampled_count": len(sampled),
        "successful_count": sum(image.name in session.scores for image in sampled),
        "failed_count": sum(image.name in session.failed for image in sampled),
        "attempted_count": attempted,
    }
