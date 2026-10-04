# Logitech Litra Glow — Home Assistant Integration
*Last updated: October 2026*

## Overview

A Logitech Litra Glow key light, USB-attached to the Mac Mini, appears in Home Assistant as a native light with on/off, brightness, and color temperature. A small Rust service, `litra-agent`, runs as a LaunchAgent in the console user's session on the Mac. It talks to the light over USB HID and serves an authenticated HTTPS + WebSocket API. A custom integration, `litra`, discovers the agent over zeroconf, pins its certificate at pairing, and receives state changes over a push stream. Both components live in the private repo [`NateUT99/ha-litra`](https://github.com/NateUT99/ha-litra), which is the source of truth for their code. This guide covers the deployment in this house.

---

## Architecture

```
Home Assistant (litra integration)
  ├── HTTPS POST /api/v1/devices/{id}  ── commands (one request per light.turn_on/off)
  └── WebSocket /api/v1/events          ── full device state, pushed on every change
        │   TLS, certificate fingerprint pinned at pairing; bearer token on every request
        ▼
<mac-mini-hostname>:47810
  └── litra-agent (LaunchAgent, console user's session)
        └── HID worker thread (polls ~1 s; only code that touches USB)
              └── Logitech Litra Glow (USB HID)
```

Key design decisions:

- **The agent runs in the console user's session.** macOS grants USB HID access to the logged-in user's session. A LaunchAgent gets that access natively, so there is no sudo rule, service account, or SSH in this path.
- **State is pushed, not polled by HA.** The agent reads the light locally about once a second and broadcasts only changes. Physical button presses and USB unplug/replug reach HA within a second, and a restart needs no refresh automation, because the stream sends full state on connect.
- **One request per command.** The integration is a real `LightEntity`, so `light.turn_on` with brightness and color temperature becomes a single request carrying both. The agent always applies on → brightness → temperature → off, because a Litra that is off stores brightness and temperature without lighting up.
- **HID responses are matched to their requests.** On macOS every open handle receives every HID response, so the agent accepts only a response that echoes its own request's header. Any other program polling the light (including the `litra` CLI) cannot corrupt the reading. See `LESSONS.md` → *macOS delivers every HID input report to every open handle*.
- **A separate connectivity sensor on the agent device.** The light going `unavailable` can mean the agent is unreachable or the Litra is unplugged. `binary_sensor.office_litra_agent_connectivity` tells the two apart. It belongs to the agent device because one agent serves every Litra on that Mac.

---

## Prerequisites

- Logitech Litra Glow connected via USB to the Mac Mini
- Rust toolchain on the Mac (`brew install rust`)
- A clone of `NateUT99/ha-litra` on the Mac
- SSH access to the HA host (`ssh ha`) for deploying the integration

---

## Step 1: Install the Agent on the Mac Mini

Run as the console user, not root. HID access comes from that user's session:

```bash
cd ha-litra/agent
./install.sh
```

`install.sh` builds the release binary, installs it to `~/.local/bin/litra-agent`, writes `~/Library/LaunchAgents/com.github.nateut99.litra-agent.plist` (`RunAtLoad`, `KeepAlive`), and bootstraps it into the user's GUI domain. The agent listens on `0.0.0.0:47810` and advertises `_litra-agent._tcp` over mDNS.

The Mac's application firewall is on, so `install.sh` also adds an allow rule with `sudo`. The firewall keys that rule on the binary's code signature, and each rebuild produces a new ad-hoc signature. After any rebuild, re-run `install.sh` rather than only `cargo build`.

On first run the agent creates `~/Library/Application Support/litra-agent/` (`0700`), containing a self-signed TLS certificate and key, a stable agent ID, and, after pairing, the token hash. All files are `0600`.

Verify:

```bash
launchctl print gui/$(id -u)/com.github.nateut99.litra-agent | grep "state ="
tail ~/Library/Logs/litra-agent.log
```

---

## Step 2: Pair

