"""Durable exam history independent of pending queue membership."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from core.storage import serialized, write_json_atomic


def _path(queue_file: Path) -> Path:
    return Path(queue_file).with_name("exam-history.json")


def _read(queue_file: Path) -> dict:
    try:
        data = json.loads(_path(queue_file).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 2, "entries": {}}
    if not isinstance(data, dict) or data.get("version") not in {1, 2} or not isinstance(data.get("entries"), dict):
        raise ValueError("考试历史格式损坏，停止写入以保护记录")
    for entry in data["entries"].values():
        if not isinstance(entry, dict):
            raise ValueError("考试历史条目损坏，停止写入以保护记录")
        if data["version"] == 1:
            previous = entry.pop("submission", None)
            if isinstance(previous, dict):
                account = (previous.get("model_config") or {}).get("account") or "unbound"
                entry["submissions"] = {account: previous}
        if not isinstance(entry.get("submissions", {}), dict) or not isinstance(entry.get("failed_models", []), list):
            raise ValueError("考试历史字段损坏，停止写入以保护记录")
    data["version"] = 2
    return data


def failed_configs(url: str, queue_file: Path) -> list[dict]:
    return list(_read(queue_file)["entries"].get(url, {}).get("failed_models", []))


@serialized
def record_failures(url: str, configs: list[dict], queue_file: Path) -> None:
    if not configs:
        return
    data = _read(queue_file)
    entry = data["entries"].setdefault(url, {})
    previous = entry.setdefault("failed_models", [])
    changed = False
    for config in configs:
        if config not in previous:
            previous.append(config)
            changed = True
    if changed:
        write_json_atomic(_path(queue_file), data)


@serialized
def record_submission_intent(url: str, model_config: dict, queue_file: Path) -> None:
    data = _read(queue_file)
    entry = data["entries"].setdefault(url, {})
    account = model_config.get("account") or "unbound"
    entry.setdefault("submissions", {})[account] = {"state": "unverified", "model_config": model_config, "at": datetime.now(timezone.utc).isoformat()}
    write_json_atomic(_path(queue_file), data)


def pending_submission(url: str, queue_file: Path, *, account: str = "unbound") -> dict | None:
    submission = _read(queue_file)["entries"].get(url, {}).get("submissions", {}).get(account)
    return submission if isinstance(submission, dict) and submission.get("state") == "unverified" else None


@serialized
def finish_submission(url: str, state: str, queue_file: Path, *, account: str = "unbound") -> None:
    data = _read(queue_file)
    entry = data["entries"].get(url, {})
    submission = entry.get("submissions", {}).get(account)
    if submission is not None:
        submission["state"] = state
        write_json_atomic(_path(queue_file), data)
