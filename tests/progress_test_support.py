from __future__ import annotations


MANUAL_TASK = {
    "preset": "manual",
    "capture": {
        "start_date": "2026-07-22",
        "start_at": "16:00",
        "end_date": "2026-07-22",
        "end_at": "20:00",
    },
}


def processing_state(
    *,
    hdr: tuple[int, int],
    sunset: tuple[int, int],
) -> dict:
    return {
        "status": "running",
        "progress": {"main_stage": "waiting_processing"},
        "children": [
            {
                "role": "bracketlapse-standby",
                "status": "running",
                "progress": {
                    "stage": "hdr",
                    "completed": hdr[0],
                    "total": hdr[1],
                },
            },
            {
                "role": "sunsetscore-resident",
                "status": "running",
                "progress": {
                    "stage": "sunset",
                    "completed": sunset[0],
                    "total": sunset[1],
                },
            },
        ],
    }
