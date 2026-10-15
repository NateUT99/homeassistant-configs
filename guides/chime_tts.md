# Chime TTS Integration

*Last updated: October 2026*

## Overview

Chime TTS is a HACS integration that wraps Home Assistant's cloud TTS service with a configurable chime sound prefix. Announcements open with a brief soft chime before the spoken message, making them instantly recognizable as home automation alerts rather than unexpected audio playback. This instance runs `nimroddolev/chime_tts` v1.3.0, installed from HACS's default store (no custom repository registration needed).

`script.household_tts_announce` is the sole entry point for every TTS announcement in this house. It pre-generates each announcement's audio via `chime_tts.say_url`, then dispatches it with `media_player.play_media` (through the small `script.household_tts_play` helper) — either to the resolved HomePod(s), or, when `auto` resolves to the living room, straight to the living room Sonos soundbar as a native Sonos announce over whatever is playing. If the soundbar is offline, the clip plays on the kitchen HomePod instead; When TTS can't land — a call in progress on the MacBook Pro, the resolved HomePod being `unavailable`, or playback never starting — the script falls back to a push notification to Nate's iPhone, optionally as an iOS critical alert.

---

## Architecture

```
automations
          │
          ▼
script.household_tts_announce
          │
          ▼
  resolved_target == 'living_room' and not call_quiet?
   (only possible via target: auto, when the AppleTV is on)
          │
   ┌──────┴──────┐
   │ yes         │ no
   ▼             ▼
 (A) living      (B) normal room resolution
     room             │  fallback guards, checked in order:
     branch           ├─ on a call: every room (routine) or  ─┐
                       │    office only (urgent)                │
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
                       script.household_tts_play  (script.turn_on → play_media, announce: true,
                                   │                   one call, every resolved room)
                                   ▼
                       wait_for_trigger: a targeted HomePod → playing, or the play run ending
                                   │
                                   ▼
                       [never started: push]
                                   │
                                   ▼
                       wait_for_trigger: playing → idle on whichever HomePod(s) were targeted
                                   │
                                   ▼
                       [resume living room AppleTV if it was ducked]

(A) chime_tts.say_url  (pre-generate, no boost)
          │
          ▼
    soundbar unavailable/unknown?
          │
   ┌──────┴──────┐
   │ no          │ yes
   ▼             ▼
 media_player.play_media       kitchen HomePod via script.household_tts_play,
 → living room soundbar         wait for it to finish (push if the kitchen
   (announce: true,             is offline too)
    extra.volume 60, LAN URL)
   │
   ▼
 delay: clip duration + 2s  (holds the queue; the AppleTV is never paused)
```

`chime_tts.say_url` generates the chime + spoken message and returns `{url, media_content_id, duration, success}` without playing anything — this instance is configured for the www-folder path, so `url` populates and `media_content_id` comes back `null`. The script always calls `say_url` and then a separate `media_player.play_media` (`announce: true`), never `chime_tts.say` directly — pre-generating first is what keeps the pause-to-playback gap under a second instead of several seconds of dead air. See `LESSONS.md` → TTS & Media.

Volume is handled differently per branch: a single-room HomePod call keeps that room's own tuned `volume_level` (kitchen 0.6, office 0.5, Avery's room 0.4, master bedroom 0.4/0.5 by sleep state); a multi-room HomePod call uses one shared 0.5, since one `media_player.play_media` call can't carry a different volume per target. The living room branch passes the announce volume to the Sonos as `extra: {volume: 60}` (or `volume_override` × 100); Sonos plays the clip at that level over the show and puts its own volume back afterward. The HomePod branch's clip is boosted with `audio_conversion: "Volume 150%"`; the living room clip isn't, since the Sonos announce volume sets its loudness and a further boost only clips. See `LESSONS.md` → TTS & Media.

> **Family room Sonos is not a script target.** `chime_tts.say` against the family room Sonos (`media_player.family_room_theater`) produces no audio and no error at any log level — see `LESSONS.md` → TTS & Media. `guides/laundry_automation.md` handles family-room awareness with a plain push notification when the Sonos is busy, entirely outside this script. The family room is a separate Sonos-only system from the living room soundbar this script does target.

> **Coordinated change:** HomePod playback converts chime_tts's URL to the clip's local path, assuming chime_tts keeps writing clips under `/config/www/` (served at `/local/`). If chime_tts is reconfigured to the media-folder path, update the `clip` template on every `script.household_tts_play` call in `script.household_tts_announce`. The living room Sonos fetches the URL itself, so its call rewrites the host to HA's LAN address, `http://10.10.0.4` (DHCP-reserved); if that address changes, update the soundbar `play_media` call.

> **Coordinated change:** Room volumes and the `audio_conversion` boost live inside `script.household_tts_announce`'s `variables:` and its `chime_tts.say_url` actions, not in a shared table. Adjusting either means editing the script directly — see `guides/reminders.md` and any other guide referencing this script for the current field contract.

