"""Cam — write-only JSONL audit recorder. Never read back by the system.

Usage:
    from cam import cam_init, cam

    cam_init("driver_taskname")       # once at startup
    cam("api_request", model=m, ...)  # fire-and-forget, never raises

If CAM_DIR env var is unset or cam.py is not importable, everything is a no-op.
"""

import os, json, time, threading

CAM_DIR = os.environ.get("CAM_DIR", "")
_lock = threading.Lock()
_file = None


def cam_init(label):
    """Create JSONL output file. No-op if CAM_DIR unset."""
    global _file
    if not CAM_DIR:
        return
    try:
        os.makedirs(CAM_DIR, exist_ok=True)
        ts = time.strftime('%Y%m%d%H%M%S')
        _file = os.path.join(CAM_DIR, f"{label}_{ts}.jsonl")
    except Exception:
        pass


def cam(event, **data):
    """Append one JSONL record. Never raises."""
    if not _file:
        return
    try:
        record = {"ts": time.strftime('%Y-%m-%dT%H:%M:%S'), "event": event}
        record.update(data)
        line = json.dumps(record, default=str) + "\n"
        with _lock:
            with open(_file, "a") as f:
                f.write(line)
    except Exception:
        pass
