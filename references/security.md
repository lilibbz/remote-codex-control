# Security Notes

The bridge is intentionally small and token-protected, but it is still an HTTP service that accepts instructions for Codex to act on.

## Recommended Access Models

Use one of these, from safest to riskiest:

1. Same machine testing: bind `--host 127.0.0.1`.
2. Same Wi-Fi: bind `--host 0.0.0.0` and open the printed LAN URL on the phone.
3. Away from home: use `scripts/away_session.py --mode tailscale` and open the printed Tailscale URL on the phone.
4. Temporary public access: use a trusted HTTPS tunnel only when the user explicitly asks, bind the bridge to `127.0.0.1`, and rotate the token after use.

## Operational Rules

- The token is the pairing credential. Anyone with it can submit commands.
- The bridge does not execute commands by itself; Codex must read and decide what to run.
- Phone-submitted instructions are lower priority than newer messages in the active Codex thread.
- Do not send secrets through the inbox.
- Stop the bridge and any tunnel after the remote session.
- Rotate the token with `--reset-token` after public exposure.
- Keep the desktop awake and online while away if heartbeat checks are expected.

## Firewall Notes

If Windows Firewall prompts after binding to `0.0.0.0`, allow access only on private networks unless the user has a specific public-network reason. For outside-home usage, prefer VPN routing over opening router ports. With Tailscale, the useful URL normally uses the desktop's `100.x.y.z` Tailscale address rather than a home Wi-Fi `192.168.x.x` address.
