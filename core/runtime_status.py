import json
import os
import time
from pathlib import Path


STATUS_FILE = Path("data/runtime_status.json")


DEFAULT_STATUS = {
    "bot": {},
    "websocket": {},
    "scanner": {},
    "market": {},
    "quotes": {},
    "watchdog": {},
}


def now():
    return time.time()


def load_status():
    if not STATUS_FILE.exists():
        return DEFAULT_STATUS.copy()

    try:
        with open(STATUS_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return DEFAULT_STATUS.copy()

    for key, value in DEFAULT_STATUS.items():
        data.setdefault(key, value.copy())

    return data


def save_status(data):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATUS_FILE.with_suffix(".tmp")

    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)

    os.replace(tmp_path, STATUS_FILE)


def update_component(component, **fields):
    data = load_status()
    item = data.setdefault(component, {})
    item.update(fields)
    item["updated_at"] = now()
    save_status(data)
    return item


def increment_component(component, field, amount=1, **fields):
    data = load_status()
    item = data.setdefault(component, {})
    item[field] = int(item.get(field, 0) or 0) + amount
    item.update(fields)
    item["updated_at"] = now()
    save_status(data)
    return item