```bash
~/.local/bin/litra-agent pair
```

This prints a new 256-bit token and the certificate's SHA-256 fingerprint. The agent stores only the token's hash, and running `pair` again immediately invalidates the previous token. Enter the token directly into HA (Step 3). Don't paste it into chat, notes, or tickets.

---

## Step 3: Install the Integration in Home Assistant

The repo is private, so HACS can't install it. Copy the integration onto the HA host and restart HA:

```bash
cd ha-litra
scp -r custom_components/litra ha:/config/custom_components/
```

Python code changes take effect only after a full HA restart, not an integration reload.

After the restart, **Settings → Devices & services** lists *Litra Agent on nates-mac-mini* under Discovered. If it doesn't appear, add **Logitech Litra** manually with `<mac-mini-hostname>` and port `47810`. Confirm that the fingerprint HA shows matches the `pair` output exactly, then enter the token.

> **Coordinated change:** HA pins the certificate fingerprint. If the agent's certificate is regenerated (by deleting `cert.pem`/`key.pem`), HA starts a re-pair flow showing the new fingerprint. Confirm it against `litra-agent fingerprint` before accepting. A fingerprint change you didn't cause means something else is answering at the agent's address.

---

## Step 4: Entities

The integration creates two devices: **Litra Agent** (the service) and the light, linked to the agent via `via_device`. After pairing, apply these registry settings:

| Device | Device name | Entity ID | Registry settings |
| --- | --- | --- | --- |
| Litra Glow | `Desk Key Light` | `light.office_desk_key_light` | Labels `sleeping`, `no_one_home`; exposed to Assist |
| Litra Agent | `Litra Agent` | `binary_sensor.office_litra_agent_connectivity` | Diagnostic connectivity sensor |

The `sleeping` and `no_one_home` labels put the key light in the household's label-targeted "lights off" sweeps.

---

## Step 5: Camera Automation

Automatically controls office lighting when the active camera on the MacBook Pro (`sensor.nates_work_laptop_active_camera`) becomes the Studio Display Camera. It's scoped to the MacBook Pro only, because that's the only Mac used for video calls; the Mac Mini is never a source, so it isn't watched.

When that camera turns on, the ceiling light and monitor light bar turn off and the key light turns on at a video-call preset (45% brightness, 4500 K). When the camera turns off, nothing happens immediately if the microphone is still captured. A video-only pause (stepping away briefly while still connected to the call) holds the room lighting as-is rather than flickering it off and back on.

Once the microphone also releases, or after a 3-minute safety cap, the key light turns off. If the MacBook Pro is currently active, the monitor light bar is then restored, and the ceiling light too if it was on before the call. If the MacBook Pro isn't active, nothing comes back on after you've walked away mid-call.

The trigger fires on the camera-name sensor, which reports the active camera's display name as a string. This matches only Studio Display Camera sessions and ignores the laptop's built-in FaceTime camera, since the goal is lighting for the desk-mounted Studio Display setup.

The restore guard is "MacBook Pro currently active", deliberately not gated on which display is attached. macOS primary-display sensors misreport over Screen Sharing, so a display-identity check would make the restore depend on how the Mac was accessed. See `LESSONS.md` → *Shell Command Integration*.

The ceiling light (`light.office_ceiling_fan_light`) is under Adaptive Lighting (`guides/adaptive_lighting.md`). The automation turns it off and restores it with a bare `light.turn_off`/`light.turn_on`, with no brightness or temperature data. That lets AL's `intercept` adapt the restore to the current curve target. `automation.office_ceiling_fan_wall_control`'s "Ceiling light changed" branch handles AL manual control and the switch LED bar on each transition.

Call start and call end are separate trigger firings, so the ceiling light's prior state is carried between them in `input_boolean.office_ceiling_light_was_on`. It's set at the top of the call-start branch, before the light is touched, and read by the call-end branch's restore step. The monitor light bar is always restored, since it's never in any state other than on or off-for-a-call.

