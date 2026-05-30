import copy
import json
import os
import tempfile
from pathlib import Path


try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None


def read_json(path, default):
    path = Path(path)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return copy.deepcopy(default)


def atomic_write_json(path, data, indent=2):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass


class JsonFileLock:
    def __init__(self, path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.handle = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.lock_path, "a+")
        if fcntl:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle:
            if fcntl:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def locked_update_json(path, default, updater):
    with JsonFileLock(path):
        data = read_json(path, default)
        result = updater(data)
        if result is not None:
            data = result
        atomic_write_json(path, data)
        return data