---

## Design Decisions

- **Pre-generate via `chime_tts.say_url`, then `media_player.play_media` — never `chime_tts.say` directly.** `chime_tts.say` generates and plays in one blocking call; the ~3–4s Nabu Casa cloud round trip is invisible when nothing else needs to fall silent first, but this script pauses another room's media in most paths, and that pause completes almost instantly. Generating before pausing anything is what keeps the gap under a second. See `LESSONS.md` → TTS & Media.
- **Wait on a literal state trigger, not a duration-based `delay`.** `chime_tts.say_url`'s reported `duration` doesn't reliably track real multi-speaker playback time, and a templated `entity_id` inside a `wait_for_trigger` can't be auto-tracked by HA and silently falls back to its timeout. The HomePod branch instead lists every HomePod as a literal state trigger and reacts to the real transition, keeping the duration only as a timeout backstop. The living room Sonos announce is the exception: it never changes the soundbar's state, so that branch holds the queue with a `delay` of the clip's duration plus 2 seconds. See `LESSONS.md` → TTS & Media.
- **`auto` prefers the living room over kitchen whenever the AppleTV is on.** `auto` resolves `master_bedroom` if `everyone_sleeping`, else `living_room` if the AppleTV is on (`playing`, `paused`, or `idle` — anything but `off`/`standby`/`unavailable`/`unknown`), else `kitchen`. An AppleTV that's on at all is a reliable signal someone is in the living room; reaching an empty kitchen instead wouldn't help them. `broadcast` deliberately has no living-room exception — it exists to reach the whole house (kitchen, master bedroom, office, Avery's room), and narrowing it to one room on some calls would silently reduce that coverage for automations that rely on it.
- **The AppleTV's own state is checked directly, never its Sonos soundbar.** The living room soundbar (HDMI ARC) reports `playing` continuously based on the input being selected, not on whether the AppleTV is actually producing sound — it can't distinguish playing from paused, let alone idle. See `LESSONS.md` → TTS & Media.
- **Living room announcements play on the Sonos soundbar, not the AppleTV.** The AppleTV's AirPlay stream plays at a low level HA can't raise: neither `media_player.volume_set` on the AppleTV nor a louder clip made an audible difference. A native Sonos announce (`announce: true` with `extra.volume`) sets its own level and mixes over the show, so the AppleTV isn't paused or resumed. The trade-off is failure detection: the announce never changes the soundbar's state, so only an offline soundbar falls back to the kitchen. See `LESSONS.md` → TTS & Media.
- **Ducking the AppleTV for HomePod announcements is gated on it actually being `playing`.** Pausing an already-paused or idle AppleTV is a no-op that would also incorrectly mark it as this call's to resume, so a show the person had already left paused stays paused rather than auto-resuming.
- **Playback runs in a separate script, and a HomePod that never starts playing gets a push.** The Apple TV integration's decoder failure (`miniaudio.DecodeError`) isn't a `HomeAssistantError`, so `continue_on_error` can't catch it — inside this script it aborts the run before any fallback step. `script.household_tts_play` holds only the `play_media` call and is started with `script.turn_on` (not a blocking call), so a failure ends that run alone. The announce script then waits up to 15 seconds for a targeted HomePod to reach `playing` (about a second on success) or for the play run to end without it, and pushes if playback didn't start. There is no retry: the only reproducible failure was an oversized clip, which a retry replays unchanged, and the local clip path below avoids it. The kitchen fallback for an offline soundbar goes through the same helper. See `LESSONS.md` → TTS & Media.
- **HomePod playback passes the clip's local path, not a URL.** Given a URL, pyatv streams the clip through a 64 KiB buffer and fails with `miniaudio.DecodeError` on any clip over 56 KiB — about 7 seconds of audio — every time. Given a path, it decodes the whole file up front. Each HomePod playback call converts `chime_tts.say_url`'s URL to `/config/www/…`, so message length is no longer limited. Cloud TTS generation itself still needs the internet. See `LESSONS.md` → TTS & Media.
- **`audio_conversion: "Volume 150%"` boosts the HomePod clip only.** The FFmpeg-level boost is independent of any speaker's `volume_level` and needs no restore step. The 150% clip already peaks at 0 dBFS, so a higher setting clips rather than getting louder. See `LESSONS.md` → TTS & Media.
- **Config entry over YAML.** The custom integration is enabled via a config entry (**Settings → Devices & Services → Add Integration → Chime TTS**), not a `configuration.yaml` block. HA discovers the custom component automatically once its files exist in `custom_components/`; the config entry is what triggers service registration. No restart is required.

---

## Prerequisites

- HACS installed and active — `chime_tts` is a HACS default-store integration, no custom repository needed
- Nabu Casa subscription active (cloud TTS)
- `media_player.kitchen_homepod`, `media_player.master_bedroom_homepod`, `media_player.office_homepod`, `media_player.averys_room_homepod` — HomePods via the Apple TV integration
- `media_player.living_room_appletv` — Apple TV integration; used only for `auto` routing and ducking
- `media_player.living_room_soundbar` — Sonos (HDMI ARC); plays living room announcements
- HA host on a DHCP reservation at `10.10.0.4` (the Sonos fetches clips from it)

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

**`target: broadcast` always reaches all four rooms — kitchen, master bedroom, office (pushed instead during a call), and Avery's room (unless `input_boolean.avery_sleeping` is on).** There is no living-room exception on this path; automations that need whole-house coverage (`automation.household_hvac_exterior_open_pause`, `automation.kitchen_refrigerator_power_monitor`'s awake-hours branch) rely on `broadcast` reaching everyone, and the living room AppleTV is still ducked so it doesn't compete with the announcement — see Design Decisions.

