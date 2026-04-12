from __future__ import annotations

from jarvis.brain_core.job_status_service import JobStatusService


def status(service: JobStatusService) -> dict:
    current = service.get_current()
    if current is None:
        return {"state": "IDLE", "progress": 0.0}
    return {
        "job_id": current.job_id,
        "state": current.state,
        "stage": current.stage,
        "progress": current.percent,
        "eta": current.eta,
    }


def subscribe_on_complete(
    service: JobStatusService, turn_id: str, speaker_id: str, channel: str
) -> dict:
    sub = service.subscribe_on_complete(
        turn_id=turn_id, speaker_id=speaker_id, channel=channel
    )
    return {"subscribed": sub.subscribed, "turn_id": sub.turn_id}


def cancel(service: JobStatusService, force: bool = False) -> dict:
    current = service.get_current()
    if current is None:
        return {"ok": False, "reason": "no_active_job"}
    result = service.cancel(job_id=current.job_id, force=force)
    return {"ok": result.acknowledged, "job_id": result.job_id, "force": result.force}
