#!/usr/bin/env python3
"""Run Codex only when a phone-submitted command arrives."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from textwrap import shorten
from typing import Any


APP_DIR = Path.home() / ".codex" / "remote-codex-control"
INBOX_FILE = "inbox.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def inbox_path(state_dir: str | None) -> Path:
    return Path(state_dir).expanduser() / INBOX_FILE if state_dir else APP_DIR / INBOX_FILE


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"Skipping invalid JSONL at {path}:{line_no}: {exc}", file=sys.stderr)
    return records


def append_status(path: Path, command_id: str, status: str, note: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "type": "status",
        "id": command_id,
        "status": status,
        "note": note,
        "created_at": utc_now(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_commands(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    commands: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        record_type = record.get("type")
        command_id = str(record.get("id", ""))
        if not command_id:
            continue
        if record_type == "command":
            item = dict(record)
            item["status"] = "pending"
            item["status_note"] = ""
            commands[command_id] = item
            order.append(command_id)
        elif record_type == "status" and command_id in commands:
            commands[command_id]["status"] = str(record.get("status", "pending"))
            commands[command_id]["status_note"] = str(record.get("note", ""))
            commands[command_id]["status_at"] = str(record.get("created_at", ""))
    return [commands[command_id] for command_id in order if command_id in commands]


def next_pending(path: Path) -> dict[str, Any] | None:
    for command in build_commands(read_records(path)):
        if command.get("status") == "pending":
            return command
    return None


def codex_command(command_name: str) -> str:
    found = shutil.which(command_name)
    if not found:
        raise RuntimeError(f"Could not find `{command_name}` on PATH.")
    return found


def make_prompt(command: dict[str, Any]) -> str:
    title = command.get("title") or "(no title)"
    body = str(command.get("body", "")).strip()
    return f"""You are processing a phone-submitted Remote Codex Control command.

Command id: {command.get("id")}
Title: {title}

User command:
{body}

Work normally in the selected workspace. If the request is clear and safe, complete it end to end.
If it is ambiguous, blocked, or unsafe, do the safe part and explain the blocker.
Final response requirements:
- Write a concise phone-visible summary of what you did.
- Mention whether verification passed, failed, or was not run.
- Mention any important file paths or commands.
- Keep the final response short enough to read on a phone.
"""


def run_codex(
    command: dict[str, Any],
    *,
    codex_bin: str,
    workdir: Path,
    sandbox: str,
    model: str | None,
    timeout_seconds: int,
    dry_run: bool,
) -> tuple[bool, str]:
    prompt = make_prompt(command)
    if dry_run:
        return True, f"Dry run: would process command {command.get('id')} in {workdir}."

    with tempfile.TemporaryDirectory(prefix="rcc-codex-") as tmp:
        output_file = Path(tmp) / "last-message.txt"
        cmd = [
            codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--cd",
            str(workdir),
            "--sandbox",
            sandbox,
            "--output-last-message",
            str(output_file),
        ]
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if output_file.exists():
            note = output_file.read_text(encoding="utf-8", errors="replace").strip()
        else:
            note = (result.stdout or result.stderr).strip()
        if not note:
            note = f"Codex exited with code {result.returncode} without a final message."
        note = shorten(note.replace("\r\n", "\n"), width=4000, placeholder="\n...[truncated]")
        return result.returncode == 0, note


def process_once(args: argparse.Namespace, path: Path, codex_bin: str) -> bool:
    command = next_pending(path)
    if not command:
        return False
    command_id = str(command["id"])
    title = command.get("title") or "(no title)"
    print(f"Processing {command_id}: {title}", flush=True)
    append_status(path, command_id, "running", "Codex is processing this command.")
    try:
        ok, note = run_codex(
            command,
            codex_bin=codex_bin,
            workdir=Path(args.workdir).expanduser().resolve(),
            sandbox=args.sandbox,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
            dry_run=args.dry_run,
        )
    except subprocess.TimeoutExpired:
        ok = False
        note = f"Timed out after {args.timeout_seconds} seconds."
    except Exception as exc:
        ok = False
        note = f"Worker failed before Codex completed: {exc}"
    append_status(path, command_id, "done" if ok else "skipped", note)
    print(f"Finished {command_id}: {'done' if ok else 'skipped'}", flush=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch the mobile inbox and run Codex only on new commands.")
    parser.add_argument("--state-dir", default=str(APP_DIR))
    parser.add_argument("--workdir", default=str(Path.cwd()), help="Workspace where Codex should run.")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="Local file polling interval. This does not use model tokens.")
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument("--sandbox", default="workspace-write", choices=["read-only", "workspace-write", "danger-full-access"])
    parser.add_argument("--model")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--once", action="store_true", help="Process at most one pending command and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Do not call Codex; mark pending commands with a dry-run note.")
    args = parser.parse_args()

    path = inbox_path(args.state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    try:
        codex_bin = codex_command(args.codex_command)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("Remote Codex event worker is running.")
    print(f"Inbox: {path}")
    print(f"Workspace: {Path(args.workdir).expanduser().resolve()}")
    print(f"Poll interval: {args.poll_seconds}s local file check, no model tokens while idle.")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            processed = process_once(args, path, codex_bin)
            if args.once:
                return 0
            if not processed:
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("\nEvent worker stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
