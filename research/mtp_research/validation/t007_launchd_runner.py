"""Small launchd one-shot job helper for T007 proof runs.

The helper only writes auditable LaunchAgent artifacts. It does not trade, sign,
build transactions, or manage wallet/private-key paths.
"""

from __future__ import annotations

import json
import plistlib
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class LaunchdJobBundle:
    label: str
    output_dir: Path
    plist_path: Path
    manifest_path: Path
    status_path: Path
    stdout_path: Path
    stderr_path: Path


def _assert_safe_program_arguments(program_arguments: Sequence[str]) -> None:
    joined = " ".join(str(arg) for arg in program_arguments)
    forbidden = ["nohup", " &", "& ", "sendTransaction", "signTransaction", "simulateTransaction"]
    hit = [value for value in forbidden if value in joined]
    if hit:
        raise ValueError(f"Forbidden launchd command token(s): {hit}")


def _shell_join(parts: Sequence[str]) -> str:
    if not parts:
        raise ValueError("shell command parts must not be empty")
    return " ".join(shlex.quote(str(part)) for part in parts)


def build_status_recording_zsh_command(
    *,
    repo_root: Path | str,
    job_output_dir: Path | str,
    staging_root: Path | str,
    archive_root: Path | str,
    postprocess_output_dir: Path | str,
    collector_command: Sequence[str],
    postprocess_command: Sequence[str],
) -> str:
    """Build a launchd-safe zsh wrapper that records runtime exit codes.

    Exit codes must be captured by the launched shell at runtime. Do not embed
    shell variables into the generated Python status writer, because that can
    collapse to an empty string before launchd ever runs the job.
    """

    repo = Path(repo_root).expanduser()
    job = Path(job_output_dir).expanduser()
    staging = Path(staging_root).expanduser()
    archive = Path(archive_root).expanduser()
    post = Path(postprocess_output_dir).expanduser()
    status_path = job / "launchd_status.json"
    started_path = job / "collector_started.txt"
    finished_path = job / "collector_finished.txt"
    collector = _shell_join(collector_command)
    postprocess = _shell_join(postprocess_command)

    return "\n".join(
        [
            "set -u",
            f"cd {shlex.quote(str(repo))}",
            "if [ -f .env ]; then set -a; . ./.env; set +a; fi",
            f"mkdir -p {shlex.quote(str(job))} {shlex.quote(str(staging))} {shlex.quote(str(post))}",
            f"date > {shlex.quote(str(started_path))}",
            "COLLECTOR_EXIT=0",
            f"PYTHONPATH={shlex.quote(str(repo))} {collector} || COLLECTOR_EXIT=$?",
            f"date > {shlex.quote(str(finished_path))}",
            "POST_EXIT=0",
            f"PYTHONPATH={shlex.quote(str(repo))} {postprocess} || POST_EXIT=$?",
            f"COLLECTOR_EXIT=\"$COLLECTOR_EXIT\" POST_EXIT=\"$POST_EXIT\" PYTHONPATH={shlex.quote(str(repo))} python3 - <<'STATUSPY'",
            "from pathlib import Path",
            "import json, os, time",
            f"status = Path({str(status_path)!r})",
            "payload = json.loads(status.read_text()) if status.exists() else {}",
            "collector_exit = int(os.environ.get(\"COLLECTOR_EXIT\", \"0\"))",
            "postprocess_exit = int(os.environ.get(\"POST_EXIT\", \"0\"))",
            "payload.update({",
            "  \"status\": \"collector_process_exited\",",
            "  \"collector_exit_code\": collector_exit,",
            "  \"postprocess_exit_code\": postprocess_exit,",
            f"  \"staging_root\": {str(staging)!r},",
            f"  \"archive_root\": {str(archive)!r},",
            f"  \"postprocess_output_dir\": {str(post)!r},",
            "  \"finished_at_epoch\": time.time(),",
            "})",
            "status.write_text(json.dumps(payload, indent=2, sort_keys=True))",
            "STATUSPY",
            'FINAL_EXIT="$COLLECTOR_EXIT"',
            'if [ "$FINAL_EXIT" -eq 0 ]; then FINAL_EXIT="$POST_EXIT"; fi',
            'exit "$FINAL_EXIT"',
            "",
        ]
    )


def create_launchd_job_bundle(
    *,
    label: str,
    output_dir: Path | str,
    program_arguments: Sequence[str],
    working_directory: Path | str,
    environment: Mapping[str, str] | None = None,
    launch_agents_dir: Path | str | None = None,
) -> LaunchdJobBundle:
    """Write a one-shot LaunchAgent plist plus manifest/status files."""

    if not label.startswith("com.mtp."):
        raise ValueError("LaunchAgent label must start with com.mtp.")
    if not program_arguments:
        raise ValueError("ProgramArguments must not be empty")
    _assert_safe_program_arguments(program_arguments)

    output_path = Path(output_dir).expanduser()
    output_path.mkdir(parents=True, exist_ok=True)
    status_path = output_path / "launchd_status.json"
    stdout_path = output_path / "stdout.log"
    stderr_path = output_path / "stderr.log"
    agents_dir = Path(launch_agents_dir).expanduser() if launch_agents_dir else Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = agents_dir / f"{label}.plist"
    manifest_path = output_path / "launchd_manifest.json"

    plist = {
        "Label": label,
        "RunAtLoad": True,
        "KeepAlive": False,
        "WorkingDirectory": str(Path(working_directory).expanduser()),
        "ProgramArguments": [str(arg) for arg in program_arguments],
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
        "EnvironmentVariables": {str(k): str(v) for k, v in dict(environment or {}).items()},
    }
    with plist_path.open("wb") as handle:
        plistlib.dump(plist, handle, sort_keys=False)

    manifest = {
        "label": label,
        "output_dir": str(output_path),
        "plist_path": str(plist_path),
        "manifest_path": str(manifest_path),
        "status_path": str(status_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "working_directory": plist["WorkingDirectory"],
        "program_arguments": plist["ProgramArguments"],
        "environment_keys": sorted(plist["EnvironmentVariables"].keys()),
        "run_at_load": True,
        "keep_alive": False,
        "uses_nohup": False,
        "uses_shell_backgrounding": False,
        "created_at_epoch": time.time(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    status_path.write_text(
        json.dumps({"label": label, "status": "created", "created_at_epoch": time.time()}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return LaunchdJobBundle(
        label=label,
        output_dir=output_path,
        plist_path=plist_path,
        manifest_path=manifest_path,
        status_path=status_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
