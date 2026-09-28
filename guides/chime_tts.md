# Chime TTS Integration

*Last updated: September 2026*

## Overview

Chime TTS is a HACS integration that wraps Home Assistant's cloud TTS service with a configurable chime sound prefix. Announcements open with a brief soft chime before the spoken message, making them instantly recognizable as home automation alerts rather than unexpected audio playback. This instance runs `nimroddolev/chime_tts` v1.3.0, installed from HACS's default store (no custom repository registration needed).

`script.household_tts_announce` is the sole entry point for every TTS announcement in this house. It pre-generates each announcement's audio via `chime_tts.say_url`, then dispatches it with `media_player.play_media` — either to the resolved HomePod(s), or directly to the living room AppleTV when `auto` resolves there. When TTS can't land — an active video call, or the resolved HomePod being `unavailable` — the script falls back to a push notification to Nate's iPhone, optionally as an iOS critical alert.

---

## Architecture

```
automations
          │
          ▼
script.household_tts_announce
          │
          ▼
  resolved_target == 'living_room'?
   (only possible via target: auto, when the AppleTV is on)
          │
   ┌──────┴──────┐
   │ yes         │ no
   ▼             ▼
 (A) living      (B) normal room resolution
     room             │  fallback guards, checked in order:
     branch           ├─ office busy with a call            ─┐
                       ├─ resolved HomePod unavailable/unknown ─┼─► notify.mobile_app_nates_iphone
                       │                     (critical payload when critical_fallback: true)
                       └─ routing (target: kitchen / master_bedroom / office / averys_room / broadcast / auto)
                                   │
                                   ▼
                       chime_tts.say_url  (pre-generate chime + TTS, not yet played)
                                   │
                                   ▼
                       media_player.volume_set  (per-room tuned volume)
                                   │
                                   ▼
                       [duck living room AppleTV if it's actually playing]
                                   │
                                   ▼
                       media_player.play_media  (announce: true, one call, every resolved room)
                                   │
                                   ▼
                       wait_for_trigger: playing → idle on whichever HomePod(s) were targeted
                                   │
                                   ▼
                       [resume living room AppleTV if it was ducked]

(A) chime_tts.say_url  (pre-generate)
          │
          ▼
    [pause the living room AppleTV, only if it was actually playing]
          │
          ▼
    media_player.play_media  (announce: true, living room AppleTV only)
          │
          ▼
    wait_for_trigger: playing → paused, or playing → idle
          │
          ▼
    [resume the AppleTV, only if this call was the one that paused it]
```

`chime_tts.say_url` generates the chime + spoken message and returns `{url, media_content_id, duration, success}` without playing anything — this instance is configured for the www-folder path, so `url` populates and `media_content_id` comes back `null`. The script always calls `say_url` and then a separate `media_player.play_media` (`announce: true`), never `chime_tts.say` directly — pre-generating first is what keeps the pause-to-playback gap under a second instead of several seconds of dead air. See `LESSONS.md` → TTS & Media.

Volume is handled differently per branch: a single-room HomePod call keeps that room's own tuned `volume_level` (kitchen 0.6, office 0.5, Avery's room 0.4, master bedroom 0.4/0.5 by sleep state); a multi-room HomePod call uses one shared 0.5, since one `media_player.play_media` call can't carry a different volume per target. The living room branch sets no `volume_level` at all — the AppleTV already has a real in-progress volume the viewer chose, and the announce pipeline plays at it as-is. Every branch's generated clip is boosted with `audio_conversion: "Volume 150%"`, since cloud TTS masters noticeably quieter than typical TV/streaming audio. See `LESSONS.md` → TTS & Media.

> **Family room Sonos is not a script target.** `chime_tts.say` against the family room Sonos (`media_player.family_room_theater`) produces no audio and no error at any log level — see `LESSONS.md` → TTS & Media. `guides/laundry_automation.md` handles family-room awareness with a plain push notification when the Sonos is busy, entirely outside this script. The family room is a separate Sonos-only system from the living room AppleTV this guide otherwise covers.

> **Coordinated change:** Room volumes and the `audio_conversion` boost live inside `script.household_tts_announce`'s `variables:` and its `chime_tts.say_url` actions, not in a shared table. Adjusting either means editing the script directly — see `guides/reminders.md` and any other guide referencing this script for the current field contract.

---

## Design Decisions

