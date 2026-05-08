#!/usr/bin/env python3
"""Start a remote-friendly phone command session for Codex."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode


APP_DIR = Path.home() / ".codex" / "remote-codex-control"
CONFIG_FILE = "config.json"
BRIDGE_SCRIPT = Path(__file__).with_name("start_mobile_bridge.py")
EVENT_WORKER_SCRIPT = Path(__file__).with_name("event_worker.py")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_config(state_dir: Path) -> dict[str, object]:
    path = state_dir / CONFIG_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(state_dir: Path, config: dict[str, object]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / CONFIG_FILE).write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def find_executable(name: str, windows_extra: list[Path] | None = None) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if windows_extra:
        for path in windows_extra:
            if path.exists():
                return str(path)
    return None


def tailscale_ip() -> str:
    exe = find_executable(
        "tailscale",
        [
            Path("C:/Program Files/Tailscale/tailscale.exe"),
            Path.home() / "AppData/Local/Tailscale/tailscale.exe",
        ],
    )
    if not exe:
        raise RuntimeError("Tailscale CLI was not found. Install Tailscale on this computer first.")
    result = subprocess.run(
        [exe, "ip", "-4"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"`tailscale ip -4` failed. Is Tailscale logged in and running? {detail}")
    ips = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not ips:
        raise RuntimeError("Tailscale did not return an IPv4 address.")
    return ips[0]


def resolve_token(state_dir: Path, reset_token: bool) -> str:
    config = load_config(state_dir)
    token = str(config.get("token") or "")
    if reset_token or not token:
        token = secrets.token_urlsafe(24)
    config.update({"token": token, "updated_at": utc_now()})
    save_config(state_dir, config)
    return token


def make_url(host: str, port: int, token: str) -> str:
    return f"http://{host}:{port}/?{urlencode({'token': token})}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Remote Codex Control for away-from-home use.")
    parser.add_argument("--mode", choices=["tailscale"], default="tailscale")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", default=str(APP_DIR))
    parser.add_argument("--reset-token", action="store_true")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host for the bridge. Keep 0.0.0.0 for Tailscale access.",
    )
    parser.add_argument("--event-worker", action="store_true", help="Also run Codex automatically when phone commands arrive.")
    parser.add_argument("--workdir", default=str(Path.cwd()), help="Workspace for event-worker Codex runs.")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="Local inbox polling interval for event worker.")
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument("--sandbox", default="workspace-write", choices=["read-only", "workspace-write", "danger-full-access"])
    parser.add_argument("--model")
    args = parser.parse_args()

    state_dir = Path(args.state_dir).expanduser()
    token = resolve_token(state_dir, args.reset_token)

    try:
        remote_host = tailscale_ip()
    except RuntimeError as exc:
        print(f"Cannot prepare away session: {exc}", file=sys.stderr)
        print("Fallback: install and log in to Tailscale on both the computer and phone.", file=sys.stderr)
        return 2

    phone_url = make_url(remote_host, args.port, token)
    print("Away session prepared.")
    print(f"Phone URL over Tailscale: {phone_url}")
    print(f"Inbox: {state_dir / 'inbox.jsonl'}")
    print("Before leaving, open this URL on your phone once while Tailscale is connected.")
    if args.event_worker:
        print("Event worker: enabled. Phone commands will trigger Codex runs without heartbeat polling.")
        print(f"Event worker workspace: {Path(args.workdir).expanduser().resolve()}")
    print("Starting bridge now. Keep this terminal open; press Ctrl+C to stop.")
    print()

    bridge_cmd = [
        sys.executable,
        str(BRIDGE_SCRIPT),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--state-dir",
        str(state_dir),
        "--token",
        token,
    ]
    if not args.event_worker:
        return subprocess.call(bridge_cmd)

    worker_cmd = [
        sys.executable,
        str(EVENT_WORKER_SCRIPT),
        "--state-dir",
        str(state_dir),
        "--workdir",
        str(Path(args.workdir).expanduser()),
        "--poll-seconds",
        str(args.poll_seconds),
        "--codex-command",
        args.codex_command,
        "--sandbox",
        args.sandbox,
    ]
    if args.model:
        worker_cmd.extend(["--model", args.model])

    processes = [
        subprocess.Popen(bridge_cmd),
        subprocess.Popen(worker_cmd),
    ]
    try:
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    print(f"Subprocess exited with code {code}; stopping away session.", file=sys.stderr)
                    return code
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping bridge and event worker.")
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
