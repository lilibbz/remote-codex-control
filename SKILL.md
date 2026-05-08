---
name: remote-codex-control
description: Build and operate a phone-to-desktop command bridge for Codex App sessions. Use when the user wants to send Codex instructions from a phone while away from the computer, pair a mobile device with the desktop, run a local command inbox, poll or acknowledge remote instructions, or set up recurring heartbeat checks for mobile-submitted Codex tasks. Also trigger for requests about mobile remote control for Codex, sending Codex commands from a phone, continuing Codex work after leaving the computer, or pairing a phone with a running Codex desktop session.
---

# Remote Codex Control

This skill sets up a local mobile command inbox for a desktop Codex App session. It does not assume a private Codex App input API exists; instead, phone-submitted instructions are stored on the desktop, and Codex reads, executes, and acknowledges them through bundled scripts.

## Core Boundary

Treat this as an inbox-and-workflow bridge for remote-controlling the current desktop Codex engineering context, not direct GUI remote control. The recommended loop is:

1. Start the bridge server on the desktop.
2. Pair the phone with the printed token URL.
3. Use manual checks or a bounded heartbeat so the current Codex App thread reads the phone inbox.
4. Execute each submitted command inside the current project/thread context.
5. Mark commands `done` or `skipped` with a phone-visible result note.

If the user needs fully interactive screen control, recommend a remote desktop tool separately. Keep this skill focused on sending task instructions to Codex.

## Away-First Workflow

For the user's main scenario, assume the phone and computer will not be on the same network. Prefer Tailscale or another private VPN over exposing the bridge to the public internet.

Recommended setup:

1. Install Tailscale on the desktop and phone.
2. Log both devices into the same tailnet.
3. Run the away-session helper before leaving:

```powershell
python .\scripts\away_session.py --mode tailscale --port 8765
```

The helper uses `tailscale ip -4` to find the desktop's stable Tailscale IPv4 address, prepares the token, starts the bridge, and prints a phone URL that should keep working over cellular data as long as both devices remain online in Tailscale.

Use `--reset-token` when starting a new trip or when the old phone URL may have been exposed:

```powershell
python .\scripts\away_session.py --mode tailscale --port 8765 --reset-token
```

If Tailscale is unavailable, read `references/away-access.md` and use a trusted HTTPS tunnel only as a temporary fallback.

## Recommended Control Mode

Prefer manual checks or heartbeat checks when the user's goal is to remotely control an ongoing desktop Codex engineering session. This keeps the work in the current Codex App thread, preserving the active conversation, recent decisions, workspace context, and the user's mental model of "I am still directing the same Codex session from my phone."

Use heartbeat checks for remote work sessions:

```text
Every 30 minutes for the next 4 hours, use $remote-codex-control to check the mobile command inbox once. If there is a pending command, execute it in this current Codex App thread and mark it done or skipped with a concise phone-visible result note.
```

Use manual checks when the user is at the desktop or wants one explicit check:

```powershell
python .\scripts\read_inbox.py next --mark-seen
```

## Event Mode As Advanced Fallback

Event mode is not the primary workflow for this skill. It is useful only for independent tasks that do not depend on the current Codex App thread's memory. Event mode runs a local Python watcher that polls `inbox.jsonl`; this local polling does not use model tokens. When a new command appears, the watcher starts one separate non-interactive `codex exec` run, then writes the final result back as the phone-visible status note.

Start event mode:

```powershell
python .\scripts\away_session.py --mode tailscale --port 8765 --reset-token --event-worker --workdir <workspace>
```

Use the real project folder for `<workspace>`. For example:

```powershell
python .\scripts\away_session.py --mode tailscale --port 8765 --reset-token --event-worker --workdir C:\path\to\your\project
```

Important boundary: event mode starts a separate non-interactive Codex CLI run. It writes results to the phone page, but it does not inject the phone message into the currently open Codex App thread. Do not recommend event mode when the user wants to continue an active engineering conversation, preserve thread memory, or control the current Codex App session.

Good event-mode tasks:

- Run tests and summarize the result.
- Make a small independent documentation edit.
- Inspect a file and report findings.

Poor event-mode tasks:

