#!/usr/bin/env python3
"""Start a small token-protected mobile command inbox for Codex."""

from __future__ import annotations

import argparse
import html
import http.server
import json
import secrets
import socket
import socketserver
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse


APP_DIR = Path.home() / ".codex" / "remote-codex-control"
CONFIG_FILE = "config.json"
INBOX_FILE = "inbox.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_config(state_dir: Path) -> dict[str, Any]:
    path = state_dir / CONFIG_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(state_dir: Path, config: dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / CONFIG_FILE).write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_lan_ips() -> list[str]:
    ips: set[str] = set()
    hostname = socket.gethostname()
    try:
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except socket.gaierror:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


def make_url(host: str, port: int, token: str) -> str:
    display_host = "127.0.0.1" if host in {"0.0.0.0", ""} else host
    return f"http://{display_host}:{port}/?{urlencode({'token': token})}"


def read_records(inbox_path: Path) -> list[dict[str, Any]]:
    if not inbox_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in inbox_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def build_commands(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    commands: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        record_type = record.get("type")
        command_id = str(record.get("id", ""))
        if not command_id:
            continue
        if record_type == "command":
            item = {
                "id": command_id,
                "created_at": record.get("created_at", ""),
                "title": record.get("title", ""),
                "body": record.get("body", ""),
                "status": "pending",
                "status_note": "",
                "status_at": "",
            }
            commands[command_id] = item
            order.append(command_id)
        elif record_type == "status" and command_id in commands:
            commands[command_id]["status"] = str(record.get("status", "pending"))
            commands[command_id]["status_note"] = str(record.get("note", ""))
            commands[command_id]["status_at"] = str(record.get("created_at", ""))
    return [commands[command_id] for command_id in order if command_id in commands]


def render_page(token_hint: str = "") -> bytes:
    safe_hint = html.escape(token_hint, quote=True)
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Remote Codex Control</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, -apple-system, Segoe UI, sans-serif; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: start center; background: #f5f7fb; color: #172033; }}
    main {{ width: min(720px, calc(100vw - 32px)); }}
    main {{ margin: 24px 0; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    h2 {{ margin: 28px 0 12px; font-size: 18px; }}
    p {{ margin: 0 0 18px; line-height: 1.45; color: #526071; }}
    label {{ display: block; margin: 16px 0 6px; font-weight: 650; }}
    input, textarea {{ width: 100%; box-sizing: border-box; border: 1px solid #c8d0dc; border-radius: 8px; padding: 12px; font: inherit; background: white; color: #172033; }}
    textarea {{ min-height: 180px; resize: vertical; }}
    button {{ margin-top: 16px; border: 0; border-radius: 8px; padding: 12px 16px; font: inherit; font-weight: 700; background: #1167d8; color: white; width: 100%; }}
    .status {{ min-height: 24px; margin-top: 14px; font-weight: 650; }}
    .panel {{ background: white; border: 1px solid #dce2ec; border-radius: 8px; padding: 24px; box-shadow: 0 14px 36px rgba(27, 38, 64, .08); }}
    .muted {{ font-size: 13px; color: #657386; }}
    .command-list {{ display: grid; gap: 10px; margin-top: 12px; }}
    .command {{ border: 1px solid #dce2ec; border-radius: 8px; padding: 12px; background: #f9fbff; }}
    .command-head {{ display: flex; gap: 8px; justify-content: space-between; align-items: start; margin-bottom: 8px; }}
    .command-title {{ font-weight: 750; overflow-wrap: anywhere; }}
    .badge {{ border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 750; background: #e8edf7; color: #314055; white-space: nowrap; }}
    .badge.done {{ background: #dff5e9; color: #126238; }}
    .badge.skipped {{ background: #fff1d7; color: #805100; }}
    .badge.seen {{ background: #e8f0ff; color: #174ea6; }}
    .command-body, .command-note {{ white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.4; }}
    .command-note {{ margin-top: 8px; padding-top: 8px; border-top: 1px solid #dce2ec; color: #172033; }}
    .empty {{ padding: 12px; border: 1px dashed #c8d0dc; border-radius: 8px; color: #657386; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #111827; color: #eef2ff; }}
      .panel {{ background: #172033; border-color: #2b3648; }}
      p, .muted {{ color: #aab6c8; }}
      input, textarea {{ background: #0f1624; color: #eef2ff; border-color: #3a475d; }}
      .command {{ background: #111827; border-color: #2b3648; }}
      .command-note {{ border-top-color: #2b3648; color: #eef2ff; }}
      .empty {{ border-color: #3a475d; color: #aab6c8; }}
    }}
  </style>
</head>
<body>
  <main class="panel">
    <h1>Remote Codex Control</h1>
    <p>Send instructions from your phone to the desktop Codex inbox. Codex reads this inbox during manual checks or heartbeat runs.</p>
    <form id="form">
      <label for="token">Pairing token</label>
      <input id="token" name="token" autocomplete="off" value="{safe_hint}" placeholder="Paste the desktop token">
      <label for="title">Title</label>
      <input id="title" name="title" maxlength="120" placeholder="Optional short title">
      <label for="body">Command</label>
      <textarea id="body" name="body" required placeholder="Tell Codex what to do..."></textarea>
      <button type="submit">Send to desktop Codex</button>
    </form>
    <div id="status" class="status"></div>
    <p class="muted">Keep the token private. Do not send passwords or API keys through this page.</p>
    <h2>Recent commands</h2>
    <div id="commands" class="command-list">
      <div class="empty">Loading...</div>
    </div>
  </main>
  <script>
    const params = new URLSearchParams(location.search);
    const tokenInput = document.querySelector("#token");
    const stored = localStorage.getItem("remote-codex-token");
    if (params.get("token")) {{
      tokenInput.value = params.get("token");
      localStorage.setItem("remote-codex-token", tokenInput.value);
    }} else if (stored) {{
      tokenInput.value = stored;
    }}
    function commandTitle(item) {{
      return item.title || item.id || "(no title)";
    }}

    function renderCommands(items) {{
      const container = document.querySelector("#commands");
      container.textContent = "";
      if (!items.length) {{
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "No commands yet.";
        container.appendChild(empty);
        return;
      }}
      for (const item of items) {{
        const card = document.createElement("div");
        card.className = "command";
        const head = document.createElement("div");
        head.className = "command-head";
        const title = document.createElement("div");
        title.className = "command-title";
        title.textContent = commandTitle(item);
        const badge = document.createElement("div");
        badge.className = `badge ${{item.status || "pending"}}`;
        badge.textContent = item.status || "pending";
        head.append(title, badge);
        const body = document.createElement("div");
        body.className = "command-body";
        body.textContent = item.body || "";
        card.append(head, body);
        if (item.status_note) {{
          const note = document.createElement("div");
          note.className = "command-note";
          note.textContent = item.status_note;
          card.appendChild(note);
        }}
        container.appendChild(card);
      }}
    }}

    async function refreshCommands() {{
      const token = tokenInput.value.trim();
      if (!token) return;
      const response = await fetch(`/api/commands?token=${{encodeURIComponent(token)}}`);
      const data = await response.json().catch(() => ({{ ok: false, commands: [] }}));
      if (response.ok && data.ok) {{
        renderCommands(data.commands || []);
      }}
    }}

    document.querySelector("#form").addEventListener("submit", async (event) => {{
      event.preventDefault();
      const status = document.querySelector("#status");
      status.textContent = "Sending...";
      const payload = {{
        token: tokenInput.value.trim(),
        title: document.querySelector("#title").value.trim(),
        body: document.querySelector("#body").value.trim()
      }};
      localStorage.setItem("remote-codex-token", payload.token);
      const response = await fetch("/api/command", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload)
      }});
      const data = await response.json().catch(() => ({{ ok: false, error: "Invalid response" }}));
      if (response.ok && data.ok) {{
        status.textContent = `Sent: ${{data.id}}`;
        document.querySelector("#title").value = "";
        document.querySelector("#body").value = "";
        await refreshCommands();
      }} else {{
        status.textContent = data.error || "Send failed";
      }}
    }});
    refreshCommands();
    setInterval(refreshCommands, 5000);
  </script>
</body>
</html>"""
    return page.encode("utf-8")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def make_handler(state_dir: Path, token: str):
    inbox_path = state_dir / INBOX_FILE

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "RemoteCodexControl/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

        def send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/api/commands":
                submitted_token = query.get("token", [""])[0]
                if not secrets.compare_digest(submitted_token, token):
                    self.send_json(403, {"ok": False, "error": "Invalid token"})
                    return
                commands = build_commands(read_records(inbox_path))[-20:]
                commands.reverse()
                self.send_json(200, {"ok": True, "commands": commands})
                return
            if parsed.path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            token_hint = query.get("token", [""])[0]
            body = render_page(token_hint)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/command":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length > 128_000:
                self.send_json(413, {"ok": False, "error": "Command is too large"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json(400, {"ok": False, "error": "Invalid JSON"})
                return
            if not secrets.compare_digest(str(payload.get("token", "")), token):
                self.send_json(403, {"ok": False, "error": "Invalid token"})
                return
            body = str(payload.get("body", "")).strip()
            title = str(payload.get("title", "")).strip()
            if not body:
                self.send_json(400, {"ok": False, "error": "Command is empty"})
                return
            command_id = secrets.token_hex(4)
            record = {
                "type": "command",
                "id": command_id,
                "created_at": utc_now(),
                "title": title[:120],
                "body": body,
                "source": self.client_address[0],
                "user_agent": self.headers.get("User-Agent", ""),
            }
            state_dir.mkdir(parents=True, exist_ok=True)
            with inbox_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.send_json(200, {"ok": True, "id": command_id})

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the Remote Codex Control mobile bridge.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Use 0.0.0.0 for LAN/VPN phone access.")
    parser.add_argument("--port", default=8765, type=int, help="Bind port.")
    parser.add_argument("--state-dir", default=str(APP_DIR), help="Directory for config and inbox.")
    parser.add_argument("--token", help="Use a specific pairing token.")
    parser.add_argument("--reset-token", action="store_true", help="Generate and save a new token.")
    args = parser.parse_args()

    state_dir = Path(args.state_dir).expanduser()
    config = load_config(state_dir)
    token = args.token or config.get("token")
    if args.reset_token or not token:
        token = secrets.token_urlsafe(24)
    config.update({"token": token, "updated_at": utc_now(), "port": args.port})
    save_config(state_dir, config)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / INBOX_FILE).touch(exist_ok=True)

    handler = make_handler(state_dir, token)
    try:
        server = ThreadedHTTPServer((args.host, args.port), handler)
    except OSError as exc:
        print(f"Could not bind {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 2

    print("Remote Codex Control bridge is running.")
    print(f"Inbox: {state_dir / INBOX_FILE}")
    print(f"Desktop URL: {make_url(args.host, args.port, token)}")
    if args.host in {"0.0.0.0", ""}:
        for ip in get_lan_ips():
            print(f"Phone LAN URL: http://{ip}:{args.port}/?{urlencode({'token': token})}")
    print("Keep this terminal open. Press Ctrl+C to stop.")
    print("For outside-home access, use a VPN or trusted HTTPS tunnel; do not expose this port directly.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
