"""Detect out-of-band edits to the requirements file before Confirm write."""
from __future__ import annotations

import hashlib
from typing import Any


FILE_CHANGED_ON_DISK = (
    "The requirements file changed on disk after this proposal. "
    "Cancel, then propose again so we re-read the file. "
    "Confirming now would overwrite those edits."
)


def fingerprint(helper: Any, user_path: str) -> dict[str, Any]:
    if hasattr(helper, "fingerprint"):
        return helper.fingerprint(user_path)
    if not helper.exists(user_path):
        return {"exists": False, "mtime_ns": None, "sha256": None}
    data = helper.read(user_path).encode("utf-8")
    return {
        "exists": True,
        "mtime_ns": None,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def stamp_baseline(helper: Any, user_path: str, proposed: dict[str, Any]) -> dict[str, Any]:
    if not proposed.get("baseline"):
        proposed["baseline"] = fingerprint(helper, user_path)
    return proposed


def reject_if_disk_changed(helper: Any, proposed: dict[str, Any]) -> None:
    baseline = proposed.get("baseline")
    path = proposed.get("path")
    if not isinstance(baseline, dict) or not path:
        return
    current = fingerprint(helper, path)
    if baseline.get("sha256") != current.get("sha256"):
        raise ValueError(FILE_CHANGED_ON_DISK)
