from core.open_position_monitor import run_once


if __name__ == "__main__":
    import json
    print(json.dumps(run_once(), indent=2, sort_keys=True))