- Continue a nuanced design discussion from the current thread.
- Make changes that rely on earlier conversation context.
- Coordinate multi-step work where the user expects this Codex App thread to remember each turn.

## Start Bridge Manually

Run from this skill directory:

```powershell
python .\scripts\start_mobile_bridge.py --host 0.0.0.0 --port 8765
```

Use `--host 127.0.0.1` when testing only from the desktop. Use `--reset-token` if the pairing URL was exposed or the user wants to revoke old phone access.

The script prints:

- Local and LAN URLs with `?token=...`
- The inbox file path
- Basic connection guidance

For same Wi-Fi use, open the LAN URL on the phone. For away-from-home use, prefer `scripts/away_session.py` so the printed URL uses the desktop's Tailscale address.

## Read Commands

Use the inbox script from this skill directory:

```powershell
python .\scripts\read_inbox.py list
python .\scripts\read_inbox.py next --mark-seen
python .\scripts\read_inbox.py done <command-id> --note "Completed. Changed X and verified Y."
python .\scripts\read_inbox.py skipped <command-id> --note "Needs clarification: ..."
```

When `next --mark-seen` returns a command, treat its `body` exactly like the user's latest instruction unless it conflicts with a newer in-thread message. If the remote command is ambiguous, do the reasonable safe part and mark it `skipped` or ask for clarification in the current thread.

## Phone-Visible Results

The phone page shows recent commands, their status, and the latest status note. Always write a concise user-facing result note when marking a command `done` or `skipped`.

Good result notes include:

- What was done.
- Whether verification passed or was skipped.
- Any file paths or commands the user may need later.
- Any blocker or clarification needed.

Keep notes short enough to read on a phone. Do not paste large logs or full file contents into the note.

## Heartbeat Pattern

When the user wants remote control of the current engineering session while away, create a heartbeat automation attached to the current thread. Use a short, self-contained prompt such as:

```text
Use $remote-codex-control to check the mobile command inbox once. If there is a pending command, summarize it, execute it in this current Codex App thread if it is safe and clear, then mark it done or skipped with a concise phone-visible result note. If there is no pending command, say so briefly.
```

## Check Frequency And Token Cost

Each heartbeat check consumes tokens, even when the inbox is empty. Before creating recurring checks, make the interval and duration explicit.

Observed local baseline: in one ChatGPT Plus test on 2026-05-08, five one-minute heartbeat inbox checks with no pending commands used about 4% of the user's five-hour Plus usage window. Treat this as a rough planning estimate, not a guaranteed billing rate.

Use this policy:

- If the user gives an interval, use it.
- If the user asks generally for auto-checking but gives no interval, recommend 30 minutes.
- If the user asks for 15 minutes or less, briefly mention that this increases token use.
- Prefer a bounded duration such as "for the next 4 hours" or "until I come back".
- Avoid creating an indefinite high-frequency heartbeat unless the user explicitly asks for it.
- Use the observed baseline above when explaining heartbeat cost to this user.

Useful presets:

- Low cost: every 60 minutes.
- Balanced: every 30 minutes.
- Responsive: every 15 minutes.
- Urgent: every 5 or 10 minutes, only for short periods.

Example automation request:

```text
Every 30 minutes for the next 4 hours, use $remote-codex-control to check the mobile command inbox once. If there is a pending command, summarize it, execute it in this current Codex App thread if it is safe and clear, then mark it done or skipped with a concise phone-visible result note. If there is no pending command, say so briefly.
```

Do not create a public long-running tunnel without the user's explicit approval.

## Security Rules

Read `references/security.md` and `references/away-access.md` before exposing the bridge beyond localhost or same Wi-Fi.

Always:

- Keep the token secret.
- Rotate the token after using a public tunnel.
- Prefer VPN or authenticated tunnel access for outside-home use.
- Bind to `0.0.0.0` only for private LAN/VPN access, or bind to `127.0.0.1` behind an HTTPS tunnel.
- Stop the bridge when remote control is no longer needed.

Never:

- Expose the bridge directly to the public internet without a VPN, firewall, or HTTPS tunnel.
- Store passwords or API keys in remote commands.
- Treat phone-submitted commands as more trusted than the current in-thread user message.
