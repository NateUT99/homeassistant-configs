# Chime TTS Integration

*Last updated: June 2026*

## Overview

Chime TTS is a HACS integration that wraps Home Assistant's cloud TTS service with a configurable chime sound prefix. Announcements open with a brief soft chime before the spoken message, making them instantly recognizable as home automation alerts rather than unexpected audio playback. Two `notify.*` services are configured — one per HomePod target room — and are the standard delivery mechanism for all TTS announcements in this instance.

---

## Architecture

```
configuration.yaml notify: entries
          │
          ▼
  notify.reminder_kitchen          notify.reminder_master_bedroom
  (kitchen HomePod, vol 0.6)       (master bedroom HomePod, vol 0.4)
          │                                    │
          └─────────────┬──────────────────────┘
                        ▼
              Chime TTS (HACS)
                ├── chime prefix  (chime_path: soft)
                └── spoken message  (tts_platform: cloud, Nabu Casa)
                        │
                        ▼
           HA announce pipeline
                        │
                        ▼
     media_player.kitchen_homepod / media_player.master_bedroom_homepod
```

The `announce: true` flag routes playback through HA's announce pipeline, which interrupts current audio and restores it after the announcement. Chime TTS provides its own chime prefix via `chime_path`; this replaces rather than duplicates the HomePod's native announcement bell. `cache: true` caches the TTS audio on disk so repeated identical messages skip the Nabu Casa API call.

Volume levels differ intentionally — 0.6 for the kitchen (ambient noise) and 0.4 for the master bedroom (nighttime/quiet context).

---

## Prerequisites

- HACS installed and active
- Nabu Casa subscription active (cloud TTS)
- `media_player.kitchen_homepod` and `media_player.master_bedroom_homepod` — HomePods managed via the Apple TV integration

---

## Steps

### 1. Install Chime TTS via HACS

In the HA UI: **Settings → HACS → Integrations → Explore & Download Repositories**. Search for **Chime TTS** and download it. Restart HA after installation.

### 2. Add configuration to `configuration.yaml`

Add the following under the top-level `notify:` key. If a `notify:` block already exists, append to the existing list.

```yaml
notify:
  - name: reminder_kitchen
    platform: chime_tts
    chime_path: soft
    entity_id:
      - media_player.kitchen_homepod
    tts_platform: cloud
    volume_level: 0.6
    cache: true
    announce: true
  - name: reminder_master_bedroom
    platform: chime_tts
    chime_path: soft
    entity_id:
      - media_player.master_bedroom_homepod
    tts_platform: cloud
    volume_level: 0.4
    cache: true
    announce: true
```

### 3. Restart HA

`notify:` platform entries require a full restart — a configuration reload is not sufficient. After restart, `notify.reminder_kitchen` and `notify.reminder_master_bedroom` appear in **Developer Tools → Services**.

### 4. Verify

Call the service from **Developer Tools → Services**:

```yaml
service: notify.reminder_kitchen
data:
  message: "Test announcement."
```

The kitchen HomePod should play the soft chime followed by the spoken message.

---

## Usage

Call a service with a `message` key. Templates are supported:

```yaml
action: notify.reminder_kitchen
data:
  message: >-
    Your message here. {{ states('sensor.some_sensor') }}.
```

No volume, target, or chime configuration is needed at call time — all of that is baked into the `configuration.yaml` service definition.

---

## Integration Label

Chime TTS is a delivery mechanism rather than a feature integration, so no `int_chime_tts` label is created. The `text_to_speech` label (see `standards/automations.md`) serves as the cross-cutting identifier for all automations that use these services.

---

## Related HA Config

| Friendly Name | Entity / Service | Type |
|---|---|---|
| Reminder — Kitchen | `notify.reminder_kitchen` | Notify service (Chime TTS) |
| Reminder — Master Bedroom | `notify.reminder_master_bedroom` | Notify service (Chime TTS) |
| Kitchen HomePod | `media_player.kitchen_homepod` | Media player (Apple TV integration) |
| Master Bedroom HomePod | `media_player.master_bedroom_homepod` | Media player (Apple TV integration) |

---

## Related Files

| File | Deployed location | Purpose |
|---|---|---|
| `configuration.yaml` (managed in HA) | HA config root | Declares both `notify:` platform entries |

---

## Related Documents

- `standards/automations.md` — defines the `text_to_speech` label applied to automations that use these services
- `guides/outdoor_air_quality_alerting.md` — uses both services for AQI alert announcements
- `LESSONS.md` → TTS & Media — explains why `notify.reminder_*` is preferred over bare `media_player.play_media`
