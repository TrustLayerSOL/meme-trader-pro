import json
import os
import time

from core.json_store import atomic_write_json, locked_update_json
from core.storage import EventStore


LIVE_STATE_FILE = "live_state.json"


DEFAULT_STATE = {
    "last_updated": None,
    "events": [],
    "alerts": [],
    "tokens": {},
    "latest_tokens": {},
}


def load_state():
    if not os.path.exists(LIVE_STATE_FILE):
        save_state(DEFAULT_STATE)
        return DEFAULT_STATE.copy()

    try:
        with open(LIVE_STATE_FILE, "r") as f:
            state = json.load(f)
    except Exception:
        return DEFAULT_STATE.copy()

    state.setdefault("events", [])
    state.setdefault("alerts", [])
    state.setdefault("tokens", {})
    state.setdefault("latest_tokens", {})
    state.setdefault("last_updated", None)

    return state


def save_state(state):
    state["last_updated"] = time.time()
    atomic_write_json(LIVE_STATE_FILE, state)


def add_event(event):
    event["time"] = time.time()

    def updater(state):
        state.setdefault("events", [])
        state["events"].append(event)

        # Keep file from getting huge
        state["events"] = state["events"][-300:]
        state["last_updated"] = time.time()
        return state

    locked_update_json(LIVE_STATE_FILE, DEFAULT_STATE.copy(), updater)

    try:
        EventStore().insert_event(event)
    except Exception as exc:
        print("Failed to mirror event to SQLite:", exc)


def add_alert(alert):
    alert["time"] = time.time()

    def updater(state):
        state.setdefault("alerts", [])
        state["alerts"].append(alert)

        # Keep recent alerts only
        state["alerts"] = state["alerts"][-200:]
        state["last_updated"] = time.time()
        return state

    locked_update_json(LIVE_STATE_FILE, DEFAULT_STATE.copy(), updater)

    try:
        EventStore().insert_alert(alert)
    except Exception as exc:
        print("Failed to mirror alert to SQLite:", exc)


def update_token(mint, data):
    def updater(state):
        state.setdefault("tokens", {})

        if mint not in state["tokens"]:
            state["tokens"][mint] = {}

        state["tokens"][mint].update(data)
        state["tokens"][mint]["last_updated"] = time.time()

        state.setdefault("latest_tokens", {})
        state["latest_tokens"][mint] = state["tokens"][mint]
        state["last_updated"] = time.time()
        return state

    locked_update_json(LIVE_STATE_FILE, DEFAULT_STATE.copy(), updater)


def get_state():
    return load_state()