#### Why the microphone, not a longer debounce

The camera-off trigger's own `for:` debounce is short (3 s, enough to absorb sensor jitter). Tolerance for brief away-periods comes instead from a `wait_for_trigger` in the "Camera turned off" branch. A fixed debounce forces a choice between "long enough to cover a water-bottle refill" and "restores lights promptly after a real call ends", and no single number satisfies both.

The microphone answers the actual question, whether the call is still connected. Conferencing apps hold the OS-level mic open for the whole call, even through muted or video-paused stretches, and release it only when you leave. Gating on `binary_sensor.nates_work_laptop_audio_input_in_use` lets an arbitrarily long pause pass with no light changes, while a real call end restores within the 3 s debounce. Live traces confirm the mic stays `on` through mid-call camera drops. The 3-minute timeout is a backstop for an app that releases the mic differently, such as a fully muted call that never registers as in use.

### Automation

Two triggers, `on` and `off` (with the 3 s debounce above), route through a `choose` with `mode: restart`, so a fresh trigger cancels any in-progress run.

On `on`, the first step records whether the ceiling light is on into `input_boolean.office_ceiling_light_was_on`. A nested `choose` then checks the light's availability before applying the preset, since the preset would silently no-op otherwise:

| Branch | Condition | Action |
| --- | --- | --- |
| Agent offline | `binary_sensor.office_litra_agent_connectivity` is `off`/`unavailable`/`unknown` | Push: "Litra agent on the Mac Mini is offline." |
| Light unplugged | `light.office_desk_key_light` is `unavailable`/`unknown` | Push: "Litra Glow not detected - check its USB cable." |
| Default | — | Turn off ceiling light and monitor light bar; `light.turn_on` the key light with `brightness_pct: 45`, `color_temp_kelvin: 4500` |

On `off`, if `binary_sensor.nates_work_laptop_audio_input_in_use` is still `on`, a `wait_for_trigger` blocks until it goes `off` or 3 minutes elapse (`continue_on_timeout: true`). The run then turns off the key light. If the MacBook Pro is currently active, it restores the monitor light bar, and restores the ceiling light with a bare `light.turn_on` when `input_boolean.office_ceiling_light_was_on` is `on`. No lights change before the wait resolves, so `mode: restart` makes a camera coming back on mid-wait a true no-op.

Full YAML: `ha/automations/automation.office_camera_lighting.yaml` (HA is authoritative — see `standards/documentation.md`).

---

## Step 6: Agent Offline Alert

Office: Litra Agent Offline Alert (`automation.office_litra_agent_offline_alert`) sends a push to both Macs (`notify.nates_mac_mini`, `notify.nates_work_laptop`) when `binary_sensor.office_litra_agent_connectivity` has been `off` for two minutes. The two-minute hold rides out an agent restart or reinstall. The trigger requires `from: "on"`, so an agent that is already down when HA starts (sensor `unavailable`) doesn't fire it.

Full YAML: `ha/automations/automation.office_litra_agent_offline_alert.yaml`.

---

## Scale Conversions Reference

All conversion happens in the integration's light entity. The agent API speaks the device's native units.

| Quantity | HA side | Agent / device side | Conversion |
| --- | --- | --- | --- |
| Brightness | 1–255 | 20–250 lumen (Glow) | `value_to_brightness` / `brightness_to_value` from `homeassistant.util.color` over the device's lumen range; HA → device rounds up |
| Color temperature | kelvin | 2700–6500 K | None. The agent rounds to the nearest 100 K (a device requirement) and clamps to range |

The ranges come from the device at runtime (`min/max_brightness_lumen`, `min/max_temperature_kelvin` in the API), so a Beam or Beam LX on the same agent gets its own correct ranges without configuration.

---

## Security Summary

