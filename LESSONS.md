# LESSONS.md

Hard-won knowledge about Home Assistant quirks, integration behavior, and patterns that didn't work as expected. Read before proposing workarounds to things that seem "obviously" broken — the obvious solution may already be documented here as having failed.

When a new gotcha is discovered, propose adding it here.

---

## Automations & YAML

### `condition: state` does not accept templated entity IDs

The `condition: state` shorthand requires a literal entity ID. Templates in the `entity_id` field fail silently — the condition evaluates without error but does not behave as expected.

Use `condition: template` with `is_state()` or `states()` instead:

```yaml
# Wrong — fails silently
- condition: state
  entity_id: "light.{{ states('input_text.target_light') }}"
  state: "on"

# Right
- condition: template
  value_template: "{{ is_state('light.' ~ states('input_text.target_light'), 'on') }}"
```

### `ha_config_set_automation` slugifies apostrophes as `_s_`, not dropped — violates naming standard

When creating an automation via `ha_config_set_automation` with no `identifier` (fresh create), HA auto-generates the `entity_id` by slugifying the `alias`. For an alias containing an apostrophe — e.g. `"Avery's Room: Sleep Mode"` — the generated ID is `automation.avery_s_room_sleep_mode`, not `automation.averys_room_sleep_mode`. `standards/naming.md` requires apostrophes dropped entirely (`averys_room`), so the auto-generated ID does not match the standard and needs a manual fix.

**Fix:** after creating an automation whose alias contains an apostrophe, check the returned `entity_id`/`automation_id` and rename it with `ha_set_entity(new_entity_id=...)` if it doesn't match the standard's apostrophe-dropped form:

```python
# Create returns automation.avery_s_room_sleep_mode — wrong per standard
ha_config_set_automation(config={"alias": "Avery's Room: Sleep Mode", ...})

# Rename to match standards/naming.md
ha_set_entity(
    entity_id="automation.avery_s_room_sleep_mode",
    new_entity_id="automation.averys_room_sleep_mode",
)
```

This only affects fresh creates (no `identifier` passed) with an apostrophe in the alias — updates to an existing automation keep the existing entity_id regardless of alias changes.

### Separate automations beat merged ones when shared triggers cause state capture problems

When two pieces of logic share a trigger and one depends on state captured at trigger time, merging them into one automation can produce unreliable state reads. The trigger fires, both branches start executing, and the second branch sees state that has already been mutated by the first.

Splitting into separate automations — each with its own trigger and its own state capture — is more reliable than chaining logic inside one automation with `parallel` or `choose` blocks.

### `notify.send_message` does not support iOS-specific notification features

`notify.send_message` is the only way to target a UI-created notify group entity (e.g., `notify.household_members`). Its service schema accepts only `message` and `title` — there is no `data` field. Passing a nested `data` key raises `extra keys not allowed @ data['data']` at runtime.

iOS-specific features — critical sound (`data.data.push`), notification tags (`data.data.tag`), and actionable buttons (`data.data.actions`) — require the native `notify.mobile_app_<device>` services, which accept a full `data` field with a nested `data` sub-key for platform-specific options:

```yaml
# Correct structure for notify.mobile_app_nates_iphone
action: notify.mobile_app_nates_iphone
data:
  message: "..."
  title: "..."
  data:              # platform-specific iOS options live here
    push:
      sound:
        name: default
        critical: 1
        volume: 1
    tag: some_tag
    actions:
      - action: "MY_ACTION"
        title: "Do It"
```

`notify.notify` (the legacy catch-all) also accepts `data`, but its `target` field routes to legacy service names — not to UI-created group entities — so it does not solve the group-targeting problem either.

### `calendar.get_events` errors with "did not match any entities" when the calendar entity is `unavailable`

`calendar.get_events` is a response-returning service call. When the target entity is `unavailable` — not just missing — HA returns the misleading error "Service call requested response data but did not match any entities", the same error as for a nonexistent entity. The automation errors and exits immediately, sending no notification.

The Remote Calendar integration goes `unavailable` on sync failures. Check the calendar entity state before assuming the automation config is broken. After reloading the integration, manually trigger the reminder automation to recover the missed notification.

### `condition: trigger` with a specific ID does not match manual triggers

`condition: trigger` with `id: "some_id"` only matches when the automation fires via the named trigger. Manual triggers (`automation.trigger` service or Developer Tools → Run) have `trigger.platform: null` and no ID, so all `choose` branches guarded by this pattern fail silently and the automation does nothing.

To allow a branch to also fire on manual triggers, wrap with an `or` condition:

```yaml
conditions:
  - condition: or
    conditions:
      - condition: trigger
        id: "evening_check"
      - condition: template
        value_template: "{{ trigger.platform is none }}"
```

---

## Dashboards

### Bubble Card `state_display` does not evaluate Jinja2 templates reliably

Bubble Card's `state_display` field accepts Jinja2 syntax (`{{ }}`), and basic `states()` calls with simple filters (e.g., `|round|int`) work in some contexts. However, HA-specific functions (`as_timestamp`, `timestamp_custom`, `strptime`) and chained method calls (`strptime(...).strftime(...)`) silently fail — the card falls back to displaying the entity's raw state string. There is no error surfaced anywhere.

**Do not use `state_display` templates for date formatting.** Instead, have the template sensor return the desired display string directly (e.g., `strftime('%B %-d, %Y')` in the sensor template). Card `state_display` is reliable only for trivial numeric formatting of the card's own entity state.

### Native HA cards do not auto-format `device_class: date` template sensors

The tile card and other native HA cards call `computeStateDisplay` which formats `input_datetime` entities as human-readable dates. Template sensors with `device_class: date` are **not** formatted this way — they display their raw ISO state string (`2026-06-15`). If a template sensor needs to display a date in a card, the sensor state itself must be the formatted string.

