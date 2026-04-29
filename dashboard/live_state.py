import json
import os
import time

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
    with open(LIVE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def add_event(event):
    state = load_state()

    event["time"] = time.time()

    state.setdefault("events", [])
    state["events"].append(event)

    # Keep file from getting huge
    state["events"] = state["events"][-300:]

    save_state(state)

    try:
        EventStore().insert_event(event)
    except Exception:
        pass


def add_alert(alert):
    state = load_state()

    alert["time"] = time.time()

    state.setdefault("alerts", [])
    state["alerts"].append(alert)

    # Keep recent alerts only
    state["alerts"] = state["alerts"][-200:]

    save_state(state)

    try:
        EventStore().insert_alert(alert)
    except Exception:
        pass


def update_token(mint, data):
    state = load_state()

    state.setdefault("tokens", {})

    if mint not in state["tokens"]:
        state["tokens"][mint] = {}

    state["tokens"][mint].update(data)
    state["tokens"][mint]["last_updated"] = time.time()

    state.setdefault("latest_tokens", {})
    state["latest_tokens"][mint] = state["tokens"][mint]

    save_state(state)


def get_state():
    return load_state()
