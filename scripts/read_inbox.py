#!/usr/bin/env python3
"""Read and acknowledge Remote Codex Control inbox commands."""

from __future__ import annotations

import argparse
import json
import sys
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
            raise SystemExit(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
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


def format_command(command: dict[str, Any], verbose: bool = False) -> str:
    title = command.get("title") or "(no title)"
    header = f"{command.get('id')} [{command.get('status')}] {command.get('created_at')} - {title}"
    if verbose:
        text = f"{header}\n{command.get('body', '').rstrip()}"
        if command.get("status_note"):
            text += f"\n\nResult note:\n{command.get('status_note')}"
        return text
    preview = shorten(str(command.get("body", "")).replace("\n", " "), width=120, placeholder="...")
    text = f"{header}\n  {preview}"
    if command.get("status_note"):
        note = shorten(str(command.get("status_note", "")).replace("\n", " "), width=120, placeholder="...")
        text += f"\n  note: {note}"
    return text


def select_commands(commands: list[dict[str, Any]], include_seen: bool, all_statuses: bool) -> list[dict[str, Any]]:
    if all_statuses:
        return commands
    allowed = {"pending", "seen"} if include_seen else {"pending"}
    return [command for command in commands if command.get("status") in allowed]


def main() -> int:
    parser = argparse.ArgumentParser(description="Read or acknowledge mobile-submitted Codex commands.")
    parser.add_argument("--state-dir", help="Directory containing inbox.jsonl.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List commands.")
    list_parser.add_argument("--limit", type=int, default=10)
    list_parser.add_argument("--include-seen", action="store_true")
    list_parser.add_argument("--all", action="store_true", help="Show all statuses.")
    list_parser.add_argument("--verbose", action="store_true")

    next_parser = sub.add_parser("next", help="Show the oldest pending command.")
    next_parser.add_argument("--include-seen", action="store_true")
    next_parser.add_argument("--mark-seen", action="store_true")

    for name in ("seen", "done", "skipped"):
        status_parser = sub.add_parser(name, help=f"Mark a command {name}.")
        status_parser.add_argument("id")
        status_parser.add_argument("--note", default="")

    args = parser.parse_args()
    path = inbox_path(args.state_dir)
    records = read_records(path)
    commands = build_commands(records)

    if args.command == "list":
        selected = select_commands(commands, args.include_seen, args.all)
        if args.limit > 0:
            selected = selected[-args.limit:]
        if not selected:
            print("No matching commands.")
            return 0
        for command in selected:
            print(format_command(command, verbose=args.verbose))
        return 0

    if args.command == "next":
        selected = select_commands(commands, args.include_seen, False)
        if not selected:
            print("No pending commands.")
            return 0
        command = selected[0]
        print(format_command(command, verbose=True))
        if args.mark_seen and command.get("status") == "pending":
            append_status(path, str(command["id"]), "seen", "Read by Codex.")
            print(f"\nMarked seen: {command['id']}")
        return 0

    command_ids = {str(command.get("id")) for command in commands}
    if args.id not in command_ids:
        print(f"Unknown command id: {args.id}", file=sys.stderr)
        return 2
    append_status(path, args.id, args.command, args.note)
    print(f"Marked {args.command}: {args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
