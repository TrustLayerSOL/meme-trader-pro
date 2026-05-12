import time
from pathlib import Path

from core.json_store import locked_update_json, read_json

STATUS_FILE = Path("data/runtime_status.json")


DEFAULT_STATUS = {
    "bot": {},
    "websocket": {},
    "scanner": {},
    "market": {},
    "quotes": {},
    "watchdog": {},
    "open_position_monitor": {},
    "wallet_discovery": {},
}


def now():
    return time.time()


def load_status():
    data = read_json(STATUS_FILE, DEFAULT_STATUS.copy())

    for key, value in DEFAULT_STATUS.items():
        data.setdefault(key, value.copy())

    return data


def save_status(data):
    locked_update_json(STATUS_FILE, DEFAULT_STATUS.copy(), lambda _data: data)


def update_component(component, **fields):
    updated = {}

    def updater(data):
        item = data.setdefault(component, {})
        item.update(fields)
        item["updated_at"] = now()
        updated.update(item)
        return data

    locked_update_json(STATUS_FILE, DEFAULT_STATUS.copy(), updater)
    return updated


def increment_component(component, field, amount=1, **fields):
    updated = {}

    def updater(data):
        item = data.setdefault(component, {})
        item[field] = int(item.get(field, 0) or 0) + amount
        item.update(fields)
        item["updated_at"] = now()
        updated.update(item)
        return data

    locked_update_json(STATUS_FILE, DEFAULT_STATUS.copy(), updater)
    return updated
