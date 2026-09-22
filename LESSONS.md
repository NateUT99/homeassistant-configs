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

### `condition: not` with a multi-item `conditions:` list is NOR, not "NOT of the AND"

`condition: not` passes only when **all** of its listed sub-conditions are false. It is `NOT A AND NOT B`, not `NOT (A AND B)`. Writing `condition: not, conditions: [A, B]` to mean "not (A and B are both true)" is a natural mistake — De Morgan's law says those should be equivalent, but they aren't what `not` computes here — and it fails **silently**: the automation still runs, takes the other branch every time, and nothing in the trace looks obviously wrong unless you check which sub-conditions actually got evaluated (a short-circuited `not` block shows only the first sub-condition in the trace once it hits one that's true, since one true entry already disproves "all false").

Concretely: `condition: not, conditions: [{state: fan, "on"}, {numeric_state: zone.home, above: 0}]` intended as "the fan is off, or nobody's home" is wrong twice over — but even the narrower, more common case of intending "NOT (A and B)" from `not: [A, B]` actually computes "NOT A and NOT B", a much narrower condition that's often close to unreachable in practice (both must independently fail).

**Fix:** to get `NOT (A AND B [AND C...])`, wrap the list in an explicit `condition: and` and negate that single group:

```yaml
# Wrong — this is NOT A and NOT B, not NOT(A and B)
- condition: not
  conditions:
    - condition: numeric_state
      entity_id: zone.home
      above: 0
    - condition: state
      entity_id: input_boolean.everyone_sleeping
      state: "off"

# Right — negates the AND-group as a whole
- condition: not
  conditions:
    - condition: and
      conditions:
        - condition: numeric_state
          entity_id: zone.home
          above: 0
        - condition: state
          entity_id: input_boolean.everyone_sleeping
          state: "off"
```

Discovered when the Inovelli LED-bar "flash while asleep" acknowledgement (`guides/inovelli_switches.md`) never fired in Master Bedroom or Avery's Room — every fan change while everyone was marked asleep silently fell through to the "steady state" branch instead, with no visible symptom beyond "the light didn't do the thing." A **trace with only one sub-condition of a multi-item `not` block evaluated** is the tell — that's the block short-circuiting on the first sub-condition that's true, disproving "all false" before it needs to check the rest.

### A bare `condition:` step inside a `repeat.sequence` aborts the whole loop, not just the current item

A `condition:` **action** (as opposed to a top-level automation `conditions:` block) that evaluates false stops the entire sequence it's in. Inside `repeat.for_each`, that sequence is the per-item body — so a false condition on iteration 3 of 8 silently skips iterations 4 through 8 as well, not just item 3. There is no trace error; the loop just ends early.

**Rule:** never use a bare `condition:` step to skip-and-continue inside a `repeat` body. Use `if:`/`then:` instead — a false `if` only skips its own `then:` block and the loop moves on to the next item normally.

```yaml
# Wrong — one unavailable calendar aborts every remaining item in the loop
- repeat:
    for_each: "{{ cal_items }}"
    sequence:
      - condition: template
        value_template: "{{ states(repeat.item.source) not in ['unavailable', 'unknown'] }}"
      - action: calendar.get_events
        ...

# Right — a skip only skips this one item
- repeat:
    for_each: "{{ cal_items }}"
    sequence:
      - if:
          - condition: template
            value_template: "{{ states(repeat.item.source) not in ['unavailable', 'unknown'] }}"
        then:
          - action: calendar.get_events
            ...
```

Found while designing `automation.household_trash_pickup` (`guides/reminders.md`), which loops over calendar-driven to-do items and must not let one dead calendar entity take down the rest of the sync.

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

A save-current-state / do-something / put-it-back pattern where the "do something" script is `mode: restart` must take the `scene.create` snapshot in the **caller**, not inside the script, and guard it on the script being idle. Otherwise a rapid second run (the restart) snapshots the script's own in-progress output as the "resting" state, and the restore afterward reapplies that instead of the real prior state.

Fix, if this pattern is used again: take the snapshot in the caller before dispatching to the `mode: restart` script, wrapped in `if: condition: state, entity_id: script.<the script>, state: "off"` so a burst snapshots once (idle) and every subsequent restart within the burst reuses that first scene. The caller being `mode: queued` keeps its own runs serialised so the guard can't race itself.

Related gotcha for the restore side: test scene existence with `states.scene.<id> is not none`, **not** `states('scene.<id>')` or `has_value(...)` — a freshly `scene.create`d scene reads `unknown` until it is first activated, so the value-based checks report it missing when it isn't.

(The Inovelli ceiling-fan LED bar used to be the worked example for this, but that design has since moved to a compute-don't-snapshot approach — see `guides/inovelli_switches.md` — so no live automation in this repo currently exercises this pattern. Kept here as a general lesson for the next time a snapshot/restore is genuinely the right shape.)

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

### ThinQ's generic notification event lands before the typed error event with the actual fault code

`event.<appliance>_notification` (`event_type`: `error_during_washing` / `drying_failed`) and `event.<appliance>_error` (`event_type`: the specific fault, e.g. `unable_to_lock_error`) both fire when a cycle aborts, but not simultaneously — measured live, the generic notification event lands roughly 0.5 seconds *before* the typed error event. An automation that composes a fault message the instant either trigger fires risks reading the typed event's `event_type` attribute before it's set, since the two are independent event entities with no ordering guarantee beyond "generic first, typed second, both within about a second."

The fix is a short settle delay (`laundry_automation.md`'s announcement automation uses 5 seconds) before composing any message that depends on the typed event's attribute, gated so it only applies when a fault is actually present — a plain cycle completion has no such race and needs no delay.

### `event` entities re-fire their trigger on every HA restart or integration reload, with a stale value

An `event` entity's `state` is the ISO timestamp of the last real event it saw. On HA restart, that value is restored — but the restore itself is a `state_changed` event (from `None` to the restored value), which fires any `state` trigger with no `to`/`from` filter, exactly as if a new event had just happened. A trigger built naively on such an entity will re-fire on every restart with the last event it ever saw, however old.

The same replay happens on an **integration reload or transport reconnect**, not just a full HA restart. A Matter Server disconnect (`matter_server.client.exceptions.InvalidState: Not connected`) took every entity on the three Inovelli LightFan switches `unavailable` and then restored them; the `event.*_switch_button_*` entities came back at their last-held timestamp, `from: unavailable` (not `None`), replaying a ~1h-old config-button single-tap that turned the Avery's Room fan on via `automation.averys_room_ceiling_fan_wall_control`. Crucially, `not_to: [unavailable, unknown]` does **not** catch this — the destination is a valid timestamp. The transition is `unavailable → <timestamp>`, so the guard that works is **`not_from: [unavailable, unknown]`** (add it alongside the existing `not_to`). All five triggers on the three `*_ceiling_fan_wall_control` automations now carry both.

Use `not_from` when the intent is simply "ignore restore transitions." Use the recency check below instead (or as well) when a genuine-but-delayed event must also be rejected — `not_from` can't tell a fresh event from a stale one, only a restore from a non-restore.

Guard against a stale value with a recency check comparing the entity's own state (parsed as a datetime) to `now()`:

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

### `sensor.<vacuum>_last_clean_begin` updates at job *end*, not job *start* — unusable as a running-job elapsed timer

Confirmed via a real run on 2026-09-15: the vacuum entered `cleaning` at 11:37 local, but
`sensor.<vacuum>_last_clean_begin` still held the *previous* day's clean's begin timestamp until
12:28 local, when the job finished and the sensor jumped straight from yesterday's value to
today's — both `last_clean_begin` and `last_clean_end` update together, at completion, as a
matched pair describing the job that just finished. There is no sensor that reports a job's
start time while that job is still running.

A Live Activity chronometer built on `last_clean_begin` as a count-up "elapsed time" therefore
computes elapsed time against whatever job last completed, not the one in progress — in this
case it read ~24 hours elapsed a few minutes into a new run, because the sensor was still
holding the prior day's timestamp. If a running job's elapsed time is needed, capture `now()`
into a purpose-built helper at the moment the job starts (e.g. an `input_datetime`, following
the pattern `guides/laundry_automation.md` uses for its own cycle-start capture) — don't trust
any Roborock-exposed timestamp sensor to reflect the in-progress job.

### `vacuum.<x>` re-enters `docked` after already being docked — don't gate a "just finished" action on "currently docked, recently"

Confirmed via real history on 2026-09-15: the vacuum genuinely completed a job and docked at
12:29, then showed a *second*, independent transition into `docked` (a real `last_changed`
update, not just an attribute tick) at 13:23 — 54 minutes later, with no new job commanded. The
likely cause is the dock's own smart auto-empty cycle (`select.<vacuum>_dock_empty_mode`) or a
similar self-service action that briefly moves the vacuum's reported state away from `docked`
and back.

An automation gating a one-time "job just finished" action on `condition: state, state: docked,
for: {minutes: N}` being *false* (i.e. "docked, but not for very long") will fire again on this
second transition, indistinguishable from a real job ending. In this instance it recreated an
already-dismissed iOS Live Activity, making a card the user had dismissed reappear with no
apparent trigger (see `guides/live_activities.md`). Use a dedicated edge trigger instead —
`trigger: state, from: [<active states>], to: docked` plus `condition: trigger, id: [...]` — so
the action only fires on a transition *out of* an active state, not on any re-entry into the
terminal one. A duration-based `for:` condition is still fine for the inverse case (clearing
something once a state has held long enough), since resending a clear/no-op action on a spurious
re-dock has no visible side effect — the risk is specific to actions that create or recreate
something.

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

### Q8 Max Plus has no mop lift and no dock wash/dry — rug protection is drawn zones, not a setting

The Roborock Q8 Max Plus (RockDock Plus) has no mopping features beyond a hand-fitted pad on a manual 350 ml water tank. Confirmed against Roborock's own docs:

- **No mop lift.** Ultrasonic carpet recognition — the app's "Rise" / "Avoid" carpet-mopping behavior — ships only on the S7 / S7 MaxV / S7 Max Ultra / S8 / S8+ / S8 Pro Ultra / Q Revo lines. The Q8 Max is not among them. Marking an area as *carpet* on the map only enables **Carpet Boost (suction)** — it does **not** stop the pad wetting the carpet. A wet pad drags straight across any rug the robot can reach.
- **The only rug protection is a no-mop zone** drawn over each rug in the app, sized a few inches larger than the rug on every side (the pad trails the wheels and LiDAR position drifts between runs). With the pad attached the robot will not enter a no-mop zone at all, so the rug is skipped that run — there is no "mop around it" middle ground on this model.
- **The dock is auto-empty dust only** (2.5 L E12 bag). No mop washing, no drying, no clean/dirty water tanks. So "mopping disabled to avoid a loud dock wash" is not a real constraint on this unit — the reason ordinary nights don't mop is simply that the pad and tank are fitted by hand.
- **Dust bin and water tank are one combined 2-in-1 module.** There is no dedicated "dust bin installed" sensor; `binary_sensor.<vacuum>_water_box_attached` is the signal that the rear cavity is occupied, and it has been solidly `on` through 10+ days of vacuum-only runs (the module stays seated; only the mop cloth plate, `binary_sensor.<vacuum>_mop_attached`, gets clipped on for mopping).

See `guides/vacuum_cleaning_routine.md` → *Weekly Mop Pass* for how the routine is built around these constraints.

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

### `input_boolean` restores its own state across HA restarts — retained-message persistence layers solve a non-problem

`input_boolean` implements HA's `RestoreEntity` and restores its last state on every restart with no configuration (as long as `initial:` is left unset — setting `initial:` disables restore). A Template Helper `device_tracker` re-evaluates its `in_zones` template from current entity states the moment it loads, so on restart it reads the already-restored `input_boolean` directly.

A presence design does **not** need MQTT retained-message topics, MQTT auto-discovery, a Mosquitto broker, or a startup recovery automation to survive restarts — that whole apparatus exists to persist state that HA already persists natively. Verified empirically: a full HA restart with `guest_mode` left `on` had both the template trackers and the guest `person` entity come back correct. If a presence chain is built on retained messages "so state survives a reboot," that's the tell it's over-engineered.

### Zone occupant counts (`zone.<name>` state) come from `person` entities only, not raw `device_tracker` entities

A `device_tracker` in a zone does not, by itself, increment that zone's occupant count — only `person` entities do (the zone's `persons` attribute is the authoritative source). A tracking-only presence source (e.g. a guest) needs its own `person` entity wrapping the `device_tracker`, even with no linked HA user account, or it's invisible to any automation/dashboard that reads zone counts. See `guides/presence_tracking.md`.

### `is_state('calendar.<x>', 'on')` only detects *any* active event — useless for a calendar with back-to-back blocks

A calendar entity's state is `on` whenever *some* event is currently active; it says nothing about *which* event. This is a trap for custody/shared-schedule calendars that are, by design, always covered by one block or another (e.g. `calendar.avery` alternates "Avery @ Nate's" and "Avery @ Cheryl's" all-day blocks with no gaps). A template like `{{ is_state('calendar.avery', 'on') }}` intended to mean "Avery is home today" is permanently stuck `on`, because there's always an event — it can never observe the one case (a gap) it was written to detect.

Caught 2026-08-29: `binary_sensor.avery_home_today` used exactly this pattern and had been unconditionally `on` since at least 2026-08-26, silently blocking the adults-only evening vacuum clean (gated on this sensor being `off`) every single night regardless of where Avery actually was. That branch was then `automation.household_vacuum_start_cleaning`'s evening arm; it is now the standalone `automation.household_vacuum_evening_cleaning`.

**Fix:** inspect the active event's summary/message, not just whether the calendar is occupied:

```jinja2
{# Wrong — always on for a calendar with continuous coverage #}
{{ is_state('calendar.avery', 'on') }}

{# Right — checks which event is active #}
{{ is_state('calendar.avery', 'on') and state_attr('calendar.avery', 'message') == "Avery @ Nate's" }}
```

This is a template-helper gotcha, not an automation-YAML one — it will not surface as a load-time or trace error. The automation traces cleanly every time; the condition just never evaluates the way its name implies. If a presence-style binary sensor derived from a calendar has held one value for suspiciously long, check whether the calendar has continuous coverage before assuming the sensor is fine.

### All-day calendar events flip their derived sensor at `00:00:00` — a trap for anything that can run past midnight

`binary_sensor.avery_home_today` (see the entry above) is built from an all-day `calendar.avery` event, and all-day events in HA are `date`-scoped, not `dateTime`-scoped. That means the sensor's underlying event boundary — and therefore the sensor itself — transitions at exactly midnight local time, confirmed in history to the millisecond (`2026-09-09T00:00:00.004`, `2026-09-14T00:00:00.004`).

Any automation whose trigger can fire after midnight but is reasoning about "today" in the sense of "the day that already started" (a bedtime routine, an overnight process) will read the *wrong* day's value if it reads the sensor live. `automation.household_vacuum_evening_cleaning` fires roughly an hour after bedtime and landed after midnight on 3 of its last 5 runs — enough for the sensor to have already rolled over to tomorrow's answer while the run still belongs to tonight.

**Fix:** don't read the raw sensor from an automation that can run past midnight. Latch the value earlier in the evening, before the date can roll over, into a plain `input_boolean`, and have the late-running automation read the latch instead of the live sensor. `automation.household_vacuum_mop_pad_reminders` re-snapshots `input_boolean.vacuum_avery_home_tonight` from the live sensor on every 30-minute tick between 19:55 and 23:59 — recurring rather than a single fixed-time trigger, so it self-heals if an HA restart lands on any one tick — and stops re-snapshotting once that window closes, so the value holds steady through the night. See `guides/vacuum_cleaning_routine.md`.

This generalizes beyond this one sensor: any `date`-scoped calendar-derived value is a midnight trap for whatever consumes it after midnight, not just this household's custody schedule.

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
- **`light.turn_off` + `transition` gives no slow fade** — the requested duration is dropped and the module applies its own configured off-ramp instead, held in the `Off transition time` / `On/Off transition time` Level Control number entities. Factory default is 2.5 s; both canopies are now set to `0.5` s (see `guides/inovelli_switches.md` Step 2). This is the HA-side limitation above, not the device.

### Inovelli White Series VTM30-SN — the outgoing binding is coupled to local paddle→load control

On the White series switch, the paddle → light Matter binding fires *because* the paddle press acts on the switch's local load relay. Anything that takes the paddle off the load also stops the binding:

- **`Control of switch load` = `Remote control only`** (`select.*_ceiling_fan_switch_control_of_switch_load`) — set to stop the phantom `switch.*_ceiling_fan_switch_load_control` entity toggling on every paddle press. It also silently kills the paddle → light binding. Reverting to `Remote & paddle control` restores it.
- **Smart Bulb Mode enabled is fine** — SBM keeps the load powered and the paddle still "controls" the (bypassed) relay, so the binding keeps working. It's specifically disabling *paddle control of the load* that breaks it.
- The phantom internal-relay toggle is therefore load-bearing, not just noise — leave `Control of switch load` at `Remote & paddle control` and hide the `switch.*_load_control` entity instead.
- Inovelli community thread confirming the coupling: <https://community.inovelli.com/t/white-dimmer-binding-and-local-control/21471>. They may decouple binding from local control in a later firmware — worth re-testing after a switch update.

### Inovelli White Series VTM30-SN — cluster 8 (Level Control) binding needs a non-Instant simulated dimming speed

A cluster 8 binding (switch Binding endpoint → canopy light endpoint 1) for paddle press-and-hold dimming emits nothing while `Dimming Speed (Simulated)` (`select.*_ceiling_fan_switch_dimming_speed_simulated`) is at `Instant` — the switch has no ramp to play out, so the hold sends no Move/Step. Set it to a duration and hold-to-dim works over the binding with HA down; releasing the paddle stops the ramp. An earlier build tested cluster 8 on canopy fw `1.0.0` and `1.0.1r1`, saw nothing, concluded it "doesn't work", and ran cluster 6 only — the real cause was the `Instant` simulated speed, not the firmware.

**`3s` is not a safe value.** It was run first and intermittently regressed to the `Instant` behaviour — the bind stopping mid-hold and sending no Move/Step, unpredictably. `2s` is reliable on both switches; `500ms`–`1s` ramp too fast to land a level. Both rooms run `2s`. If hold-to-dim goes flaky after a firmware update, re-check this select before assuming the binding broke.

**Whole-room off/on is a paddle double-tap, not a hold** (September 2026) — the cluster 8 hold-to-dim binding was briefly removed to free the hold gesture for whole-room off/on, then restored once it was clear `multi_press_2` fires on the paddle (Button Delay already `300ms` for the config button). Hold = dim (binding); double-tap = whole-room (automation). Guide `guides/inovelli_switches.md` Steps 4 and 6.

### A Thread binding is not immune to a border-router restart, despite mesh redundancy

Updating the OpenThread Border Router core add-on (2026-09-14, ~16:56 ET) was followed roughly 53 minutes later by Supervisor stopping and restarting the Matter Server add-on container (17:49:32–17:49:38 ET). In that window, every Inovelli switch/LightFan-module pair in Office, Master Bedroom, and Avery's Room went `unavailable` simultaneously for ~85 seconds, and — confirmed by direct testing, not just inference — **a plain single paddle tap (light on/off, the cluster-6 Matter binding) did not respond**, alongside the cluster-8 hold-to-dim binding and every automation-driven fan control. This is on a fabric with 7 Thread border routers (6 Apple HomePods + this OTBR add-on).

The expectation going in was that Matter bindings run peer-to-peer over the mesh and don't need a controller, and that 7 border routers should mean no single one restarting takes anything down. Both are true in general and neither saved this: a binding still depends on the two specific devices holding a live route to each other, and a device's actual connectivity runs through whichever router is currently its *parent* — not "the mesh" as an abstraction. Multiple border routers give the network redundancy to reconverge around a lost router; they don't prevent the devices parented to that specific router from dropping out and needing to re-attach first. If a device's best real RF path happens to be the router that just restarted, it goes down regardless of how many other routers exist elsewhere in the house.

Confirmed via: `fan.*`/`light.*` entities across all three rooms transitioning to `unavailable` in the exact window bracketed by the supervisor-logged Matter Server container restart; automation traces recording `matter_server.client.exceptions.InvalidState: Not connected` for every in-flight service call during that window; and direct confirmation that the cluster-6 binding itself (no automation involved) failed to respond to a physical paddle tap.

Not yet confirmed: whether the affected devices' Thread parent was specifically this OTBR add-on (vs. some other mesh-reconvergence side effect of the update). `sensor.*_thread_routing_role` was disabled by default on all six switch/LightFan-module entities and has been enabled for future troubleshooting — a device sitting at `end_device` (Avery's Room's LightFan module, unlike Office's and Master Bedroom's `routing_end_device`) has no relay capability of its own and is the most exposed of the three if this recurs.

### Each Inovelli VTM30-SN + LightFan-module pair is two independent Thread nodes, and self-healing doesn't fix a merely-congested link

Each "switch" in `guides/inovelli_switches.md` is actually two separate Matter/Thread devices in the registry — e.g. Master Bedroom's `Ceiling Fan Switch` (VTM30-SN paddle, its own extended MAC and its own Thread attachment) and `Ceiling Fan` (VTM36 canopy module, a different extended MAC, a different attachment) — not one device with two entities. That split matters for how each gesture actually travels:

- **Paddle single-tap** — a pure Matter binding, switch load-relay → canopy endpoint, peer-to-peer. Never touches HA (see "the outgoing binding is coupled to local paddle→load control" above).
- **Paddle double-tap, paddle hold-release, and every config-button gesture** — all round-trip through HA: the switch node reports an `event.*_switch_button_*` state change, `automation.*_ceiling_fan_wall_control` reacts, and HA issues a service call back out to the *fan-module* node. Two independent Thread hops, each potentially on a different route.

Roughly 4-5 hours after the 2026-09-14 OTBR-restart outage above (same day, ~21:34-21:39 ET, Master Bedroom), the config button showed a distinct failure signature that is **not** the same bug as the `unavailable` outage: no entity went `unavailable`, and `error_log` had no `matter_server` disconnects in that window. Instead, the first config-button tap produced no `event.*_switch_button_config` state change at all for a stretch of real time, then multiple button events (up/down/config mixed) landed within a ~250ms window — too tight to be sequential human taps. Read as a **backlog-and-flush**: presses were genuinely sent by the switch but queued somewhere on its report path to HA, then delivered all at once when that path cleared. Nothing was dropped or bounced at the device; it was delayed in transit.

Why 7 border routers (6 HomePods + this OTBR) and two of them physically adjacent to the affected room didn't prevent this: Thread self-healing is a **failure-recovery** mechanism, not a **quality-optimizing** one. A child attaches to a parent once, based on link quality *at attach time*, and does not continuously re-evaluate for a better nearby parent while the current link still minimally works — the same stickiness as a Wi-Fi client not roaming off a weak AP just because a strong one is closer. Reconvergence only triggers once a parent is actually lost (missed keepalives past a threshold); a marginal-but-not-dead link can sit degraded indefinitely. Physical proximity to a border router is therefore not evidence of being attached to it — each of the two nodes in a switch/module pair could easily have a different, non-obvious parent.

**Not resolved:** which router either Master Bedroom node is actually parented to, or its link margin. The OTBR add-on's REST API (`:8081`) exposes only the local node's own state (`GET /node`, `/node/state`, `/node/ext-address`) — `GET /diagnostics` 404s on this add-on version (3.2.0), and there is no `docker exec`/`ot-ctl` access from the standard HA OS SSH shell, so a real child/neighbor table with per-device RSSI isn't reachable without deeper access than this environment grants. If this recurs, the newly-enabled `sensor.*_ceiling_fan_switch_uptime` / `_reboot_count` / `_thread_channel` / `_thread_network_name` (Master Bedroom switch node, enabled 2026-09-14 — needs a Matter config-entry reload to start populating) are the next diagnostic layer available without add-on-level access.

### Adaptive Lighting `detect_non_ha_changes: false` blanket-flags every untracked turn-on as manual, not just genuine ones

The initial assumption here was that `detect_non_ha_changes: false` makes AL *ignore* a light change it didn't route itself — e.g. a wall-paddle turn-on over a Matter binding. That's wrong. AL's `_respond_to_off_to_on_event` handler (`basnijholt/adaptive-lighting`, `switch.py`) marks *any* off→on transition manual whenever the event isn't tied to a tracked `light.turn_on` context — unconditionally, without checking what brightness the light actually landed on:

```python
if (self._take_over_control
    and (not self._detect_non_ha_changes or self._manual_control_on_external_turn_on)
    and not from_turn_on):
    self.manager.set_manual_control_attributes(entity_id)
```

A wall-paddle tap never calls `light.turn_on` (it's a Matter binding, not a service call), so with `detect_non_ha_changes` off, *every* paddle turn-on gets flagged manual — regardless of how precisely Matter `OnLevel` pre-staging landed it on the curve. This defeated pre-staging's entire purpose: two Inovelli canopy lights turned on at the wall and stuck at whatever brightness they came up at, confirmed via `manual_control_brightness` on the instance switch with no corresponding hold (`long_release`) anywhere in the paddle's event history — a plain tap alone was enough to trigger it.

**Fix:** set `detect_non_ha_changes: true` instead. That routes turn-on detection through AL's real value-comparison logic (`significant_change()`) — a light landing at or near its curve target isn't flagged; only a genuine deliberate value is. `guides/adaptive_lighting.md` has the instance config.

**Separately**, a binding-driven turn-*off* is invisible to AL regardless of this setting — `turn_on_off_event_listener` (the code path that resets manual control on turn-off) only fires on `light.turn_off` **service calls**, and a paddle-off is a state change with no service call behind it. The wall-control automations (`guides/inovelli_switches.md` Step 6) cover this by reacting to the light's *observed* state going `off`, not the call — that branch is still required with `detect_non_ha_changes` on.

### Inovelli VTM30-SN LED bar — only a saturated `hs_color` renders reliably; white / colour-temp are dropped

The switch's RGB notification bar (`light.*_ceiling_fan_switch_led`) advertises `supported_color_modes: [color_temp, hs, xy]` with a nonsense range (`min_color_temp_kelvin` 15, `max` 1000000). In practice, from inside a `script` / automation run: `color_temp_kelvin` and a low-saturation / white `hs_color` or `rgb_color` all flip the entity to `on`, trace cleanly, and show `on` in state history for the full hold — but **emit no visible light**. A fully-saturated `hs_color` (e.g. the fan speed hues `[175/220/265, 100]`) renders every time. A *direct* `light.turn_on` with white does render, which made this maddening to isolate. Fan speed blips work because they use saturated hues; a "warm white 3000 K" canopy-light cue was chased for hours and abandoned (September 2026) — the light turning on/off is its own feedback. If you ever need a non-speed colour on this bar, keep saturation at 100.

**Historical note:** the Inovelli LED bar design (`guides/inovelli_switches.md`) has since moved entirely off this RGB channel and onto the switch's native `LED Color`/`LED Intensity`/`LED Effect` parameters, which retire this quirk rather than working around it — the native `LED Color` select has no saturation concept and includes `White` as a first-class option. `light.*_ceiling_fan_switch_led` is left hidden and unused. This lesson is kept for reference in case that channel is ever revisited.

### Inovelli VTM30-SN LED bar — paddle presses cause a brief native transition flicker, independent of any HA-set value

A paddle-driven change (e.g. the bound ceiling light toggling on/off) shows a ~1s downward-wipe visual on the LED bar that isn't caused by anything HA commands. Confirmed by entity history: `select.*_ceiling_fan_switch_led_effect` never leaves `Solid` through the transition, and the same or larger intensity changes made via the config button (which never touches the paddle) show no flicker at all — only paddle-driven changes do.

The paddle is the one path where the switch's own internal load-control relay physically flips (that's what fires the Matter binding — see the "outgoing binding is coupled to local paddle→load control" entry above). The working theory is a local, firmware-level "paddle was pressed" acknowledgment on the relay-toggle path itself, not anything reachable from `select.select_option`. Tracked in GitHub issue #2 for re-testing after a firmware update; not fixable from the HA side today.

### Inovelli VTM30-SN LED Intensity select — the step list isn't evenly spaced; a plausible-looking literal can be invalid

`select.*_ceiling_fan_switch_led_intensity_on` / `_off` expose a fixed, non-uniform option list: `0, 1, 3, 5, 8, 10, 13, 16, 20, 23, 26, 30, 33, 36, 40, 45, 50, 60, 70, 80, 90, 100`. A hand-picked "reasonable" value in that range (`25`, right between the real steps `23` and `26`) is not automatically a member of the list — `select.select_option` rejects it outright: `Option 25 is not valid for entity ..., valid options are: 0, 1, 3, 5, 8, ...`.

This fails loudly (a clear error in the automation trace, not a silent no-op), but only on the code path that actually writes the bad value — a value used solely in a "day" branch that only runs while a bedroom's fan happens to be on during waking hours can sit broken for a long time before anything exercises it. Caught here when `script.<prefix>_ceiling_fan_led_state` (`guides/inovelli_switches.md`) used a literal `25` for its day-time fan-running intensity, chosen without checking it against the entity's actual `options` attribute.

**Fix:** before hardcoding a `select.select_option` value, read the target entity's `options` list (`ha_get_state` includes it in `attributes`) and pick a listed value — don't assume a step list is evenly spaced or continuous.

### A `binary_sensor.*_home_today`-style sensor flips at midnight, not at the moment the person leaves

A calendar/schedule-derived "is so-and-so home today" sensor recalculates at the day boundary, not when the person actually leaves the house. Gating any nighttime behavior on it going instantaneously `off` — e.g. neutralizing a stale personal sleep flag once someone's "not home today" — fires hours before they've actually gone, while they may still be asleep in the house.

Fix: require the `off` state to have held for a **minimum duration** (`condition: state` with `for:`) long enough to span the person's usual overnight-to-departure window, not an instantaneous check.

(The Inovelli LED-bar design briefly used `for: "08:00:00"` against `binary_sensor.avery_home_today` for exactly this reason, then dropped the sensor from that feature entirely — see `guides/inovelli_switches.md` — once the design changed so a stale personal sleep flag could only ever pick the wrong *dim* brightness, never leave a switch fully dark. The general lesson (minimum-duration gating on any midnight-boundary sensor) still applies to the next place this pattern is needed.)

---

## iOS Live Activities

### `critical_text` paired with `progress` and no chronometer displaces the progress bar, not just the Dynamic Island

`script.household_live_activity`'s field contract documents `critical_text` as "short Dynamic
Island text," implying it's harmless to send alongside a `progress` bar on the Lock Screen card.
That combination was untested until the vacuum's running card shipped it: both laundry consumers
also pass `critical_text`, but always alongside `ends_at` (a chronometer), and the script's own
logic drops `critical_text` outright whenever a chronometer is active — so the pairing of
`progress` + `critical_text` with *no* chronometer had never actually been exercised.

Confirmed live on 2026-09-15: running the vacuum's master-mop-pass card this way showed the area
figure (e.g. "52.2 m²") sitting where the percentage/progress readout should be, and no progress
bar rendered at all. The iOS Companion App's generic Live Activity view apparently shares layout
between the Lock Screen card and the Dynamic Island's expanded region rather than keeping
`critical_text` confined to a separate Dynamic-Island-only slot as the field's own description
assumes.

Fix: don't pass `critical_text` on any card that also carries a numeric `progress` and no
chronometer. `automation.household_vacuum_live_activity`'s "Cleaning, everyone awake" branch now
omits it — the bar renders correctly, and the area figure still surfaces on the `done` card's
message text instead. If a future consumer needs both a live percentage and a short text stat on
the same running card, treat that as an open design question, not an assumed-safe combination.

---

## Shell Command Integration

### Poll for state on command-line lights that can change out-of-band

The Litra Glow integration (`guides/litra_glow.md`) started in optimistic mode, then moved to a polling `command_line` sensor as the source of truth for `state`/`level`/`temperature`. Optimistic mode looks appealing — no per-interaction latency, no flicker — but it silently diverges from reality whenever the device changes without HA's involvement: the USB cable drops, or the light is adjusted via `litra-rs` directly on the Mac. HA then reports a state that's simply wrong, with no mechanism to notice or correct it.

The polling sensor closes that gap: it's the actual source of truth, refreshed immediately after every command handler (`homeassistant.update_entity`) so the UI updates within about a second rather than waiting out the poll interval, and it naturally surfaces `unavailable`/`unknown` when the Mac or the USB device drops — which optimistic mode has no way to represent at all.

**Rule:** prefer polling over optimistic mode whenever the backing device can change state outside HA's control (manual CLI use, another controller, a flaky USB/network link). Reserve optimistic mode for commands that are the *only* way the device's state ever changes.

### macOS primary-display sensors are unreliable while the Mac is driven over Screen Sharing

A Companion App / `command_line` sensor reporting the Mac's primary-display name or resolution reads correctly at the physical console, but while the Mac is being controlled via Screen Sharing it can report an empty display name and a generic virtual resolution instead of the real attached display. An automation that gates on display *identity* (e.g. "restore the desk light only if the primary display is `Studio Display`") then fires or fails to fire depending purely on how the Mac happened to be accessed at that moment.

**Rule:** don't gate automations on which display is attached. If the intent is "someone is at the desk," use a coarser signal — at least one Mac reporting active — which doesn't depend on display detection. `guides/litra_glow.md` §9 uses exactly this fallback.

### Principle of least privilege for shell access

Shell command integrations that SSH into another machine should use:

- A **dedicated service account** on the remote machine, not the user's normal account
- A **scoped SSH key** with `command="..."` restrictions in `authorized_keys` if the command set is fixed
- **Sudoers whitelisting** for any privileged operations, naming the exact commands allowed
- A **dispatch script** on the remote side that validates inputs rather than passing arbitrary strings to the shell

---

## HACS Integrations

### ha-chore-calendar: `pending_period` must be less than the chore's interval (confirmed current, 2026-09-20)

Setting a `pending_period` that equals or exceeds the chore's interval gets the chore permanently stuck in `completed` state. Confirmed by reading `custom_components/chore_calendar/models/base.py::compute_status` directly (v0.12.2, upstream `tcarney/ha-chore-calendar`): `pending_at = due_at - pending_period`, and if `pending_period >= interval` then `pending_at <= last_completed`, which makes `last_completed >= pending_at` unconditionally true — the very first check in `compute_status`, returning `COMPLETED` regardless of how far `now` advances past `due_at`. Nothing fixes this at runtime; only a different `pending_period` value does.

**Rule:** always set `pending_period < interval`. For a 14-day interval, cap pending_period at 7 days. For 30-day intervals, 21 days works well. If you need to see a chore earlier, shorten the interval instead.

### ha-chore-calendar: the "midnight tick" bug in earlier notes does not match current source — likely a misdiagnosis of the rule above

An earlier version of this entry claimed the `completed → pending` transition evaluates only on a daily midnight tick with a strict `today.date() > pending_from.date()` comparison, and that scheduled chores were unreliable for narrow notification windows as a result. **Retracted as of 2026-09-20** after reading the current upstream source directly:

- `coordinator.py`'s `DataUpdateCoordinator` re-evaluates every chore on a **60-second** interval (`DEFAULT_UPDATE_INTERVAL = 60`), not once a day.
- `base.py::compute_status` compares against a full `datetime` (`now >= overdue_at`, `now >= due_at`, `now >= pending_at`) throughout — there is no `.date()` truncation anywhere in the status state machine, for any chore type (interval, scheduled, or oneshot).

No commit history or changelog entry was found describing a midnight-only evaluation ever existing, though the codebase has been substantially refactored since (see the `pending_period` unification landed in PR #12 / v0.8.0, April 2026) — it's possible an earlier pre-refactor version behaved differently, but there's no confirmation either way. The much more likely explanation: the stuck-`completed` symptom that prompted this note was the **`pending_period >= interval` bug above**, misread as a timing/midnight issue rather than a windowing misconfiguration. Trash pickup at the time used a 2-day `pending_period` — plausible to have equaled or exceeded whatever interval/window the scheduled chore was actually configured with.

**Current guidance:** don't assume ha-chore-calendar's status transitions are unreliable. Set `pending_period < interval` per the rule above, and treat any future stuck-`completed` symptom as that misconfiguration first, not an integration bug — re-verify against current source before reintroducing a "don't use X" rule.

### ha-chore-calendar: `create_item` has no field to seed `last_completed` — use `complete_item` right after

`chore_calendar.create_item`'s schema (interval/scheduled/oneshot sub-objects, `pending_period`, `grace_period`) has no `last_completed` or equivalent field. A freshly created interval chore has `last_completed: None` and reads `pending` (unscheduled, dormant) regardless of how the interval is configured. To anchor a chore's first due date to something other than "starts unscheduled," call `chore_calendar.complete_item` immediately after creation with `completed_at:` set to the desired last-done timestamp — `due` then computes as `completed_at + interval`, exactly as if that completion had really happened.

### ha-chore-calendar: a chore doesn't surface as `needs_action` until its pending window opens, even mid-cycle

Unlike a plain to-do item (open the moment it's created), an interval chore stays in the `completed` (dormant) bucket from the moment of completion until `now >= due_at - pending_period`. A chore completed today with a 30-day interval and a 21-day pending period will not appear as actionable — on the card, in `todo.get_items(status=needs_action)`, or via `todo.household_chores`'s open-item count — until roughly day 9 of its cycle. This is correct, intended behavior (it's what distinguishes ha-chore-calendar's richer PENDING/DUE/OVERDUE lifecycle from a bare due-date list), but it surprises anyone expecting every open chore to always be visible somewhere. Check a chore's own `sensor.household_chores_<chore>` `due` attribute to see exactly when it opens, rather than assuming "not in the open list" means "something's wrong."

### ha-chore-calendar's `todo.household_chores` entity requires `due_datetime`, not `due_date`

Only `TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM` is advertised (confirmed in `custom_components/chore_calendar/todo.py::_coerce_due`); passing a bare date via `todo.update_item`'s `due_date:` field is rejected outright ("Date-only due values are not supported; provide a due datetime"). This differs from `local_todo`, which accepts either. Any automation writing a due date to this specific todo entity must use `due_datetime:` with a full timestamp.

### `chore_calendar.update_item`'s `entity_id` must be a plain string in `data:` — `target:` breaks it

Home Assistant's automation `target:` block always expands `entity_id` into a list in the resulting `service_data`, even for a single entity. Most services accept that transparently, but `chore_calendar.update_item`'s (and by extension `create_item`'s, `complete_item`'s, etc.) service schema declares its `entity_id` field as a single string (`entity` selector with no `multiple: true`), and rejects a list outright with `value should be a string at 'entity_id'` — a step-level error, not a validation error at automation-save time, so it isn't caught until the action actually runs.

**Fix:** put `entity_id` inside `data:` as a plain string instead of using `target:` for this service:

```yaml
# Wrong — target: always produces a list, which this service's schema rejects
- action: chore_calendar.update_item
  target:
    entity_id: calendar.household_chores
  data:
    item: "{{ uid }}"
    oneshot:
      due_datetime: "{{ due }}"

# Right
- action: chore_calendar.update_item
  data:
    entity_id: calendar.household_chores
    item: "{{ uid }}"
    oneshot:
      due_datetime: "{{ due }}"
```

`calendar.get_events` and the native `todo.*` services tolerate `target:` fine against the same integration's entities — this is specific to `chore_calendar`'s own custom services.

### `chore_calendar.update_item` reopening a completed `oneshot` clears `terminal` but not `last_completed` — the reopened chore is correctly dormant until its new pending window

Passing a new `oneshot.due_datetime` to `update_item` on a completed oneshot clears its `terminal` flag (confirmed in `services.py::_async_handle_update`'s `reopens_cycle` predicate), which is what lets it re-enter the status cycle at all. But `last_completed` from the previous cycle is left untouched — it's still set to whenever the chore was last marked done. `compute_status`'s fallthrough (`now` before the new `pending_at`, `last_completed is not None`) therefore reports `completed` again, not `pending`, until `now` actually reaches `due_datetime - pending_period`. This is the *same* dormancy behavior documented above for interval chores — not a separate bug, and not something that needs a manual `last_completed` clear. A reopened oneshot with a due date days out will sit `completed` in the interim exactly as intended.

### A `due_datetime` should represent when the human action is required, not when the underlying event happens — or the card's countdown is confusing

Built the trash-pickup chore with `due_datetime` set to the pickup truck's arrival time (07:00 the pickup morning) and `pending_period: 12h`, reasoning that this correctly opened the `pending` window at 19:00 the evening before — which is when the reminder automation actually fires. It does, but the card itself shows "due in 12 hours" all evening, counting down to the truck rather than to anything the person needs to do — because the field genuinely means "the event is at this timestamp," and the truck's arrival was the event chosen.

**Fix:** set `due_datetime` to the actual deadline for the human action (19:00 the evening before pickup — when the bin needs to be at the curb), not the downstream event's own timing. This makes the card's status/countdown legible on its own terms. The cost: every piece of automation logic that reasons about "due date" relative to the real-world event now needs a one-day offset applied consistently — evening reminders check `due == today` instead of `due == tomorrow`, a wake-up reminder the next morning checks `due == yesterday` instead of `due == today`, and a sync that advances to the next cycle after a completion must skip *two* days past the stored due date (the deadline day, then the actual event day) rather than one. Get the semantic right before wiring the automation, since retrofitting it means touching every date comparison at once.

---

## Reminders & To-do Lists

### `todo.get_items` omits keys with no value — never use a bare attribute lookup

An item with no due date or no description simply has no `due` or `description` key in the response at all — it is not present as `null`. `it.description` on such an item raises `UndefinedError` and kills the automation run. Always read with `.get('due', '')` / `.get('description', '')`, never a bare `it.due` / `it.description`.

`due` itself comes back as a plain ISO **string** — `"2026-09-25"` for a date-only item, a full ISO datetime for a datetime item — never a `date`/`datetime` object. `due[:10]` normalizes both shapes to a bare date, and ISO date strings compare correctly with plain `<=`/`>=`/`max()`, so no `as_datetime()` round-trip is needed for comparisons — only for actual `+ timedelta` arithmetic.

### `todo.update_item` merges fields, it does not replace the item

Updating only `status` on an item leaves its existing `due` and `description` completely untouched — confirmed by seeding an item with both, flipping `status: completed`, and reading it back with `due`/`description` intact. This is what lets a mark-done automation set `status: completed` alone and trust a separate reschedule automation to read the untouched `due`/`description` afterward.

### A `local_todo` item's `completed` timestamp is transient — present only while `status: completed`

`todo.get_items` includes a `completed` key (full ISO datetime) on an item currently in `completed` status. The moment the item is reopened (`status: needs_action`), that key is gone from the next read — it is not retained as history. This makes it useful for exactly one purpose: an automation that fires on completion and reads the item back in the same run can use `completed` as a more accurate "when was this actually done" timestamp than `now()`, since the automation may run late (e.g. off a `time_pattern` safety-net poll rather than the instant of completion). It cannot be used to reconstruct a completion history after the fact.

### `result.items` in Jinja resolves to the dict `.items()` method, not a key named `items`

`todo.get_items`'s response is `{entity_id: {"items": [...]}}`. In a template, `result.items` is Jinja's dot-access falling through to the dict's built-in `.items()` method rather than the `"items"` key, since dot-access tries attributes before subscript keys. Use bracket notation for the key, and `.get()` for the entity_id level so a response missing the entity (e.g. the read raced a delete) returns `{}`/`[]` instead of raising:

```jinja
{# Wrong — returns a bound method object, not the list #}
{{ result['todo.household_chores'].items }}

{# Right #}
{{ result.get('todo.household_chores', {}).get('items', []) }}
```

---

## Physical Setup

### Key light distance matters more than brightness

For reducing facial shine in video calls, **distance** is a more effective variable than brightness. The inverse square law means moving the light twice as far away reduces intensity to a quarter while keeping the same color and spectrum.

Aim for a dimmer, farther light over a brighter, closer one. The brightness floor is whatever your camera needs for good exposure.
