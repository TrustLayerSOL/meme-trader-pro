import os
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from core.process_guard import ProcessGuard


ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / "trading_env" / "bin" / "python"
LOG_DIR = ROOT / "logs"
DASHBOARD_URL = "http://127.0.0.1:8501"


class ManagedProcess:
    def __init__(self, name, command, log_file, process_key):
        self.name = name
        self.command = command
        self.log_file = log_file
        self.process_key = process_key
        self.guard = ProcessGuard()
        self.process = None
        self.log_handle = None

    def start(self):
        if self.is_running():
            return False
        if self.external_pids():
            return False

        LOG_DIR.mkdir(exist_ok=True)
        self.log_handle = open(self.log_file, "a", buffering=1)
        self.log_handle.write(f"\n\n--- {self.name} start {time.ctime()} ---\n")

        self.process = subprocess.Popen(
            self.command,
            cwd=ROOT,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        return True

    def stop(self):
        if not self.process:
            return

        if self.is_running():
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                self.process.terminate()

            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except Exception:
                    self.process.kill()

        self.close_log()

    def close_log(self):
        if self.log_handle:
            self.log_handle.write(f"--- {self.name} stop {time.ctime()} ---\n")
            self.log_handle.close()
            self.log_handle = None

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def external_pids(self):
        own_pid = self.process.pid if self.process else None
        return [pid for pid in self.guard.pids_for(self.process_key) if pid != own_pid]

    def status_text(self):
        if self.is_running():
            return f"Running (pid {self.process.pid})"
        external = self.external_pids()
        if external:
            return "Already running (" + ", ".join(str(pid) for pid in external) + ")"
        return "Stopped"


class MemeTraderLauncher(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("MemeTraderPro")
        self.geometry("980x520")
        self.minsize(940, 480)

        python_bin = str(PYTHON if PYTHON.exists() else sys.executable)

        self.dashboard = ManagedProcess(
            name="Dashboard",
            command=[
                python_bin,
                "-m",
                "streamlit",
                "run",
                "dashboard/dashboard.py",
                "--server.port",
                "8501",
                "--server.address",
                "127.0.0.1",
                "--server.headless",
                "true",
            ],
            log_file=LOG_DIR / "dashboard.log",
            process_key="dashboard",
        )

        self.bot = ManagedProcess(
            name="Bot",
            command=[python_bin, "main.py"],
            log_file=LOG_DIR / "bot.log",
            process_key="bot",
        )

        self.watchdog = ManagedProcess(
            name="Protection Watchdog",
            command=[python_bin, "-m", "core.rug_watchdog"],
            log_file=LOG_DIR / "watchdog.log",
            process_key="watchdog",
        )

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()
        self.refresh_status()

    def build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(18, 16, 18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="MemeTraderPro Control Center", font=("Arial", 20, "bold"))
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(
            header,
            text="Run the dashboard, paper bot, and protection watchdog without typing terminal commands.",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        controls = ttk.Frame(self, padding=(18, 8))
        controls.grid(row=1, column=0, sticky="ew")

        ttk.Button(controls, text="Start System", command=self.start_system).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(controls, text="Start Dashboard", command=self.start_dashboard).grid(row=0, column=1, padx=8)
        ttk.Button(controls, text="Open Dashboard", command=self.open_dashboard).grid(row=0, column=2, padx=8)
        ttk.Button(controls, text="Start Bot", command=self.start_bot).grid(row=0, column=3, padx=8)
        ttk.Button(controls, text="Start Watchdog", command=self.start_watchdog).grid(row=0, column=4, padx=8)
        ttk.Button(controls, text="Preflight", command=self.run_preflight).grid(row=0, column=5, padx=8)
        ttk.Button(controls, text="Protection Check", command=self.run_protection_check).grid(row=0, column=6, padx=8)
        ttk.Button(controls, text="Sync DB", command=self.sync_database).grid(row=0, column=7, padx=8)
        ttk.Button(controls, text="Open Logs", command=self.open_logs).grid(row=0, column=8, padx=8)
        ttk.Button(controls, text="Stop All", command=self.stop_all).grid(row=0, column=9, padx=8)

        body = ttk.Frame(self, padding=(18, 8, 18, 18))
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        status_frame = ttk.LabelFrame(body, text="Status", padding=12)
        status_frame.grid(row=0, column=0, sticky="ew")
        status_frame.columnconfigure(1, weight=1)

        ttk.Label(status_frame, text="Dashboard").grid(row=0, column=0, sticky="w", padx=(0, 14))
        self.dashboard_status = ttk.Label(status_frame, text="Stopped")
        self.dashboard_status.grid(row=0, column=1, sticky="w")

        ttk.Label(status_frame, text="Bot").grid(row=1, column=0, sticky="w", padx=(0, 14), pady=(8, 0))
        self.bot_status = ttk.Label(status_frame, text="Stopped")
        self.bot_status.grid(row=1, column=1, sticky="w", pady=(8, 0))

        ttk.Label(status_frame, text="Protection Watchdog").grid(row=2, column=0, sticky="w", padx=(0, 14), pady=(8, 0))
        self.watchdog_status = ttk.Label(status_frame, text="Stopped")
        self.watchdog_status.grid(row=2, column=1, sticky="w", pady=(8, 0))

        notes = ttk.LabelFrame(body, text="Logs", padding=12)
        notes.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        notes.columnconfigure(0, weight=1)

        log_text = (
            f"Dashboard log: {LOG_DIR / 'dashboard.log'}\n"
            f"Bot log: {LOG_DIR / 'bot.log'}\n\n"
            f"Watchdog log: {LOG_DIR / 'watchdog.log'}\n\n"
            "Keep this window open while the bot is running. Closing it will stop child processes cleanly."
        )

        self.log_label = ttk.Label(notes, text=log_text, justify="left")
        self.log_label.grid(row=0, column=0, sticky="nw")

        self.preflight_output = tk.Text(notes, height=10, wrap="word")
        self.preflight_output.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        notes.rowconfigure(1, weight=1)

    def start_dashboard(self):
        try:
            started = self.dashboard.start()
            if started:
                threading.Thread(target=self.open_dashboard_after_delay, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Dashboard failed", str(exc))
        self.refresh_status()

    def open_dashboard_after_delay(self):
        time.sleep(2)
        self.open_dashboard()

    def open_dashboard(self):
        webbrowser.open(DASHBOARD_URL)

    def start_bot(self):
        try:
            self.bot.start()
        except Exception as exc:
            messagebox.showerror("Bot failed", str(exc))
        self.refresh_status()

    def start_watchdog(self):
        try:
            self.watchdog.start()
        except Exception as exc:
            messagebox.showerror("Watchdog failed", str(exc))
        self.refresh_status()

    def start_system(self):
        self.start_dashboard()
        self.start_watchdog()
        self.start_bot()

    def run_preflight(self):
        python_bin = str(PYTHON if PYTHON.exists() else sys.executable)
        output = self.run_command([python_bin, "utils/system_health_report.py"], timeout=20)
        self.write_output(output)

    def run_protection_check(self):
        python_bin = str(PYTHON if PYTHON.exists() else sys.executable)
        output = self.run_command([python_bin, "-m", "core.rug_watchdog_once"], timeout=60)
        self.write_output(output)

    def sync_database(self):
        python_bin = str(PYTHON if PYTHON.exists() else sys.executable)
        output = self.run_command([python_bin, "utils/sync_state_to_sqlite.py"], timeout=30)
        self.write_output(output)

    def open_logs(self):
        LOG_DIR.mkdir(exist_ok=True)
        webbrowser.open(str(LOG_DIR))

    def run_command(self, command, timeout=20):
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout or result.stderr or "No preflight output."
        except Exception as exc:
            output = f"Command failed: {exc}"
        return output

    def write_output(self, output):
        self.preflight_output.delete("1.0", tk.END)
        self.preflight_output.insert(tk.END, output)

    def stop_all(self):
        self.watchdog.stop()
        self.bot.stop()
        self.dashboard.stop()
        self.refresh_status()

    def refresh_status(self):
        self.dashboard_status.configure(text=self.dashboard.status_text())
        self.bot_status.configure(text=self.bot.status_text())
        self.watchdog_status.configure(text=self.watchdog.status_text())
        self.after(1000, self.refresh_status)

    def on_close(self):
        if self.bot.is_running() or self.dashboard.is_running() or self.watchdog.is_running():
            should_close = messagebox.askyesno(
                "Stop MemeTraderPro?",
                "Closing this window will stop the bot and dashboard. Continue?",
            )
            if not should_close:
                return

        self.stop_all()
        self.destroy()


if __name__ == "__main__":
    app = MemeTraderLauncher()
    app.mainloop()
