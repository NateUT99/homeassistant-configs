# Chime TTS Integration

*Last updated: September 2026*

## Overview

Chime TTS is a HACS integration that wraps Home Assistant's cloud TTS service with a configurable chime sound prefix. Announcements open with a brief soft chime before the spoken message, making them instantly recognizable as home automation alerts rather than unexpected audio playback. This instance runs `derekcentrico/chime_tts`, a maintained fork of the (no-longer-updated) original — installed via HACS as a custom repository.

`script.household_tts_announce` calls `chime_tts.say` directly, targeting the resolved speaker per call. There is no `notify:` platform configuration — see the design decision below for why. When TTS can't land — an active video call, or the resolved HomePod being `unavailable` — the script falls back to a push notification to Nate's iPhone, optionally as an iOS critical alert.

---

## Architecture

```
automations
          │
          ▼
script.household_tts_announce
  │  fallback guards, checked in order:
  ├─ active video call (Mac Mini / work laptop camera sensor)  ─┐
  ├─ resolved HomePod is unavailable / unknown                  ─┼─► notify.mobile_app_nates_iphone
  │                                    (critical payload when critical_fallback: true)
  └─ routing (target: kitchen / master_bedroom / office / averys_room / auto)
          │
          ▼
chime_tts.say
  ├── chime prefix  (chime_path: soft)
  └── spoken message  (tts_platform: cloud, Nabu Casa)
          │
          ▼
HA announce pipeline
          │
          ▼
media_player.kitchen_homepod / master_bedroom_homepod /
office_homepod / averys_room_homepod
```

The `announce: true` flag routes playback through HA's announce pipeline, which interrupts current audio and restores it after the announcement. `cache: true` caches the TTS audio on disk so repeated identical messages skip the Nabu Casa API call.

Volume levels differ per room — 0.65 kitchen (ambient noise), 0.5 master bedroom / office, 0.4 Avery's room (nighttime/quiet context). Kitchen and master bedroom are tuned values (the `snapshot/2026-07-27-pre-move/` baseline); office and Avery's room are starting guesses and may need adjustment after first use.

> **Family room Sonos is not a script target.** `chime_tts.say` against the family room Sonos (`media_player.family_room_theater`) produces no audio and no error at any log level — see `LESSONS.md` → TTS & Media. `guides/laundry_automation.md` handles family-room awareness with a plain push notification when the Sonos is busy, entirely outside this script.

> **Coordinated change:** Room volumes live inside `script.household_tts_announce`'s `choose` branches (one literal `volume_level` per target), not in a shared table. Adjusting a room's volume means editing that branch directly — see `guides/reminders.md` and any other guide referencing this script for the current field contract.

---

## Design Decisions

- **`chime_tts.say` directly, not a `notify:` platform.** The fork's `notify.py` is a thin wrapper that calls the same `chime_tts.say` service internally. Calling `say` directly means no `configuration.yaml` entry, no full-restart to change a volume, and the whole delivery mechanism in one MCP-retrievable script that mirrors into `ha/scripts/`. The chime prefix — the reason to use Chime TTS over bare `media_player.play_media` / `tts.speak` at all — is unaffected by which service dispatches it.
- **Config entry over YAML.** The custom integration is enabled via a config entry (**Settings → Devices & Services → Add Integration → Chime TTS**), not a `configuration.yaml` block. HA discovers the custom component automatically once its files exist in `custom_components/`; the config entry is what triggers service registration. No restart is required — confirmed live.

---

## Prerequisites

- HACS installed and active, with `derekcentrico/chime_tts` added as a custom repository
- Nabu Casa subscription active (cloud TTS)
- `media_player.kitchen_homepod`, `media_player.master_bedroom_homepod`, `media_player.office_homepod`, `media_player.averys_room_homepod` — HomePods via the Apple TV integration

---

## Steps

### 1. Install Chime TTS via HACS