**Bottom line:** use `notify.mobile_app_nates_iphone` for any notification that uses iOS features. Reserve `notify.send_message` + a group entity for simple message-only broadcasts with no platform-specific payload.

### `ha_config_set_automation` `category` parameter is ignored in `python_transform` mode

When calling `ha_config_set_automation` with `python_transform`, the `category` parameter has no effect — the automation's category is left unchanged. The category must be set in a separate `ha_set_entity` call using the `categories` parameter:

```python
# This does NOT change the category when python_transform is used:
ha_config_set_automation(identifier="...", python_transform="...", category="some_id")

# Follow up with this instead:
ha_set_entity(entity_id="automation.foo", categories={"automation": "some_id"})
```

This does not affect full `config` replacement mode — the `category` parameter works correctly there.

### HA Manual Alarm panel arms instantly even with open contacts — gate arming in an automation

The HA Manual Alarm Control Panel (`platform: manual`) accepts an arm request (`alarm_arm_night`, `alarm_arm_away`, etc.) unconditionally. It never checks the state of contact sensors before arming and has no "arm failed" event. There are no `arming_requested` or `arm_failed` states.

Combined with how `automation.household_alarm_perimeter_trigger` works — it only fires when a perimeter contact *changes* to `on` — a door that is **already open at arm time** creates a silent gap: the panel arms normally, but the perimeter trigger never fires for that door (its state did not change), and the alarm is now armed with an open contact that will never trip it.

**Fix:** gate arming in an automation that checks perimeter state *before* calling the arm service. Do not rely on the panel or the perimeter trigger to catch this condition.

```yaml
# WRONG — arms unconditionally; open door at arm time silently creates a gap
- action: alarm_control_panel.alarm_arm_night
  target:
    entity_id: alarm_control_panel.home_alarm

# RIGHT — check perimeter first; arm only if clear (or notify if not)
- if:
    - condition: state
      entity_id: binary_sensor.exterior_door_open
      state: "off"
    # ... additional checks (e.g. cover.garage_door state: closed)
  then:
    - action: alarm_control_panel.alarm_arm_night
      ...
  else:
    - action: notify.mobile_app_nates_iphone
      # critical push naming the open door(s)
```

`automation.household_bedtime_secure_and_report` implements this pattern for night arming. See `guides/home_alarm.md` for the full design.

### `parallel:` action blocks are safe for small, fixed action counts — check blast radius before assuming so generally

