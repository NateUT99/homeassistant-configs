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

### Restoration branches need guard conditions

An automation that restores a prior state (turning a thermostat back on after a door closes, restoring lights after a guest mode ends) must verify the current state of the target before restoring. Don't assume that because the automation turned something off, it can blindly turn it back on — the user or another automation may have changed it in the interim.

Always include a `condition: state` (or template equivalent) confirming the target is in the state you expect to restore from.

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

### Use Chime TTS `notify.reminder_*` services for all HomePod announcements

Even though `media_player.play_media` with `announce: true` works on HomePods (see above), the preferred pattern for all TTS announcements in this instance is the **Chime TTS** HACS integration. Chime TTS prepends a configurable chime sound before the spoken message, making announcements less jarring and easier to recognize as home automation alerts rather than random audio playback.

The integration creates room-specific `notify.*` services (e.g., `notify.reminder_kitchen`, `notify.reminder_master_bedroom`). Call them with a `message` key only — Chime TTS handles volume and the chime prefix internally:

```yaml
action: notify.reminder_kitchen
data:
  message: "Your message here."
```

Templates work inside `message`. Do not use `media_player.play_media` directly for new TTS announcements — the chime prefix is the reason both the `notification` and `text_to_speech` labels exist on automations that speak.

---

## Sensors & Calibration

### Percentual offset calibration cannot eliminate a fixed sensor floor

Some Zigbee sensors report a non-zero floor value even when the measured quantity is zero (e.g., a power meter reading 0.5W with nothing plugged in). Percentual offset calibration in Z2M can scale readings but cannot subtract a constant.

To eliminate a floor:

- Use an **absolute offset** via a `template` sensor that subtracts the floor value
- Or adjust the **threshold** in any binary logic that consumes the sensor (e.g., "consider it 'on' above 5W instead of above 0W")

### Sensor-derived state values need debouncing for fast-changing inputs

Binary sensors derived from analog values (power above threshold = device on) can chatter rapidly when the input hovers near the threshold. Use `for:` durations on triggers consuming these, or wrap the binary logic in a template sensor with hysteresis.

---

## Zigbee & Lighting Groups

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

## Matter & HomeKit

### Use Matter Hub (RiDDiX fork) as the sole bridge

Multiple Matter/HomeKit bridges fighting over the same devices produces unreliable state and duplicated entities in HomeKit. Standardize on Matter Hub and disable other bridges.

### Some integrations need HACS replacements for proper entity types

The default Xiaomi integration exposes pedestal fans as switches, not fans, which breaks HomeKit fan controls (oscillate, speed). The `hass-xiaomi-miot` HACS integration exposes proper `fan` entities. When a device's primary entity type seems wrong, check HACS for a better integration before working around it.

---

## Shell Command Integration

### Optimistic mode for command-line lights

When an HA `light` entity is backed by a `command_line` shell command (e.g., the Litra Glow via `litra-rs`), prefer **optimistic mode** over polling for state. Polling adds latency to every UI interaction and produces flickering between commanded state and stale poll results.

Optimistic mode assumes the command succeeded and updates HA state immediately. Reconcile with reality only when an error occurs or on manual refresh.

### Principle of least privilege for shell access

Shell command integrations that SSH into another machine should use:

- A **dedicated service account** on the remote machine, not the user's normal account
- A **scoped SSH key** with `command="..."` restrictions in `authorized_keys` if the command set is fixed
- **Sudoers whitelisting** for any privileged operations, naming the exact commands allowed
- A **dispatch script** on the remote side that validates inputs rather than passing arbitrary strings to the shell

---

## Physical Setup

### Key light distance matters more than brightness

For reducing facial shine in video calls, **distance** is a more effective variable than brightness. The inverse square law means moving the light twice as far away reduces intensity to a quarter while keeping the same color and spectrum.

Aim for a dimmer, farther light over a brighter, closer one. The brightness floor is whatever your camera needs for good exposure.
