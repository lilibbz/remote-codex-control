# Remote Codex Control

Remote Codex Control is a Codex skill that lets you send instructions from a phone to a desktop Codex App session, then view concise execution results on the phone.

The main use case is leaving your computer while a Codex engineering session is still running. Your phone sends commands into a local desktop inbox; the current Codex App thread checks that inbox manually or through a bounded heartbeat, executes the work in the active project context, and writes a phone-visible result note.

## What It Does

- Starts a small token-protected HTTP bridge on the desktop.
- Serves a mobile-friendly command page.
- Stores phone-submitted commands in `inbox.jsonl` on the desktop.
- Lets Codex read, acknowledge, complete, or skip commands.
- Shows recent command status and result notes on the phone.
- Supports Tailscale-based away-from-home access.
- Includes an optional event worker for independent background tasks.

## Recommended Architecture

```text
Phone browser
  -> Tailscale private IP
  -> desktop bridge server
  -> inbox.jsonl
  -> current Codex App thread via manual check or heartbeat
  -> phone-visible result note
```

The recommended mode is current-thread control. This preserves the active Codex App conversation, recent engineering decisions, and workspace context.

## Requirements

- Codex App on the desktop.
- Python 3.10 or newer.
- Tailscale on the desktop and phone for away-from-home access.
- A phone browser.

No router port forwarding is required or recommended.

## Installation

Clone or download this repository into your Codex skills directory:

```powershell
cd $HOME\.codex\skills
git clone https://github.com/YOUR_NAME/remote-codex-control.git
```

Restart or refresh Codex App so the skill is discoverable as:

```text
$remote-codex-control
```

## One-Time Tailscale Setup

1. Install Tailscale on your desktop.
2. Install Tailscale on your phone.
3. Log both devices into the same tailnet.
4. Confirm both devices are online in the Tailscale app.
5. Optional: ping between devices to verify connectivity.

## Start An Away Session

Run this on the desktop before leaving:

```powershell
cd $HOME\.codex\skills\remote-codex-control
python .\scripts\away_session.py --mode tailscale --port 8765 --reset-token
```

The script prints a URL like:

```text
Phone URL over Tailscale: http://100.x.y.z:8765/?token=...
```

Open that full URL on your phone while Tailscale is connected.

Keep the PowerShell window open. Press `Ctrl+C` when you want to stop remote access.

## Send A Test Command

On the phone page, enter:

```text
Test: please confirm that you received this phone command.
```

Tap `Send to desktop Codex`. If the page shows `Sent: ...`, the command reached the desktop inbox.

## Current-Thread Control

Ask Codex in the active desktop thread to check once:

```text
Use $remote-codex-control to check the mobile command inbox once.
```

Or create a bounded heartbeat:

```text
Every 30 minutes for the next 4 hours, use $remote-codex-control to check the mobile command inbox once. If there is a pending command, execute it in this current Codex App thread and write a concise phone-visible result note.
```

This is the recommended workflow because it keeps the active Codex App thread in control.

## Manual Inbox Commands

From the skill directory:

```powershell
python .\scripts\read_inbox.py list
python .\scripts\read_inbox.py next --mark-seen
python .\scripts\read_inbox.py done <command-id> --note "Completed. Changed X and verified Y."
python .\scripts\read_inbox.py skipped <command-id> --note "Needs clarification: ..."
```

The phone page refreshes recent command statuses every few seconds.

## Optional Event Mode

Event mode starts a local Python watcher that consumes no model tokens while idle. When a phone command arrives, it launches a separate non-interactive `codex exec` run and writes the result back to the phone page.

Use it only for independent tasks that do not require the current Codex App thread's memory:

```powershell
python .\scripts\away_session.py --mode tailscale --port 8765 --reset-token --event-worker --workdir C:\path\to\your\project
```

Do not use event mode when you need continuity with the active Codex App conversation.

## Token And Usage Notes

Heartbeat checks consume usage even when the inbox is empty. In one ChatGPT Plus test on 2026-05-08, five one-minute heartbeat checks with no pending commands used about 4% of the user's five-hour Plus usage window. Treat this only as a rough planning estimate because usage can vary by model, context, and whether commands are executed.

Recommended presets:

- Every 60 minutes: lowest cost.
- Every 30 minutes: balanced default.
- Every 15 minutes: responsive, moderate cost.
- Every 5 or 10 minutes: short urgent windows only.

Prefer bounded sessions, such as "for the next 4 hours".

## Security

- Keep the token URL private.
- Rotate the token with `--reset-token` before each new trip.
- Do not send passwords, API keys, or secrets through the phone page.
- Prefer Tailscale or another private VPN.
- Do not expose port `8765` directly to the public internet.
- Do not use router port forwarding.
- Stop the bridge when remote access is no longer needed.

See [references/security.md](references/security.md) and [references/away-access.md](references/away-access.md).

## Validation

Run:

```powershell
python -m py_compile .\scripts\away_session.py .\scripts\event_worker.py .\scripts\read_inbox.py .\scripts\start_mobile_bridge.py
python .\scripts\away_session.py --help
python .\scripts\read_inbox.py list
```

If this repository is installed as a Codex skill, also validate:

```powershell
python $HOME\.codex\skills\.system\skill-creator\scripts\quick_validate.py $HOME\.codex\skills\remote-codex-control
```

## Project Status

This is an early practical prototype. The stable core is the phone inbox, Tailscale access pattern, manual/heartbeat current-thread control, and phone-visible result notes.

Potential future improvements:

- Better mobile UI controls.
- Command search and filters.
- Per-device command views.
- Optional local PIN in addition to the token.
- Cleaner setup wizard.
- Automated tests for the bridge API.