**`target: auto`'s living-room preference is what most single-room callers should use.** Most TTS automations in this house call with `target: auto` (or an explicit `kitchen`/`master_bedroom` when the message is *about* that room specifically, like a mop-pass warning) rather than `broadcast`, so they benefit from the living-room routing automatically.

**One `media_player.play_media` action targeting a list of entity_ids, not a loop.** Every HomePod resolved for a given call is spoken to with a single action carrying `target.entity_id` as a list — a real single dispatch, not one call per room. A `repeat` action executes its iterations sequentially, so a per-room loop would speak kitchen, then master bedroom, then office, then Avery's room one after another rather than together — audibly staggered, not a broadcast. A single multi-target action starts every resolved HomePod within under a second of each other.

**A call silences routine announcements house-wide; urgent ones still play outside the office.** Every HomePod in the house carries into the office, so during a call a routine announcement is pushed instead of spoken anywhere — `call_quiet` marks every target room busy, including the living room soundbar path. An urgent announcement (`chime_path: error` or `critical_fallback: true`, i.e. water leak, refrigerator fault, laundry fault) still plays everywhere except the office, which gets the push; a life-safety alert shouldn't wait for a call to end. `office_busy` is `true` when `binary_sensor.nates_work_laptop_audio_input_in_use` is `on` — the same MacBook Pro signal `automation.office_camera_lighting` relies on to detect an active call, deliberately audio-input rather than camera so an audio-only call (mic in use, no camera) still counts.

**Fallback guard.** Any room that's unreachable — busy because of a call (see above), or that room's HomePod offline — is pulled out of the room list before the `media_player.play_media` call and covered by a single push to `notify.mobile_app_nates_iphone` instead (one push regardless of how many rooms were unreachable, since the message/title is identical either way). The remaining reachable rooms still get TTS in their own single action. `chime_tts` against a dead speaker fails silently at every log level, so detecting "offline" ahead of the call — rather than after — is what keeps the announcement from vanishing with no trace.

`critical_fallback: true` upgrades that push to a critical alert; callers that just want the message delivered leave it unset.

Do not call `chime_tts.say_url`, `media_player.play_media`, or `script.household_tts_play` directly from automations — use the script so the fallback guards, per-room volume, living-room routing, and ducking logic stay in one place.

---

## Related HA Config

| Friendly Name | Entity / Service | Type |
|---|---|---|
| TTS Announce | `script.household_tts_announce` | Script — standard entry point for all TTS announcements |
| TTS Play | `script.household_tts_play` | Script — internal; runs one `play_media` call so a playback failure can't abort the announce script |
| Chime TTS: Say URL | `chime_tts.say_url` | Service (Chime TTS config entry) — pre-generates audio |
| Kitchen HomePod | `media_player.kitchen_homepod` | Media player (Apple TV integration) |
| Master Bedroom HomePod | `media_player.master_bedroom_homepod` | Media player (Apple TV integration) |
| Office HomePod | `media_player.office_homepod` | Media player (Apple TV integration) |
| Avery's Room HomePod | `media_player.averys_room_homepod` | Media player (Apple TV integration) |
| Living Room AppleTV | `media_player.living_room_appletv` | Media player (Apple TV integration) — `auto` routing signal; ducked for HomePod announcements |
| Living Room Soundbar | `media_player.living_room_soundbar` | Media player (Sonos) — plays living room announcements |

---

## Related Documents

- `standards/automations.md` — defines the `text_to_speech` label applied to automations that use `script.household_tts_announce`
- `guides/laundry_automation.md` — first consumer of the script (kitchen/master_bedroom targets); also owns the family-room-busy push notification, handled independently of this script
- `LESSONS.md` → TTS & Media — Sonos playback diagnostic trail (why family room isn't a script target); the pre-generation, wait_for_trigger, AppleTV AirPlay volume, audio_conversion ceiling, and HDMI ARC gotchas behind this script's current design