| Layer | Detail |
| --- | --- |
| Privilege | Agent runs as the console user in that user's session; no sudo rule, service account, or SSH for this integration |
| Transport | TLS with a self-signed certificate generated on first run; HA pins its SHA-256 fingerprint at pairing (trust on first use, confirmed by the user against `litra-agent pair`) |
| Authentication | 256-bit random bearer token on every request, including the WebSocket upgrade; the agent stores only its SHA-256 hash and compares in constant time |
| Command surface | Four endpoints (`info`, `devices`, `devices/{id}`, `events`). Typed JSON with unknown fields rejected, 1 KB body limit, values clamped to the device's range. Nothing reaches a shell |
| On-disk secrets | `~/Library/Application Support/litra-agent/` is `0700`; certificate key, token hash, and agent ID are `0600` |
| Network exposure | Listens on `0.0.0.0:47810`; reachable through the macOS application firewall by an explicit allow rule for the binary |
| Rotation | `litra-agent pair` issues a new token and revokes the old one at once; HA then starts its re-pair flow |
| Worst case if the token leaks | Someone on the LAN can turn the key light on or off and change its brightness and temperature. No shell, file access, or other device control. The token is useless against an agent whose certificate HA doesn't pin |

---

## Related HA Config

| Artifact | Entity ID | Type |
| --- | --- | --- |
| Desk Key Light | `light.office_desk_key_light` | Light (`litra` custom integration) |
| Litra Agent Connectivity | `binary_sensor.office_litra_agent_connectivity` | Connectivity binary sensor (`litra` custom integration) |
| Office Ceiling Light | `light.office_ceiling_fan_light` | Matter light (`guides/inovelli_switches.md`, `guides/adaptive_lighting.md`) — switched off/on by the camera automation, not owned by it |
| Office Ceiling Light Was On | `input_boolean.office_ceiling_light_was_on` | Helper — internal automation state, hidden from dashboards/voice; owned by the camera automation |
| Office: Camera Lighting | `automation.office_camera_lighting` | Automation |
| Office: Litra Agent Offline Alert | `automation.office_litra_agent_offline_alert` | Automation |

---

## Related Files

| File | Location | Purpose |
| --- | --- | --- |
| Agent source | `NateUT99/ha-litra` → `agent/`; binary at `~/.local/bin/litra-agent` on the Mac Mini | HID worker and HTTPS/WebSocket API |
| LaunchAgent | `~/Library/LaunchAgents/com.github.nateut99.litra-agent.plist` on the Mac Mini | Keeps the agent running in the console user's session |
| Agent state | `~/Library/Application Support/litra-agent/` on the Mac Mini | Certificate, key, agent ID, token hash |
| Agent log | `~/Library/Logs/litra-agent.log` on the Mac Mini | launchd-captured stderr |
| Integration source | `NateUT99/ha-litra` → `custom_components/litra/`; deployed to `/config/custom_components/litra/` on HA | HA integration |
| Camera lighting automation | `ha/automations/automation.office_camera_lighting.yaml` | Mirror — HA authoritative |
| Agent offline alert automation | `ha/automations/automation.office_litra_agent_offline_alert.yaml` | Mirror — HA authoritative |

---

## Related Documents

- `NateUT99/ha-litra` `README.md` — agent API reference and development setup
- `guides/adaptive_lighting.md` — the ceiling light the camera automation switches
- `guides/mac_mini_remote_control.md` — the other HA → Mac Mini integration (SSH-based; independent of this one)

---

## Troubleshooting

- **Light and connectivity sensor both unavailable after an agent upgrade.** The firewall allow rule is tied to the old binary's signature. Re-run `install.sh`, which re-applies it.
- **Re-pair flow appears unexpectedly.** Either the token was rotated (`pair` was run) or the certificate changed. The flow labels the fingerprint *CHANGED* or *unchanged*. Treat an unexplained change as an address conflict or interception until proven otherwise.
- **`litra devices --json` shows an impossible value (e.g. `256 K`).** The `litra` CLI doesn't match responses to requests, so it can read the agent's traffic. The agent itself is unaffected; re-run the CLI.
