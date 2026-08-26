# Chime TTS Integration

*Last updated: August 2026*

## Overview

Chime TTS is a HACS integration that wraps Home Assistant's cloud TTS service with a configurable chime sound prefix. Announcements open with a brief soft chime before the spoken message, making them instantly recognizable as home automation alerts rather than unexpected audio playback. This instance runs `derekcentrico/chime_tts`, a maintained fork of the (no-longer-updated) original — installed via HACS as a custom repository.

`script.household_tts_announce` calls `chime_tts.say` directly, targeting the resolved speaker per call. There is no `notify:` platform configuration — see the design decision below for why.

---

## Architecture

```
automations
          │
          ▼
script.household_tts_announce
  │  (checks camera sensors for active video call)
  ├─ on call → notify.mobile_app_nates_iphone  (push fallback)
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

Volume levels differ per room — 0.65 kitchen (ambient noise), 0.5 master bedroom / office, 0.4 Avery's room (nighttime/quiet context). Kitchen and master bedroom values come from the pre-move `configuration.yaml` baseline in `snapshot/2026-07-27-pre-move/`; office and Avery's room have no prior baseline and may need tuning after first use.

> **Family room Sonos is not a script target.** A Sonos-aware branch was tried and pulled — see `LESSONS.md` → TTS & Media for why. `guides/laundry_automation.md` instead pushes a plain notification when the family room Sonos is busy, handled entirely in that automation, not in this script.

> **Coordinated change:** Room volumes live inside `script.household_tts_announce`'s `choose` branches (one literal `volume_level` per target), not in a shared table. Adjusting a room's volume means editing that branch directly — see `guides/reminders.md` and any other guide referencing this script for the current field contract.

---

## Design Decisions

- **`chime_tts.say` directly, not a `notify:` platform.** The pre-move instance configured room-specific `notify.reminder_*` services via a `notify:` block in `configuration.yaml`. The fork's `notify.py` is a thin wrapper that calls the same `chime_tts.say` service internally — nothing is gained by the extra layer. Calling `say` directly means: no `configuration.yaml` entry, no full-restart-to-change-a-volume, and the whole delivery mechanism lives in an MCP-retrievable script that mirrors into `ha/scripts/`. The only historically documented rationale for Chime TTS at all was "use it instead of bare `media_player.play_media`/`tts.speak`, because of the chime prefix" — that reasoning is unaffected by which service dispatches it.
- **Config entry over YAML.** The custom integration is enabled via a config entry (**Settings → Devices & Services → Add Integration → Chime TTS**), not a `configuration.yaml` block. HA discovers the custom component automatically once its files exist in `custom_components/`; the config entry is what triggers service registration. No restart is required — confirmed live.
- **Family room Sonos is deliberately not a script target.** A `chime_tts.say` call against the family room Sonos (`media_player.family_room_theater`) was tested and produced no audio and no error at any log level, despite HA's control channel to the speaker working correctly — see `LESSONS.md` → TTS & Media for the full diagnostic trail. Rather than ship an unverified target, the script stays HomePod-only; `guides/laundry_automation.md` covers family-room awareness with a plain push notification when the Sonos is busy, entirely outside this script.

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
  notification_title: "My Alert"  # optional: push title when TTS is suppressed
```

| Field | Required | Default | Description |
|---|---|---|---|
| `message` | Yes | — | Text to speak. Templates are supported. |
| `target` | No | `auto` | `kitchen`, `master_bedroom`, `office`, `averys_room`, or `auto` — picks master bedroom when `everyone_sleeping` is on, kitchen otherwise |
| `notification_title` | No | `Missed Announcement` | Title for the push notification sent when TTS is suppressed |

**Video call check:** Before routing to a speaker, the script checks `sensor.nates_mac_mini_active_camera` and `sensor.nates_work_laptop_active_camera`. If either is not `Inactive`, the announcement is suppressed and a push notification is sent to `notify.mobile_app_nates_iphone` instead. This keeps TTS from interrupting work calls.

Do not call `chime_tts.say` directly from automations — use the script so the video call check and per-room volume stay in one place. All four targets (kitchen, master bedroom, office, Avery's room) are individually confirmed working end-to-end.

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
