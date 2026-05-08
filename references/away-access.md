# Away Access

This skill is optimized for the user leaving the computer while still sending Codex instructions from a phone.

## Preferred: Tailscale Private VPN

Use Tailscale when the phone and computer are not on the same Wi-Fi. Tailscale assigns the desktop a stable `100.x.y.z` private address inside the user's tailnet. Official Tailscale docs describe `tailscale ip -4` as the CLI command for retrieving the device's IPv4 address.

One-time setup:

1. Install Tailscale on the Windows computer.
2. Install Tailscale on the phone.
3. Log both devices into the same account or tailnet.
4. Confirm both devices are connected in the Tailscale app.

Before leaving:

```powershell
cd $HOME\.codex\skills\remote-codex-control
python .\scripts\away_session.py --mode tailscale --port 8765 --reset-token
```

For remote engineering control, keep Codex App open and use a bounded heartbeat in the current thread. This preserves the active conversation and project context while letting the phone send instructions.

Example current-thread heartbeat:

```text
Every 30 minutes for the next 4 hours, use $remote-codex-control to check the mobile command inbox once. If there is a pending command, execute it in this current Codex App thread and write a concise phone-visible result note.
```

Event mode is an advanced fallback for independent tasks that do not need current-thread memory. It starts a separate non-interactive Codex CLI run:

```powershell
python .\scripts\away_session.py --mode tailscale --port 8765 --reset-token --event-worker --workdir C:\path\to\your\project
```

Event mode uses a local file watcher while idle, so idle checks do not consume model tokens. A Codex run is started only when the phone submits a command. The run is non-interactive and separate from the currently open Codex App thread, so do not use it when the user expects the active thread's memory and decisions to carry forward.

Open the printed `Phone URL over Tailscale` on the phone. The URL should continue to work over cellular data if:

- The desktop remains powered on and online.
- Codex App remains open if heartbeat checks are expected.
- The bridge terminal remains running.
- Tailscale remains connected on both devices.

## Choosing A Check Interval

Automatic checks trade responsiveness for token use. Choose the interval before leaving:

In one ChatGPT Plus test on 2026-05-08, five one-minute heartbeat inbox checks with no pending commands used about 4% of the user's five-hour Plus usage window. Use this only as a rough estimate because actual usage can vary by model, context, and whether commands are executed.

- Every 60 minutes: lowest cost, good for occasional updates.
- Every 30 minutes: recommended default.
- Every 15 minutes: responsive, moderate cost.
- Every 5 or 10 minutes: use only for short urgent windows.

Prefer a bounded window, for example "every 30 minutes for the next 4 hours". Stop or pause the heartbeat after returning to the computer.

For this skill's main purpose, heartbeat is usually preferable to event mode because it keeps the current Codex App thread in control. Use event mode only when saving idle token use matters more than preserving thread memory.

## Temporary Fallback: HTTPS Tunnel

Use Cloudflare Tunnel, ngrok, or another trusted tunnel only when a private VPN is not available. Cloudflare's current docs describe Cloudflare Tunnel as outbound-only: `cloudflared` connects from the desktop to Cloudflare, so no router port forwarding is needed.

For a public tunnel, bind the bridge to localhost:

```powershell
python .\scripts\start_mobile_bridge.py --host 127.0.0.1 --port 8765 --reset-token
```

Then point the tunnel at:

```text
http://127.0.0.1:8765
```

Use the tunnel's HTTPS URL plus the token query parameter printed by the bridge. Rotate the token and stop the tunnel after use.

## Do Not Use Router Port Forwarding

Do not forward port `8765` from the router to the desktop. The bridge is designed for private VPN or authenticated tunnel access, not raw public internet exposure.