- **Pre-generate via `chime_tts.say_url`, then `media_player.play_media` — never `chime_tts.say` directly.** `chime_tts.say` generates and plays in one blocking call; the ~3–4s Nabu Casa cloud round trip is invisible when nothing else needs to fall silent first, but this script pauses another room's media in most paths, and that pause completes almost instantly. Generating before pausing anything is what keeps the gap under a second. See `LESSONS.md` → TTS & Media.
- **Wait on a literal state trigger, not a duration-based `delay`.** `chime_tts.say_url`'s reported `duration` doesn't reliably track real multi-speaker playback time, and a templated `entity_id` inside a `wait_for_trigger` can't be auto-tracked by HA and silently falls back to its timeout. Both branches instead list every entity a call could target as literal state triggers and react to the real transition, keeping the duration only as a timeout backstop. See `LESSONS.md` → TTS & Media.
- **`auto` prefers the living room over kitchen whenever the AppleTV is on.** `auto` resolves `master_bedroom` if `everyone_sleeping`, else `living_room` if the AppleTV is on (`playing`, `paused`, or `idle` — anything but `off`/`standby`/`unavailable`/`unknown`), else `kitchen`. An AppleTV that's on at all is a reliable signal someone is in the living room; reaching an empty kitchen instead wouldn't help them. `broadcast` deliberately has no living-room exception — it exists to reach the whole house (kitchen, master bedroom, office, Avery's room), and narrowing it to one room on some calls would silently reduce that coverage for automations that rely on it.
- **The AppleTV's own state is checked directly, never its Sonos soundbar.** The living room soundbar (HDMI ARC) reports `playing` continuously based on the input being selected, not on whether the AppleTV is actually producing sound — it can't distinguish playing from paused, let alone idle. See `LESSONS.md` → TTS & Media.
- **Pausing and resuming the AppleTV are both gated on it having actually been `playing`, not merely on** `auto` **routing there or the call ducking it.** Pausing an already-paused or idle AppleTV is a no-op that would also incorrectly mark it as this call's to resume; resuming is further gated on this call being the one that paused it, so a show the person had already left paused stays paused rather than auto-resuming.
- **`audio_conversion: "Volume 150%"` boosts the generated clip itself.** Cloud TTS masters noticeably quieter than TV/streaming audio even when the target speaker's own volume is untouched; this FFmpeg-level boost is independent of any speaker's `volume_level` and needs no restore step. See `LESSONS.md` → TTS & Media.
- **Config entry over YAML.** The custom integration is enabled via a config entry (**Settings → Devices & Services → Add Integration → Chime TTS**), not a `configuration.yaml` block. HA discovers the custom component automatically once its files exist in `custom_components/`; the config entry is what triggers service registration. No restart is required.

---

## Prerequisites

- HACS installed and active — `chime_tts` is a HACS default-store integration, no custom repository needed
- Nabu Casa subscription active (cloud TTS)
- `media_player.kitchen_homepod`, `media_player.master_bedroom_homepod`, `media_player.office_homepod`, `media_player.averys_room_homepod` — HomePods via the Apple TV integration
- `media_player.living_room_appletv` — Apple TV integration; `media_player.living_room_soundbar` exists (Sonos, HDMI ARC) but is not used by this script — see Design Decisions

---

## Steps

### 1. Install Chime TTS via HACS

Search **Chime TTS** in **HACS → Integrations** and download it — it's a default-store listing, no custom repository registration needed. Restart Home Assistant to load the integration.

### 2. Add the config entry

**Settings → Devices & Services → Add Integration → Chime TTS.** This has no configuration fields of its own — adding the entry is what registers `chime_tts.say`, `chime_tts.say_url`, `chime_tts.replay`, and `chime_tts.clear_cache` as callable services.

### 3. Verify

Call `chime_tts.say_url` from **Developer Tools → Actions** with `return_response` enabled:

```yaml
action: chime_tts.say_url
data:
  message: "Test announcement."
  chime_path: soft
  tts_platform: cloud
  cache: true
  audio_conversion: "Volume 150%"
```

The response should return a `url` field pointing at a generated `.mp3`. Play it to confirm audio: a `media_player.play_media` call with that `media_content_id`, `media_content_type: music`, and `announce: true` against `media_player.kitchen_homepod` should play the soft chime followed by the boosted spoken message.

---

## TTS Announce Script

All TTS automations in this instance call `script.household_tts_announce` — it is the standard entry point.

```yaml
action: script.household_tts_announce
data:
  message: "Your message here."
  target: auto                    # optional: kitchen / master_bedroom / office / averys_room / broadcast / auto
  notification_title: "My Alert"  # optional: push title used on the fallback path
  critical_fallback: true         # optional: send the fallback push as an iOS critical alert
  chime_path: error               # optional: soft (default) or error
  volume_override: 0.75           # optional: 0.0-1.0, overrides the tuned per-room volume
```

| Field | Required | Default | Description |
|---|---|---|---|
| `message` | Yes | — | Text to speak. Templates are supported. |
| `target` | No | `auto` | `kitchen`, `master_bedroom`, `office`, `averys_room`, `broadcast`, or `auto` — `auto` picks `master_bedroom` if `everyone_sleeping`, else `living_room` if the AppleTV is on, else `kitchen`; `broadcast` unconditionally fans out to kitchen, master bedroom, office, and Avery's room |
| `notification_title` | No | `Missed Announcement` | Title for the push notification sent when a room falls back to a push |
| `critical_fallback` | No | `false` | When a fallback push fires, add the iOS `push.sound.critical` / `interruption-level: critical` payload so it breaks through silent mode and Focus |
| `chime_path` | No | `soft` | Which Chime TTS preset plays before the message. `soft` is the routine-announcement chime every other caller uses; `error` is a distinct fault/life-safety chime — used by the water leak, refrigerator fault, and laundry fault callers |
| `volume_override` | No | — | Overrides the tuned per-room volume table and the multi-room 0.5 default with this exact level (0.0–1.0) for every targeted HomePod. Used by the water leak alert (0.75) to be unmistakably louder than any routine announcement |

**`target: broadcast` always reaches all four rooms — kitchen, master bedroom, office (unless it's busy with a call), and Avery's room (unless `input_boolean.avery_sleeping` is on).** There is no living-room exception on this path; automations that need whole-house coverage (`automation.household_hvac_exterior_open_pause`, `automation.kitchen_refrigerator_power_monitor`'s awake-hours branch) rely on `broadcast` reaching everyone, and the living room AppleTV is still ducked so it doesn't compete with the announcement — see Design Decisions.

**`target: auto`'s living-room preference is what most single-room callers should use.** Most TTS automations in this house call with `target: auto` (or an explicit `kitchen`/`master_bedroom` when the message is *about* that room specifically, like a mop-pass warning) rather than `broadcast`, so they benefit from the living-room routing automatically.

**One `media_player.play_media` action targeting a list of entity_ids, not a loop.** Every HomePod resolved for a given call is spoken to with a single action carrying `target.entity_id` as a list — a real single dispatch, not one call per room. A `repeat` action executes its iterations sequentially, so a per-room loop would speak kitchen, then master bedroom, then office, then Avery's room one after another rather than together — audibly staggered, not a broadcast. A single multi-target action starts every resolved HomePod within under a second of each other.

**"Office busy" is a per-room condition, not a global one.** A call only makes the *Office* speaker unsuitable — kitchen, master bedroom, and Avery's room are physically far enough away that TTS there won't bleed into the call's microphone. `office_busy` is `true` when `binary_sensor.nates_work_laptop_audio_input_in_use` is `on` — the same MacBook Pro signal `automation.office_camera_lighting` relies on to detect an active call, deliberately audio-input rather than camera so an audio-only call (mic in use, no camera) still excludes the office.

**Fallback guard.** Any room that's unreachable — office busy with a call, or that room's HomePod offline — is pulled out of the room list before the `media_player.play_media` call and covered by a single push to `notify.mobile_app_nates_iphone` instead (one push regardless of how many rooms were unreachable, since the message/title is identical either way). The remaining reachable rooms still get TTS in their own single action. `chime_tts` against a dead speaker fails silently at every log level, so detecting "offline" ahead of the call — rather than after — is what keeps the announcement from vanishing with no trace.

`critical_fallback: true` upgrades that push to a critical alert; callers that just want the message delivered leave it unset.

Do not call `chime_tts.say_url` or `media_player.play_media` directly from automations — use the script so the fallback guards, per-room volume, living-room routing, and ducking logic stay in one place.

---

## Related HA Config

| Friendly Name | Entity / Service | Type |
|---|---|---|
| TTS Announce | `script.household_tts_announce` | Script — standard entry point for all TTS announcements |
| Chime TTS: Say URL | `chime_tts.say_url` | Service (Chime TTS config entry) — pre-generates audio |
| Kitchen HomePod | `media_player.kitchen_homepod` | Media player (Apple TV integration) |
| Master Bedroom HomePod | `media_player.master_bedroom_homepod` | Media player (Apple TV integration) |
| Office HomePod | `media_player.office_homepod` | Media player (Apple TV integration) |
| Avery's Room HomePod | `media_player.averys_room_homepod` | Media player (Apple TV integration) |
| Living Room AppleTV | `media_player.living_room_appletv` | Media player (Apple TV integration) — spoken to directly or ducked, depending on routing |

---

## Related Documents

- `standards/automations.md` — defines the `text_to_speech` label applied to automations that use `script.household_tts_announce`
- `guides/laundry_automation.md` — first consumer of the script (kitchen/master_bedroom targets); also owns the family-room-busy push notification, handled independently of this script
- `LESSONS.md` → TTS & Media — Sonos playback diagnostic trail (why family room isn't a script target); the pre-generation, wait_for_trigger, AppleTV-announce, volume-mastering, and HDMI ARC gotchas behind this script's current design
