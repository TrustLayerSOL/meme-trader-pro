import os
import signal
import subprocess


PROCESS_PATTERNS = {
    "dashboard": ["streamlit", "dashboard/dashboard.py"],
    "bot": ["main.py"],
    "watchdog": ["core.rug_watchdog"],
}


class ProcessGuard:
    def __init__(self, patterns=None):
        self.patterns = patterns or PROCESS_PATTERNS

    def pids_for(self, name):
        patterns = self.patterns.get(name, [])
        if not patterns:
            return []

        rows = self.process_rows()
        pids = []
        current_pid = os.getpid()
        for pid, command in rows:
            if pid == current_pid:
                continue
            if self.is_wrapper_process(command):
                continue
            if all(pattern in command for pattern in patterns):
                pids.append(pid)
        return sorted(set(pids))

    def is_running(self, name):
        return bool(self.pids_for(name))

    def status_rows(self):
        rows = []
        for name in ["dashboard", "bot", "watchdog"]:
            pids = self.pids_for(name)
            rows.append({
                "component": name,
                "running": bool(pids),
                "pids": ", ".join(str(pid) for pid in pids) if pids else "",
                "status": "RUNNING" if pids else "STOPPED",
            })
        return rows

    def terminate(self, name, timeout=8):
        pids = self.pids_for(name)
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        if not pids:
            return []

        deadline = timeout
        try:
            subprocess.run(["sleep", str(min(timeout, 1))], check=False)
        except Exception:
            pass

        remaining = self.pids_for(name)
        if deadline <= 1:
            return remaining

        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return self.pids_for(name)

    def process_rows(self):
        try:
            result = subprocess.run(
                ["ps", "-axo", "pid=,command="],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return []

        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            try:
                pid = int(parts[0])
            except Exception:
                continue
            rows.append((pid, parts[1]))
        return rows

    def is_wrapper_process(self, command):
        stripped = command.strip()
        return (
            stripped.startswith("SCREEN ")
            or stripped.startswith("login ")
            or stripped.startswith("bash -lc ")
            or stripped.startswith("/bin/bash -lc ")
            or stripped.startswith("/bin/zsh -c ")
        )