Add `derekcentrico/chime_tts` as a custom repository (category: Integration) in **HACS → Integrations**, then download it. No restart needed for the files to be discovered — HA logs a "custom integration not tested" warning on next load, which is expected for any HACS custom component.

### 2. Add the config entry

**Settings → Devices & Services → Add Integration → Chime TTS.** This has no configuration fields of its own — adding the entry is what registers `chime_tts.say`, `chime_tts.say_url`, `chime_tts.replay`, and `chime_tts.clear_cache` as callable services.

### 3. Verify

Call `chime_tts.say` from **Developer Tools → Actions**:

```yaml
action: chime_tts.say
target:
  entity_id: media_player.kitchen_homepod
data:
  message: "Test announcement."
  chime_path: soft
  tts_platform: cloud
  volume_level: 0.65
  announce: true
```

The kitchen HomePod should play the soft chime followed by the spoken message.

---

## TTS Announce Script

All TTS automations in this instance call `script.household_tts_announce` rather than `chime_tts.say` directly — it is the standard entry point.

```yaml
action: script.household_tts_announce
data:
  message: "Your message here."
  target: auto                    # optional: kitchen / master_bedroom / office / averys_room / auto
  notification_title: "My Alert"  # optional: push title used on either fallback
  critical_fallback: true         # optional: send the fallback push as an iOS critical alert
```

| Field | Required | Default | Description |
|---|---|---|---|
| `message` | Yes | — | Text to speak. Templates are supported. |
| `target` | No | `auto` | `kitchen`, `master_bedroom`, `office`, `averys_room`, or `auto` — picks master bedroom when `everyone_sleeping` is on, kitchen otherwise |
| `notification_title` | No | `Missed Announcement` | Title for the push notification sent on either fallback path |
| `critical_fallback` | No | `false` | When a fallback push fires, add the iOS `push.sound.critical` / `interruption-level: critical` payload so it breaks through silent mode and Focus |

**Fallback guards.** Two conditions send a push to `notify.mobile_app_nates_iphone` instead of speaking, checked in this order:

1. **Active video call** — `sensor.nates_mac_mini_active_camera` or `sensor.nates_work_laptop_active_camera` is not `Inactive`. Suppresses TTS so it can't interrupt a work call.
2. **Target HomePod offline** — the resolved room's `media_player` is `unavailable` or `unknown`. `chime_tts.say` against a dead speaker fails silently at every log level, so the announcement would vanish with no trace; the push is the only way it lands.

Both paths reuse `message` and `notification_title`. `critical_fallback: true` upgrades whichever push fires to a critical alert; callers that just want the message delivered leave it unset.

Do not call `chime_tts.say` directly from automations — use the script so the fallback guards and per-room volume stay in one place. All four targets (kitchen, master bedroom, office, Avery's room) are individually confirmed working end-to-end.

---

## Related HA Config

| Friendly Name | Entity / Service | Type |
|---|---|---|
| TTS Announce | `script.household_tts_announce` | Script — standard entry point for all TTS announcements |
| Chime TTS: Say | `chime_tts.say` | Service (Chime TTS config entry) |
| Kitchen HomePod | `media_player.kitchen_homepod` | Media player (Apple TV integration) |
| Master Bedroom HomePod | `media_player.master_bedroom_homepod` | Media player (Apple TV integration) |
| Office HomePod | `media_player.office_homepod` | Media player (Apple TV integration) |
| Avery's Room HomePod | `media_player.averys_room_homepod` | Media player (Apple TV integration) |

---

## Related Documents

- `standards/automations.md` — defines the `text_to_speech` label applied to automations that use `script.household_tts_announce`
- `guides/laundry_automation.md` — first consumer of the script (kitchen/master_bedroom targets); also owns the family-room-busy push notification, handled independently of this script
- `LESSONS.md` → TTS & Media — Sonos playback diagnostic trail (why family room isn't a script target); why `media_player.play_media`/`tts.speak` are avoided in favor of Chime TTS on HomePods
