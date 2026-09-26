# Chime TTS Integration

*Last updated: September 2026*

## Overview

Chime TTS is a HACS integration that wraps Home Assistant's cloud TTS service with a configurable chime sound prefix. Announcements open with a brief soft chime before the spoken message, making them instantly recognizable as home automation alerts rather than unexpected audio playback. This instance runs `nimroddolev/chime_tts` v1.3.0, installed from HACS's default store (no custom repository registration needed).

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

Volume levels differ per room — 0.65 kitchen (ambient noise), 0.5 master bedroom / office, 0.4 Avery's room (nighttime/quiet context). Kitchen and master bedroom are tuned values (the `snapshot/2026-07-27-pre-move/` baseline); office and Avery's room are starting guesses and may need adjustment after first use. Master bedroom drops further, to 0.4, while `everyone_sleeping` is on — gated on that state directly rather than on the caller, so it applies whether the room was reached via `target: auto` or an explicit `target: master_bedroom` call.

> **Family room Sonos is not a script target.** `chime_tts.say` against the family room Sonos (`media_player.family_room_theater`) produces no audio and no error at any log level — see `LESSONS.md` → TTS & Media. `guides/laundry_automation.md` handles family-room awareness with a plain push notification when the Sonos is busy, entirely outside this script.

> **Coordinated change:** Room volumes live inside `script.household_tts_announce`'s `choose` branches (a `volume_level` per target — a literal for every room except master bedroom, which templates on `everyone_sleeping`), not in a shared table. Adjusting a room's volume means editing that branch directly — see `guides/reminders.md` and any other guide referencing this script for the current field contract.

---

## Design Decisions

- **`chime_tts.say` directly, not a `notify:` platform.** The integration's `notify.py` is a thin wrapper that calls the same `chime_tts.say` service internally. Calling `say` directly means no `configuration.yaml` entry, no full-restart to change a volume, and the whole delivery mechanism in one MCP-retrievable script that mirrors into `ha/scripts/`. The chime prefix — the reason to use Chime TTS over bare `media_player.play_media` / `tts.speak` at all — is unaffected by which service dispatches it.
- **Config entry over YAML.** The custom integration is enabled via a config entry (**Settings → Devices & Services → Add Integration → Chime TTS**), not a `configuration.yaml` block. HA discovers the custom component automatically once its files exist in `custom_components/`; the config entry is what triggers service registration. No restart is required — confirmed live.

---

## Prerequisites

- HACS installed and active — `chime_tts` is a HACS default-store integration, no custom repository needed
- Nabu Casa subscription active (cloud TTS)
- `media_player.kitchen_homepod`, `media_player.master_bedroom_homepod`, `media_player.office_homepod`, `media_player.averys_room_homepod` — HomePods via the Apple TV integration

---

## Steps

### 1. Install Chime TTS via HACS

Search **Chime TTS** in **HACS → Integrations** and download it — it's a default-store listing, no custom repository registration needed. Restart Home Assistant to load the integration.

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
| `target` | No | `auto` | `kitchen`, `master_bedroom`, `office`, `averys_room`, `broadcast`, or `auto` — `auto` picks master bedroom when `everyone_sleeping` is on, kitchen otherwise; `broadcast` fans out to kitchen, master bedroom, office, and Avery's room (see below) |
| `notification_title` | No | `Missed Announcement` | Title for the push notification sent when a room falls back to a push |
| `critical_fallback` | No | `false` | When a fallback push fires, add the iOS `push.sound.critical` / `interruption-level: critical` payload so it breaks through silent mode and Focus |

**`target: broadcast`.** Fans out to kitchen and master bedroom always, office unless it's busy with a call, and Avery's room unless `input_boolean.avery_sleeping` is on (so she isn't woken). `automation.household_hvac_exterior_open_pause`'s door-warning, pause, and resume announcements are the first consumer.

**One `chime_tts.say` action targeting a list of entity_ids, not a loop.** Every room resolved for a given call is spoken to with a single action carrying `target.entity_id` as a list — this is a real single dispatch, not one `chime_tts.say` per room. A `repeat` loop was tried first and rejected: `repeat` executes its iterations sequentially, so a 4-room broadcast would speak kitchen, then master bedroom, then office, then Avery's room one after another rather than together — audibly staggered, not a broadcast. Live-verified 2026-09-24: all four HomePods began `playing` within under a second of each other on a single multi-target call. The tradeoff is volume — one service call carries one `volume_level` for every target, so a single-room call keeps that room's own tuned volume (kitchen 0.6, office 0.5, Avery's room 0.4, master bedroom 0.4/0.5 by sleep state) while a multi-room call uses one shared volume (0.5).

**"Office busy" is a per-room condition, not a global one.** A call only makes the *Office* speaker unsuitable — kitchen, master bedroom, and Avery's room are physically far enough away that TTS there won't bleed into the call's microphone. `office_busy` is `true` when `binary_sensor.nates_work_laptop_audio_input_in_use` is `on` — the same MacBook Pro signal `automation.office_camera_lighting` relies on to detect an active call, deliberately audio-input rather than camera so an audio-only call (mic in use, no camera) still excludes the office.

**Fallback guard.** Any room that's unreachable — office busy with a call, or that room's HomePod offline — is pulled out of the room list before the `chime_tts.say` call and covered by a single push to `notify.mobile_app_nates_iphone` instead (one push regardless of how many rooms were unreachable, since the message/title is identical either way). The remaining reachable rooms still get TTS in their own single action. `chime_tts.say` against a dead speaker fails silently at every log level, so detecting "offline" ahead of the call — rather than after — is what keeps the announcement from vanishing with no trace.

`critical_fallback: true` upgrades that push to a critical alert; callers that just want the message delivered leave it unset.

Do not call `chime_tts.say` directly from automations — use the script so the fallback guards, per-room volume, and broadcast logic stay in one place. The four individual targets (kitchen, master bedroom, office, Avery's room) are confirmed working end-to-end; `broadcast` is new and config-verified but not yet exercised by a live trigger.

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