Converting a sequential list of independent actions to a `parallel:` block (e.g. `automation.household_sleep_mode`'s night-prep sequence — thermostat, two lights, a label turn-off, garage, lock, media player) reduces wall-clock time to the slowest single action instead of the sum, with no adverse HA Green load: seven simple service calls firing concurrently is a non-event for both the automation engine and Z2M/Zigbee traffic.

The risk isn't `parallel:` itself, it's what it's applied to. A block becomes a real burst of concurrent device commands, not a handful, when either:

- **A target resolves broadly** — a `label_id`/`area_id` target covering dozens of entities, fired inside a parallel arm
- **The action count is dynamic** — `repeat.for_each` nested inside `parallel`, where the list length isn't visible in the YAML

Neither condition applied here (fixed 7 actions, only one broad target — `label_id: sleeping` — and that target is a single service call, not one call per matched entity). See `standards/automations.md` §5.4 for the check to apply before parallelizing a less obviously-small block.

### Restoration branches need guard conditions

An automation that restores a prior state (turning a thermostat back on after a door closes, restoring lights after a guest mode ends) must verify the current state of the target before restoring. Don't assume that because the automation turned something off, it can blindly turn it back on — the user or another automation may have changed it in the interim.

Always include a `condition: state` (or template equivalent) confirming the target is in the state you expect to restore from.

### `scene.create` snapshots taken from inside a `mode: restart` script capture the script's own output

A save-current-state / do-something / put-it-back pattern where the "do something" script is `mode: restart` must take the `scene.create` snapshot in the **caller**, not inside the script, and guard it on the script being idle.

The `inovelli_fan_canopy` LED-bar blip is the worked example. `script.<prefix>_ceiling_fan_led_blip` is `mode: restart` so a rapid second fan change keeps the bar lit and resets the hold timer. If the snapshot lived at the top of that script, the second (restarting) run would snapshot the bar mid-animation — capturing a blip colour as the "resting" state — and the restore at the end would leave the bar stuck lit.

Fix: `automation.<prefix>_ceiling_fan_wall_control` runs `scene.create` before `script.turn_on`, wrapped in `if: condition: state, entity_id: script.<prefix>_ceiling_fan_led_blip, state: "off"`. A burst snapshots once (blip idle), every subsequent restart within the burst skips the snapshot and reuses that first scene. The automation being `mode: queued` keeps its own runs serialised so the guard can't race itself.

Related gotcha for the restore side: test scene existence with `states.scene.<id> is not none`, **not** `states('scene.<id>')` or `has_value(...)` — a freshly `scene.create`d scene reads `unknown` until it is first activated, so the value-based checks report it missing when it isn't.

---

## Dashboards & Lovelace

### Sections view badges require individual `custom:mushroom-template-badge` entries

Placing a `custom:mushroom-chips-card` as a single item in the sections view `badges` array does not work — the card is silently dropped from the visual editor and may not render at all. The badge row expects individual badge-type objects.

The correct pattern for Mushroom-styled badges is one `custom:mushroom-template-badge` per badge, placed directly in the `badges` array. Use `visibility` conditions on each badge for conditional display — the `type: conditional` chip wrapper used inside chip strips does not work here:

```yaml
badges:
  - type: custom:mushroom-template-badge
    entity: alarm_control_panel.home_alarm
    icon: "mdi:shield-home"
    color: "green"
    tap_action:
      action: more-info

  - type: custom:mushroom-template-badge     # conditional badge
    entity: binary_sensor.water_leak_detected
    icon: mdi:water-alert
    color: red
    tap_action:
      action: navigate
      navigation_path: /mobile-app/water-leaks
    visibility:
      - condition: state
        entity: binary_sensor.water_leak_detected
        state_not: "off"
```

Note: badge field is `color`, not `icon_color` (which is the chip/card field name).

### Mushroom chip `more-info` action does not accept an `entity` field

The Mushroom chip action schema types the `entity` key inside an action object as `never` — placing it there causes the visual editor to reject the chip with "Expected a value of type `never`" and breaks visual editing for the entire chip strip.

The correct pattern: set `entity` at the **chip level** (not inside the action), then use a bare `{action: more-info}` with no entity key. The chip's root `entity` field is what the `more-info` action resolves against.

```yaml
# Wrong — fails visual editor
- type: template
  tap_action:
    action: more-info
    entity: weather.apartment   # ← invalid here

# Right — entity belongs at chip root
- type: template
  entity: weather.apartment     # ← here
  tap_action:
    action: more-info           # entity resolved from chip root
```

This applies to every chip type (template, entity, action) and every action field (tap_action, hold_action, double_tap_action). If the chip needs to target an entity for more-info but has no natural `entity` association, add the `entity` key at the chip root — it does not affect non-more-info actions on the same chip.

### Orphaned CSS selectors in Bubble Card `styles` strings poison the next CSS rule

In Bubble Card's `styles` property (evaluated as a JavaScript template literal), a CSS selector line with no `{}` block is not ignored — the parser treats everything from the end of the previous `}` to the next `{` as a single selector. If the next actual CSS rule is `display: none !important`, that declaration is silently applied to every element matched by the orphaned selectors as well.

The symptoms are specific buttons becoming invisible with no console errors and no obvious connection to the cause. The problem is easy to introduce when editing the styles string because JS expressions in the template (`${setAttribute(...)}`) also land in the selector gap, further obscuring what's happening.

Example of what went wrong: the styles string had these two orphaned lines placed before `.bubble-sub-button-12 { display: none !important; }`:

```
.bubble-sub-button-6,.bubble-sub-button-7,.bubble-sub-button-10,...
.bubble-sub-button-6 .bubble-sub-button-name-container,...
${...JS expressions evaluated to "" ...}
.bubble-sub-button-12 { display: none !important; }
```

The CSS parser saw `.bubble-sub-button-6,.bubble-sub-button-7,.bubble-sub-button-10,...` as part of `.bubble-sub-button-12`'s selector, applying `display: none !important` to all of them.

**Fix:** ensure every CSS selector block in a `styles` string has its `{}` declarations inline. Remove any selector lines that lack one; if styling was intended for those selectors, add the `{}` block explicitly.

### HA rejects single-word custom dashboard URL paths

New storage-mode dashboards require a hyphen in the `url_path`. A slug like `mobile` or `home` is rejected with `VALIDATION_INVALID_PARAMETER: url_path must contain a hyphen (-)`. Use `mobile-home`, `home-main`, etc.

This applies only to new custom dashboards created via the storage API. Built-in paths (`lovelace`, `map`) are unaffected.

### Bubble Card icon vs. button action areas

In Bubble Card button cards, `tap_action` and `hold_action` at the top level bind to the **icon** area, not the card body. `button_action.hold_action` binds to the **button body** (the name/state text area). Using `hold_action` for a primary action the user expects to trigger by holding the card will result in the action only firing when holding the small icon, which is unintuitive.

For hold-to-complete patterns on reminder-style cards:

```yaml
tap_action:
  action: none
hold_action:
  action: none
button_action:
  tap_action:
    action: none
  hold_action:
    action: perform-action
    perform_action: script.turn_on
    target:
      entity_id: script.reminder_mark_complete
    data:
      variables:
        reminder_entity: input_datetime.<key>
```

### Bubble Card pop-up `cards` array accepts any HA card type

The `cards` array inside a Bubble Card `pop-up` card renders like a normal Lovelace card list — native `tile`, `grid`, `conditional`, `picture-entity`, and other custom cards all work. Pop-up content is not restricted to Bubble Card card types.

### Bubble Card `card_type: climate` renders correctly

The Bubble Card climate card (`card_type: climate`, `entity: climate.<entity>`) renders a working thermostat control surface. It does not require any additional configuration beyond the `entity` field for basic HVAC mode and temperature control.

### Sections view footer: ALL content must be in a nested `card` property inside an outer mushroom-chips-card

The native sections view footer only renders content placed in the `card` property of an outer `custom:mushroom-chips-card`. **Any card placed directly as the footer renders as invisible** — this includes grid cards, mushroom-template-cards, and mushroom-chips-card chips placed in the outer `chips` array. Always use this wrapper structure:

```yaml
footer:
  type: custom:mushroom-chips-card   # outer wrapper — required, do not skip
  card:
    # ANY card type goes here — this is what actually renders
    type: grid
    columns: 5
    square: false
    cards:
      - type: custom:mushroom-template-card
        icon: mdi:sofa
        layout: vertical
        tap_action:
          action: navigate
          navigation_path: "#living-room"
```

The inner `card` can be a grid, a mushroom-chips-card with action chips, or any other card type. The outer mushroom-chips-card's own `chips` array does not render. Never place a card directly as the footer value, even if it seems like it should work — it won't.

---

## TTS & Media

### `tts.speak` fails on HomePods via the Apple TV integration

Calling `tts.speak` with `tts.home_assistant_cloud` targeting a HomePod managed by the Apple TV integration fails with `miniaudio.DecodeError: ('failed to init decoder', -1)`. The Apple TV integration's pyatv RAOP streaming layer downloads the Nabu Casa audio URL and passes it through miniaudio for decoding — the format Nabu Casa generates is incompatible.

Use `media_player.play_media` with `announce: true` and the `media-source://tts/cloud?message=...` URI scheme instead. This routes through HA's announce pipeline and avoids the pyatv decode path entirely:

```yaml
action: media_player.play_media
target:
  entity_id: media_player.kitchen_homepod
data:
  announce: true
  extra:
    volume: 65
  media:
    media_content_id: "media-source://tts/cloud?message=Your message here."
    media_content_type: music
```

Templates work inside `media_content_id`.

### Use Chime TTS for all HomePod/Sonos announcements — call `chime_tts.say` directly, not a `notify:` platform

Even though `media_player.play_media` with `announce: true` works on HomePods (see above), the preferred pattern for all TTS announcements in this instance is the **Chime TTS** HACS integration (`derekcentrico/chime_tts` fork). Chime TTS prepends a configurable chime sound before the spoken message, making announcements less jarring and easier to recognize as home automation alerts rather than random audio playback.

The pre-move apartment configured this via a `notify:` platform block in `configuration.yaml` (`notify.reminder_kitchen`, `notify.reminder_master_bedroom`), requiring a full HA restart to add or change a room. The new-house rebuild calls `chime_tts.say` directly from `script.household_tts_announce` instead — the fork's `notify.py` is a thin wrapper around the same service, so nothing is lost, and the whole delivery mechanism now lives in one MCP-retrievable script instead of `configuration.yaml` plus a script. Enabling Chime TTS itself is a config entry (**Settings → Devices & Services → Add Integration → Chime TTS**), not YAML — no restart required, confirmed live in this instance.

```yaml
action: chime_tts.say
target:
  entity_id: media_player.kitchen_homepod
data:
  message: "Your message here."
  chime_path: soft
  tts_platform: cloud
  volume_level: 0.65
  announce: true
```

Templates work inside `message`. Do not call `chime_tts.say` (or `media_player.play_media`) directly from automations — call `script.household_tts_announce`, which applies the video-call suppression and per-room volume. See `guides/chime_tts.md`.

### ThinQ `current_status` sensor sits in `end` for only ~30–45 seconds

`sensor.<appliance>_current_status` (via `lg_thinq`) transitions `... → end → power_off`, but measured across three real cycles the `end` state lasted only 31–44 seconds before moving on. A state trigger on `to: end` alone is a narrow target — an HA restart or a momentarily missed state-change event during that window loses the transition entirely. Pair it with a second, independent signal (in this instance, the appliance's `event.*_notification` entity, whose `event_type` attribute carries the same information) rather than relying on the state trigger alone. See `guides/laundry_automation.md` for the full pattern, including the recency guard the event-trigger path needs (below).

### `event` entities re-fire their trigger on every HA restart, with a stale value

An `event` entity's `state` is the ISO timestamp of the last real event it saw. On HA restart, that value is restored — but the restore itself is a `state_changed` event (from `None` to the restored value), which fires any `state` trigger with no `to`/`from` filter, exactly as if a new event had just happened. A trigger built naively on such an entity will re-fire on every restart with the last event it ever saw, however old.

Guard against this with a recency check comparing the entity's own state (parsed as a datetime) to `now()`:

```yaml
condition: template
value_template: >-
  {{ (now() - (states('event.utility_room_washer_notification') |
  as_datetime)).total_seconds() < 300 }}
```

This is a case where the template condition shorthand is the right tool — there's no native condition primitive for "this event's own timestamp value is recent." Caught live in this house: the Aug 22 `washing_is_complete` event re-surfaced with a fresh `last_changed` after an unrelated HA restart on Aug 26, which would have fired a four-day-stale laundry alert without the guard.

### Sonos TTS via Chime TTS: state polling works, playback silently doesn't (unresolved)

On this instance, `chime_tts.say` targeting a Sonos entity (`media_player.family_room_theater`) produces no observable effect — no state change, no error at any HA log level (including `debug`), across repeated tests. HA's control channel to the speaker is confirmed healthy (state polling correctly reports `idle`; the physical speaker is powered on and idle in the Sonos app). Debug logging on `custom_components.chime_tts` shows the integration correctly detects the Sonos platform, builds the Sonos-specific public playback URL (as opposed to the generic `media-source://` URL used for HomePod/AirPlay), calls `media_player.play_media` with `announce: true` — then explicitly polls for the entity to report `playing` and times out after the full audio duration without it ever doing so.

Ruled out: HA's `internal_url` being unset (it was fixed mid-session; no change in behavior). Likely candidate, unconfirmed: the Nabu Casa cloud remote-UI URL Chime TTS builds for Sonos playback isn't reachable or playable by the physical speaker (network segmentation between the Sonos and Nabu Casa's proxy, or a Nabu Casa-side quirk specific to that content type) — HomePod/AirPlay doesn't share this dependency since it streams through HA's own process rather than handing the speaker a URL to fetch.

`script.household_tts_announce` does **not** target this Sonos — a `target: family_room` branch was built and tested (this entry documents that testing), then removed once it became clear the actual requirement was simpler: push a notification when the Sonos is busy, not route TTS to it. `guides/laundry_automation.md` implements that directly with a `state` condition on `media_player.family_room_theater`, no Chime TTS involvement. This entry stays as a record of the underlying Chime TTS + Sonos limitation, in case a future automation wants Sonos TTS specifically and needs to know this was already tried.

---

## Sensors & Calibration

### Percentual offset calibration cannot eliminate a fixed sensor floor

Some Zigbee sensors report a non-zero floor value even when the measured quantity is zero (e.g., a power meter reading 0.5W with nothing plugged in). Percentual offset calibration in Z2M can scale readings but cannot subtract a constant.

To eliminate a floor:

- Use an **absolute offset** via a `template` sensor that subtracts the floor value
- Or adjust the **threshold** in any binary logic that consumes the sensor (e.g., "consider it 'on' above 5W instead of above 0W")

### `| int` truncates negative floats to zero — use `| float` for threshold comparisons

Jinja2's `| int` filter calls Python's `int()`, which truncates toward zero. A sensor value of `-0.97` becomes `0`, so `{{ value | int < 0 }}` evaluates to `False` even though the value is genuinely negative. This silently masks an overdue condition in any template that compares a float sensor against zero.

Use `| float` instead of `| int` whenever the comparison involves values between -1 and 0:

```jinja2
{# Wrong — int(-0.97) = 0, so 0 < 0 is False even when sensor is overdue #}
{{ states('sensor.roborock_q8_max_sensor_time_left') | int < 0 }}

{# Right — float(-0.97) = -0.97, so -0.97 < 0 is True #}
{{ states('sensor.roborock_q8_max_sensor_time_left') | float < 0 }}
```

This affected all four Roborock maintenance template sensors (`binary_sensor.roborock_clean_sensor`, `binary_sensor.roborock_replace_filter`, `binary_sensor.roborock_replace_main_brush`, `binary_sensor.roborock_replace_side_brush`): the underlying `_time_left` sensors report hours as floats, and the first hour of overdue time is between -1 and 0, which `| int` rounds to 0 and silently drops.

### Sensor-derived state values need debouncing for fast-changing inputs

Binary sensors derived from analog values (power above threshold = device on) can chatter rapidly when the input hovers near the threshold. Use `for:` durations on triggers consuming these, or wrap the binary logic in a template sensor with hysteresis.

---

## Vacuum & Roborock

### A commanded dock always cancels the active cleaning job — pause-then-resume is not possible

On the Roborock Q8 Max Plus (via the official HA Roborock integration), any manually issued dock command ends the current cleaning job, regardless of how the job was started or whether it was paused first. This was confirmed with three separate live tests on 2026-08-25:

| Test | Result |
|---|---|
| Whole-house clean → `vacuum.pause` → `vacuum.return_to_base` | `binary_sensor.*_cleaning` → off, progress reset to 0 |
| Whole-house clean → `vacuum.return_to_base` (no pause first) | Same — job cancelled |
| Segment clean → `vacuum.pause` → `vacuum.return_to_base` | Same — job cancelled |

This matches Roborock's own documentation: "placing a paused robot on the dock manually will end the current cleanup." The only thing that preserves an in-progress job is the robot's *autonomous* low-battery return-and-resume — which cannot be triggered or replicated via HA service calls. Design around this rather than fighting it: see `guides/vacuum_cleaning_routine.md` for the fixed-zone approach this instance uses instead of resume.

### `binary_sensor.<vacuum>_cleaning` reflects Roborock's `status.in_cleaning`, and survives autonomous recharge

The Roborock integration's `binary_sensor.*_cleaning` (device class `running`) is `on` for the entire duration of an in-progress job, including while the robot is docked and charging mid-job due to low battery — it only turns `off` when the job is actually cancelled or completed. Confirmed via history: the sensor stayed `on` continuously through a 3h15m autonomous dock-and-recharge cycle, with the robot resuming cleaning on its own once charged. Use this sensor, not the vacuum's `state`, to answer "is there an unfinished job right now."

### `vacuum.start` sends a dock command instead of starting when the robot is returning home

From the integration's `async_start()`: if `status.in_returning == 1` (robot is en route to the dock), `vacuum.start` translates to `APP_CHARGE`, not a resume or new-clean command. Calling `vacuum.start` while `sensor.<vacuum>_status` reads `returning_home` silently does the opposite of what's intended. Wait for the robot to actually reach `charging` status first.

### Cleaning progress is relative to job size, not house size, and is non-monotonic

`sensor.<vacuum>_cleaning_progress` resets to 0 at the start of every new job and climbs toward 100 as *that job's* commanded area is covered — a 5-room segment clean reads 100% at full coverage of those 5 rooms, identical to how a full-house clean reads 100% at full-house coverage. Never compare progress values across differently-scoped jobs (e.g., a "day zone" job vs. a "night zone" job) without an explicit discriminator recording which job produced the reading — `input_select.vacuum_active_zone` in this instance's automations.

Progress also dips slightly rather than climbing strictly monotonically (observed: 35→34→30→29, 79→78→79 in the same run). A `numeric_state: above` threshold tolerates this; a `state: to: "100"` trigger does not.

### `sensor.<vacuum>_current_room` cannot be used to infer "this room is finished"

For a house with open-plan adjacent rooms, `current_room` flips back and forth between the two rooms every 30 seconds to a couple of minutes as the robot works the shared boundary, rather than settling on one room, finishing it, and moving to the next. A rule like "mark the room the robot just left as done" produces false completions almost immediately. There is no per-room completion signal exposed by the integration — only whole-job progress. If per-room granularity is needed, it has to come from a fixed, hand-defined zone (a specific list of vendor room IDs sent to `app_segment_clean`), not from watching robot position.

### `app_segment_clean`'s segment order does not determine cleaning route

Confirmed via a real automation trace on 2026-08-26: a job commanded as `segments: [16,17,19,21,23,24]` was actually visited in the order 19 → 21 → 17 → 16 (with 23 and 24 skipped — closed doors, see below). The robot path-plans from its own current position rather than walking the array in order. No need to sort or "logicalize" a segment list for routing purposes — it has no effect.

### `sensor.<vacuum>_current_room`'s `options` enum is fixed at integration setup and can't represent renamed/newly-recognized rooms

The entity's `options` attribute (a fixed enum list) only contains the room names known when the integration last built its room list. Renaming a room in the Roborock app (or Roborock recognizing a previously-generic "Room" as a new named room) doesn't retroactively add it to this list — confirmed by sending the robot to segment 20 (renamed "Master Closet" in-app) and watching `current_room` hold on "Living room" the entire time, unable to report a state outside its enum. `roborock.get_maps` also did not surface the app-side rename. Don't trust this sensor (or `get_maps`' room-name dict) to confirm a room rename or split took effect — verify with a direct segment-clean test and visual confirmation instead.

### Closed doors cap achievable progress by single-digit percentages per small room, not proportionally to room count

A real daytime run (2026-08-26) that skipped 2 of 6 commanded rooms (Utility Room + Pantry, both door-closed) still reached 91% cleaning progress — confirming progress is area-weighted, not room-count-weighted. Small rooms (closets, utility rooms) missing to a closed door cost only a few percentage points each, not `1/room_count`. Relevant when setting a "zone cleaned today" threshold: don't assume N inaccessible rooms out of M total caps progress at `(M-N)/M`.

### Merging/renaming rooms in the app: `get_maps` can lag reality by hours, and a merge retires one ID rather than aliasing it

When two rooms are merged in the Roborock app (tested 2026-08-26, Kitchen + Dining room), the merge lands on one of the two original segment IDs and the other is retired outright — not kept as a working alias. `roborock.get_maps`' cached room-name dict took hours to catch up, and returned a stale, self-consistent-looking picture the whole time (both old rooms still listed separately, both looking plausible) rather than erroring or flagging staleness. A `get_maps` snapshot taken mid-lag is not trustworthy for deciding which ID survived.

The reliable check is functional, not observational: send `app_segment_clean` targeting a candidate ID and watch `vacuum.<x>` state. A live ID flips to `cleaning` within seconds; a retired one silently no-ops (no error, no state change) — same signature as any other dead segment ID. Confirm this immediately before editing an automation's segment list, and re-confirm if significant time passed since the last check, since the answer can change again as the sync continues to converge (a "27 still works" result checked once may not hold an hour later).

---

## Zigbee & Lighting Groups

### Z2M reports `light.turn_off transition` state optimistically — breaks `wait_for_trigger`

When `light.turn_off` is called with a `transition` value on a Z2M/MQTT light, Z2M immediately publishes `state: OFF` to MQTT even though the bulb is physically still fading. HA sees the state change and any `wait_for_trigger` watching for the light to go `off` fires instantly — well before the transition completes. Downstream actions (e.g. enabling AL sleep mode) then run while the bulb is still physically on.

Additionally, some Zigbee bulbs (including Hue bulbs on Z2M) ignore `transition` on `turn_off` entirely at the hardware level, turning off immediately rather than fading.

**Reliable fade-to-off pattern:**

```yaml
# 1. Dim to near-zero using "move to level" — reliably supported and not optimistically reported
- action: light.turn_on
  target:
    entity_id: light.avery_room_ceiling
  data:
    brightness_pct: 1
    transition: 44

# 2. Fixed delay — immune to Z2M state reporting; waits for the physical transition
- delay:
    seconds: 47

# 3. Instant off at 1% — imperceptible; no transition means no optimistic reporting problem
- action: light.turn_off
  target:
    entity_id: light.avery_room_ceiling
```

Never use `wait_for_trigger` (watching for a Z2M light to go `off`) as a proxy for a transition completing — the trigger fires on the reported state, not the physical state.

### Prefer HA Light Groups over Zigbee groups for small fixtures

For fixtures with 2–4 bulbs, **HA Light Groups** are simpler and more reliable than Zigbee-level groups:

- Simpler management — defined in YAML or UI, no controller-level config
- Per-bulb state feedback — HA tracks each bulb individually
- No conflict with Adaptive Lighting's `manual_control` detection

Reserve Zigbee groups for large installations (12+ bulbs) where the network-level efficiency matters.

### Reset devices before re-pairing to a new Zigbee network

When migrating a device from one Zigbee network to another (ZHA → Z2M, Z2M → Hue), reset the device to factory state first. Devices retain coordinator association in non-volatile memory and may fail to pair or pair partially if not reset.

### Hue-branded devices belong on the Hue bridge; everything else on Z2M

Hue bulbs and accessories work most reliably on the Hue bridge — they get firmware updates, entertainment sync, and the Hue app's native scene management. Non-Hue Zigbee devices live on Z2M, which has better diagnostic visibility and broader device support.

The clean separation (Hue on channel 20, Z2M on channel 11) prevents interference and keeps each network simpler.

---

## Presence & Device Trackers

### Template `device_tracker`'s `in_zones` requires full zone entity_id, not the bare slug — fails silently

The Template Helper `device_tracker` platform's `in_zones` field must be a list of zone **entity_ids** (`zone.home`), not bare zone slugs (`home`). A bare slug is not rejected anywhere — not by config validation, not in logs, and `ha_eval_template` will happily render `{{ ['home'] }}` without complaint since it has no zone-matching semantics to enforce. The only symptom is that the tracker's `in_zones` attribute stays `[]` and its state stays `not_home` forever, regardless of the input the template depends on.

This looked exactly like a startup race condition during initial testing (tracker didn't reflect its source `input_boolean` immediately after a reload, or after a full HA restart) until the zone identifier format was corrected — after which both live toggles and cold-boot restores worked immediately. If a template `device_tracker` won't budge from `not_home`, check the `in_zones` value uses the full `zone.<slug>` form before suspecting a timing issue.

### Zone occupant counts (`zone.<name>` state) come from `person` entities only, not raw `device_tracker` entities

A `device_tracker` in a zone does not, by itself, increment that zone's occupant count — only `person` entities do (the zone's `persons` attribute is the authoritative source). A tracking-only presence source (e.g. a guest) needs its own `person` entity wrapping the `device_tracker`, even with no linked HA user account, or it's invisible to any automation/dashboard that reads zone counts. See `guides/presence_tracking.md`.

### `is_state('calendar.<x>', 'on')` only detects *any* active event — useless for a calendar with back-to-back blocks

A calendar entity's state is `on` whenever *some* event is currently active; it says nothing about *which* event. This is a trap for custody/shared-schedule calendars that are, by design, always covered by one block or another (e.g. `calendar.avery` alternates "Avery @ Nate's" and "Avery @ Cheryl's" all-day blocks with no gaps). A template like `{{ is_state('calendar.avery', 'on') }}` intended to mean "Avery is home today" is permanently stuck `on`, because there's always an event — it can never observe the one case (a gap) it was written to detect.

Caught 2026-08-29: `binary_sensor.avery_home_today` used exactly this pattern and had been unconditionally `on` since at least 2026-08-26, silently blocking `automation.household_vacuum_start_cleaning`'s adults-only evening branch (gated on this sensor being `off`) every single night regardless of where Avery actually was.

**Fix:** inspect the active event's summary/message, not just whether the calendar is occupied:

```jinja2
{# Wrong — always on for a calendar with continuous coverage #}
{{ is_state('calendar.avery', 'on') }}

{# Right — checks which event is active #}
{{ is_state('calendar.avery', 'on') and state_attr('calendar.avery', 'message') == "Avery @ Nate's" }}
```

This is a template-helper gotcha, not an automation-YAML one — it will not surface as a load-time or trace error. The automation traces cleanly every time; the condition just never evaluates the way its name implies. If a presence-style binary sensor derived from a calendar has held one value for suspiciously long, check whether the calendar has continuous coverage before assuming the sensor is fine.

---

## Matter & HomeKit

### Use Matter Hub (RiDDiX fork) as the sole bridge

Multiple Matter/HomeKit bridges fighting over the same devices produces unreliable state and duplicated entities in HomeKit. Standardize on Matter Hub and disable other bridges.

### Some integrations need HACS replacements for proper entity types

The default Xiaomi integration exposes pedestal fans as switches, not fans, which breaks HomeKit fan controls (oscillate, speed). The `hass-xiaomi-miot` HACS integration exposes proper `fan` entities. When a device's primary entity type seems wrong, check HACS for a better integration before working around it.

### HA's Matter light integration drops `transition` on `light.turn_off`

`matter` light `async_turn_off()` sends a bare `OnOff.Off()` command with no transition parameter — the `transition:` value passed to `light.turn_off` is silently ignored (HA `dev` as of Aug 2026; tracked open as [core #160066](https://github.com/home-assistant/core/issues/160066)). The device then applies whatever its own configured off-ramp is. `light.turn_on` *does* pass transition through, as `MoveToLevelWithOnOff` with `transitionTime` in 0.1 s units.

This is a different failure mode from the Z2M one under "Zigbee & Lighting Groups" (Z2M *does* send the transition but reports `OFF` optimistically). Same fix, though: fade-to-off must be a `light.turn_on` ramp to minimum, a fixed `delay`, then a plain `light.turn_off` to cut the residual. `automation.averys_room_sleep_mode` uses this pattern for the Inovelli canopy light.

### Inovelli White Series LightFan canopy (Matter/Thread) — transition behavior

Live-tested 2026-08-30 on `light.averys_room_ceiling_fan_light` (model "White Series LightFan Module", fw 1.0.1r1):

- **`light.turn_on` + `transition` is honored precisely.** A commanded 20 s fade produced a clean linear ramp (13→78→142→207→255) hitting the target at exactly 20 s, with intermediate `brightness` reports about every 5 s.
- **A new command overrides an in-progress fade.** `brightness_pct: 100, transition: 0` sent mid-fade snapped straight to 255.
- **The configured 13% min-level does NOT clamp a hub `MoveToLevel`.** Ramping toward `brightness_pct: 1` went all the way to `brightness` 3 and the light stayed `on` — it did not auto-off at the bottom and did not floor at 13%. An explicit `light.turn_off` is still required to actually turn it off.
- **`light.turn_off` + `transition` gives no slow fade** — the requested duration is dropped and the module applies its own configured off-ramp instead, held in the `Off transition time` / `On/Off transition time` Level Control number entities. Factory default is 2.5 s; both canopies are now set to `0.5` s (see `guides/inovelli_fan_canopy.md` Step 2). This is the HA-side limitation above, not the device.

### Inovelli White Series VTM30-SN — the outgoing binding is coupled to local paddle→load control

On the White series switch, the paddle → light Matter binding fires *because* the paddle press acts on the switch's local load relay. Anything that takes the paddle off the load also stops the binding:

- **`Control of switch load` = `Remote control only`** (`select.*_ceiling_fan_switch_control_of_switch_load`) — set to stop the phantom `switch.*_ceiling_fan_switch_load_control` entity toggling on every paddle press. It also silently kills the paddle → light binding. Reverting to `Remote & paddle control` restores it.
- **Smart Bulb Mode enabled is fine** — SBM keeps the load powered and the paddle still "controls" the (bypassed) relay, so the binding keeps working. It's specifically disabling *paddle control of the load* that breaks it.
- The phantom internal-relay toggle is therefore load-bearing, not just noise — leave `Control of switch load` at `Remote & paddle control` and hide the `switch.*_load_control` entity instead.
- Inovelli community thread confirming the coupling: <https://community.inovelli.com/t/white-dimmer-binding-and-local-control/21471>. They may decouple binding from local control in a later firmware — worth re-testing after a switch update.

### Inovelli White Series VTM30-SN — cluster 8 (Level Control) binding needs a non-Instant simulated dimming speed

A cluster 8 binding (switch Binding endpoint → canopy light endpoint 1) for paddle press-and-hold dimming emits nothing while `Dimming Speed (Simulated)` (`select.*_ceiling_fan_switch_dimming_speed_simulated`) is at `Instant` — the switch has no ramp to play out, so the hold sends no Move/Step. Set it to a duration (`3s` tested smooth on Avery's Room, `2s` slightly fast) and hold-to-dim works over the binding with HA down; releasing the paddle stops the ramp. An earlier build tested cluster 8 on canopy fw `1.0.0` and `1.0.1r1`, saw nothing, concluded it "doesn't work", and ran cluster 6 only — the real cause was the `Instant` simulated speed, not the firmware. Guide `guides/inovelli_fan_canopy.md` Steps 3–4 now cover both clusters.

---

## Shell Command Integration

### Poll for state on command-line lights that can change out-of-band

The Litra Glow integration (`guides/litra_glow.md`) started in optimistic mode, then moved to a polling `command_line` sensor as the source of truth for `state`/`level`/`temperature`. Optimistic mode looks appealing — no per-interaction latency, no flicker — but it silently diverges from reality whenever the device changes without HA's involvement: the USB cable drops, or the light is adjusted via `litra-rs` directly on the Mac. HA then reports a state that's simply wrong, with no mechanism to notice or correct it.

The polling sensor closes that gap: it's the actual source of truth, refreshed immediately after every command handler (`homeassistant.update_entity`) so the UI updates within about a second rather than waiting out the poll interval, and it naturally surfaces `unavailable`/`unknown` when the Mac or the USB device drops — which optimistic mode has no way to represent at all.

**Rule:** prefer polling over optimistic mode whenever the backing device can change state outside HA's control (manual CLI use, another controller, a flaky USB/network link). Reserve optimistic mode for commands that are the *only* way the device's state ever changes.

### Principle of least privilege for shell access

Shell command integrations that SSH into another machine should use:

- A **dedicated service account** on the remote machine, not the user's normal account
- A **scoped SSH key** with `command="..."` restrictions in `authorized_keys` if the command set is fixed
- **Sudoers whitelisting** for any privileged operations, naming the exact commands allowed
- A **dispatch script** on the remote side that validates inputs rather than passing arbitrary strings to the shell

---

## HACS Integrations

### ha-chore-calendar: `pending_period` must be less than the chore's interval

Setting a `pending_period` that equals or exceeds the chore's interval causes the chore to get stuck in `completed` state after the `update_item` service call. The integration appears to update (the new `pending_period_mins` is visible in diagnostics), but the sensor state never transitions to `pending` — it stays `completed` indefinitely.

The root cause: when `pending_period >= interval`, the calculated "pending from" date (`next_due - pending_period`) falls before the `last_completed` date. The integration's state machine doesn't handle this overlap and leaves the chore in `completed`.

**Rule:** always set `pending_period < interval`. For a 14-day interval, cap pending_period at 7 days. For 30-day intervals, 21 days works well. If you need to see a chore earlier, shorten the interval instead.

### ha-chore-calendar: pending state transitions evaluate at midnight, not in real-time (integration bug)

The README documents `pending_period` as "how long before the due time the chore reads as pending" — implying real-time evaluation. The actual implementation does not honor this: the `completed → pending` transition is evaluated on a midnight tick, and the chore becomes `pending` at the first midnight where `today.date > pending_from.date` (strict greater-than, not >=).

Consequence: with `next_due = 07:00` and `pending_period_mins = 1440` (1 day), `pending_from = previous day at 07:00`. At midnight of the previous day, `today.date == pending_from.date` — the strict-greater check fails, so the chore stays `completed`. It doesn't flip to pending until midnight of the due day itself — 7 hours before pickup, not 24.

**Workaround:** size `pending_period` so that `pending_from` falls on a calendar day *before* the day you need `pending` state. For a 07:00 due time and a 19:00 evening-before notification, a 2-day period (2880 min) puts `pending_from` at 07:00 two days before pickup — `pending_from.date` is then strictly before the notification day, so the midnight check flips to pending at midnight the evening before.

### ha-chore-calendar: scheduled chores unreliable for narrow notification windows — don't use

Even with a correctly sized 2-day pending window, the trash pickup scheduled chore missed the `completed → pending` transition on two consecutive pickup cycles (sensors remained in `completed` state at the 19:00 notification window, despite `next_due` being the next day). A coordinator reload did not fix it.

The midnight tick mechanism for scheduled chores is fragile: any missed poll, coordinator hiccup, or off-by-one in the date math can silently leave a sensor stuck in `completed` indefinitely with no error surfaced.

**Rule:** don't use ha-chore-calendar scheduled chores for any automation with a narrow or time-critical notification window. Use `calendar.get_events` against an external calendar (iCloud via Remote Calendar integration) instead — it queries the authoritative schedule at notification time with no state machine dependency. ha-chore-calendar interval chores remain reliable for the 09:00-daily overdue check because the window is 24 hours wide and failure means a 1-day delay rather than a silent miss.

---

## Physical Setup

### Key light distance matters more than brightness

For reducing facial shine in video calls, **distance** is a more effective variable than brightness. The inverse square law means moving the light twice as far away reduces intensity to a quarter while keeping the same color and spectrum.

Aim for a dimmer, farther light over a brighter, closer one. The brightness floor is whatever your camera needs for good exposure.
