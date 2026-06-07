# Dashboard Design Standard

---

## Purpose & Scope

This standard governs the design and construction of all Home Assistant storage-mode dashboards in this instance. It covers visual layer choices, card conventions, room tile design, pop-up patterns, chip strip conventions, and HACS dependency policy.

Scope: storage-mode dashboards created via the HA UI or `ha_config_set_dashboard`. YAML-mode dashboards (`configuration.yaml`) are out of scope.

The standard is viewport-agnostic. The `mobile` dashboard is the reference implementation. When a desktop dashboard is built, a separate guide documents the grid and nav differences; the card vocabulary, pop-up pattern, and theming rules in this standard apply to both.

---

## Core Principles

- **Bubble Card is the primary card framework.** Use it for room tiles, pop-up overlays, chip strips, media, climate, separator headings, and utility controls. Reach for Mushroom or native `tile` only when Bubble Card has no equivalent or its equivalent is materially worse. Known fallback domains are documented in the HACS Dependency Policy below — reaches for fallback are always deliberate and noted at the use site.
- **Modal pop-ups replace page navigation.** Use Bubble Card pop-ups (triggered by URL hash) for all room drill-down and utility detail views. Do not use `subview: true` views. Browser back navigation, ESC, tap-outside, and swipe-down all close pop-ups.
- **Room tiles: tap = popup, hold = toggle, sub-buttons = key devices.** Every room tile is a single Bubble Card `button` card. Tapping opens the area's modal pop-up. Holding toggles the primary light. Sub-buttons on the tile surface provide 2–4 quick-action controls for the most-used devices in that room (fan, primary media, key lights) without requiring the pop-up.
- **No brightness or color sliders anywhere.** Adaptive Lighting manages brightness and color temperature automatically. Do not expose a slider on any room tile, pop-up, or inline card — it creates a confusing dual-control surface. The `button_type: switch` layout shows entity state color without a slider.
- **Mushroom chips-card for chip strips.** The Home view chip strips are implemented as Mushroom `mushroom-chips-card` cards — one card per strip, stacked vertically. Bubble Card `sub-buttons-only` was evaluated and rejected: the visual output does not match the compact pill-chip style Mushroom delivers. This is a deliberate, documented fallback per the HACS Dependency Policy below.
- **Condition-triggered sections for ambient context.** Sections can appear and disappear automatically by setting section-level `visibility` directly on an entity's state — no chip, no `input_boolean` toggle needed. Use this for content that is relevant whenever a particular state exists (e.g., overdue reminders, vacuum not docked). The chip for the same feature navigates directly to the full pop-up; the inline section just surfaces the most actionable summary automatically.
- **Inline toggle as a manual override pattern.** A chip's `tap_action` can toggle an `input_boolean` helper (`input_boolean.show_<feature>`, initial: `false`) to show or hide a section inline on the Home view rather than opening a pop-up modal. Use when the content is compact, the user should explicitly request it, and there is no clear automatic trigger condition. Pop-ups are better for extensive content or when isolating focus from the Home view matters. Tapping the chip again dismisses the inline content. A `hold_action` on the same chip can navigate to the full pop-up if one exists.
- **Theming via Bubble Card CSS variables.** Centralize all visual tokens (border radius, accent color, blur, sub-button spacing) in global Bubble Card CSS variable overrides. Bubble Neon provides the base visual language. card-mod is retained for narrow CSS cases that global variables don't reach (currently: vacuum map image transforms).
- **Confirmation dialogs always include descriptive text.** See the Confirmation Dialogs section below.
- **The design target is between Apple Home and full HA.** Sufficient ambient context at a glance (chip strips, room state on tiles), with tap to drill into any room or utility. Avoid information density that requires interpretation on the Home view; reserve raw sensor data and detailed controls for pop-ups.

---

## HACS Dependency Policy

Approved frontend resources:

| Resource | Purpose | Status |
|---|---|---|
| Bubble Card | Primary card framework | Required |
| Bubble Card Tools | Module store backend (required for custom modules) | Required |
| Bubble Badges 2 | Overlay badge indicators on card surfaces | Required |
| Bubble Weather | Weather icon templating module | Required |
| Bubble Neon | Visual theme / CSS variable baseline | Required |
| card-mod | CSS overrides where Bubble Card global variables don't reach | Narrow use |
| Mushroom Cards | Fallback for specific capability gaps | Fallback only |

**Mushroom Cards fallback — documented gaps today:**

| Gap | Mushroom card | When to use |
|---|---|---|
| Chip strip visual style | `mushroom-chips-card` | Home view chip strips; Bubble Card `sub-buttons-only` evaluated and rejected visually |
| Jinja `icon_color` template where Bubble Card JS template is brittle | `mushroom-template-card` | Reminder cards, vacuum consumables |
| Light color-picker UX not yet matched by Bubble Card | `mushroom-light-card` | Explicit color-picking UI, if needed |

Document every Mushroom fallback use at the card use site (inline comment or guide note). Do not introduce new fallback gaps without updating this table.

Do not introduce additional HACS frontend resources without an explicit decision.

---

## Dashboard Naming

| Property | Convention |
|---|---|
| `url_path` | Short hyphenated slug: `mobile`, `desktop` |
| `title` | Human-readable without version numbers: `Mobile`, `Desktop` |
| `icon` | Reflects the target device: `mdi:cellphone` for mobile, `mdi:monitor` for desktop |
| `show_in_sidebar` | `true` |

Version numbers are dropped from dashboard slugs — they belong in git history and the guide's Last Updated date, not the URL.

---

## Home View Structure

Every dashboard's primary view is titled **Home**, uses `type: sections` and `max_columns: 1` (mobile).

**Sections, in this order:**

1. **Chip strips** — no section title; one `mushroom-chips-card` per strip stacked vertically
2. **Condition-triggered sections** — no section titles; section-level `visibility` gated on entity state (e.g., overdue count, vacuum state); appear automatically when relevant, otherwise zero-height
3. **Room tiles** — all rooms in a single section with no title; a Bubble Card `separator` card at the top acts as the visible heading. Do not use per-room sections — the `sections` view type renders a large top margin above each section heading, making per-room sections visually noisy.
4. **Pop-up definitions** — one section per area at the bottom of the view; these render invisibly until triggered by their hash
5. **Footer navigation** — a `card_type: sub-buttons` card with `footer_mode: true`; persistent room/area navigation bar at the bottom of the view

Do not reorder these groups or add sections between them without updating this standard.

Pop-up sections have no visible title. HA renders an empty section heading as zero-height when no title is set, so the block collapses cleanly — the pop-up overlay is the intended UI surface, not the section.

---

## Room Tile Pattern

Each area (room or utility) on the Home view is a single Bubble Card `button` card. It serves as the visual entry point for that area.

**Standard room tile (rooms with a primary light):**

```yaml
type: custom:bubble-card
card_type: button
name: <Room Name>
icon: <mdi room icon>
entity: light.<area>_<primary>        # primary light entity
button_type: switch                    # shows entity on/off state in background; or use slider + read_only_slider: true for ambient brightness display
tap_action:
  action: navigate
  navigation_path: "#<area-slug>"     # opens the room pop-up
hold_action:
  action: toggle                      # quick light on/off without popup
double_tap_action:
  action: none
sub_button:
  - entity: <key device 1>
    name: <label>
    tap_action: {action: toggle}
  # 2–4 sub-buttons total; curate per room based on what's most-used
```

**Sub-button selection rule:** Include the 2–4 devices you'd interact with most from the home view without needing the full pop-up. Default set: ceiling fan (if present), primary media player (if addressable from this view), any frequently-toggled secondary light. Don't include sensors (read-only entities belong in the pop-up).

**`button_type` options:** `switch` shows entity on/off color in the card background — default for most rooms. `slider` with `read_only_slider: true` shows a brightness bar as ambient state info without an interactive control. Do not use `slider` without `read_only_slider: true` — that exposes an adjustable brightness slider, which is prohibited.

**Fallback room tiles (rooms without a primary light):**

| Room type | `button_type` | Entity |
|---|---|---|
| Garage (cover only) | `name` | `cover.garage_door` — sub-buttons for garage door open/close |
| Outside (sensors only) | `state` | `sensor.outside_temperature` |

**Utility tiles** follow the same structure with `button_type: name` or `state`, `tap_action: navigate #popup`, and sub-buttons for the 1–2 most relevant status readouts (e.g., overdue reminders count for the Reminders tile, vacuum state for the Vacuum tile).

---

## Pop-up Pattern

Each area's pop-up is a Bubble Card `pop-up` card placed in its own section at the bottom of the Home view.

**Hash slug naming:** `#<area-slug>` where `<area-slug>` is the hyphenated area name: `#living-room`, `#kitchen`, `#master-bedroom`, `#averys-room`, `#office`, `#bathroom`, `#garage`, `#outside`, `#reminders`, `#vacuum`, `#climate`, `#water-leaks`.

**Structure:**

```yaml
type: custom:bubble-card
card_type: pop-up
hash: "#living-room"
name: Living Room
icon: mdi:sofa
cards:
  # Pop-up content — any Bubble Card or HA card
  - type: custom:bubble-card
    card_type: separator
    name: Lights
  - type: custom:bubble-card
    card_type: button
    entity: light.living_room_fan
    ...
```

**Close behavior:** swipe down from header, ESC on desktop, tap outside, browser back. Do not add a manual back-navigation card — Bubble Card renders a close button.

**Room pop-up content structure** (include only sections that apply):

| Section | Content | Required |
|---|---|---|
| Lights | Bubble Card buttons, one per light entity; no sliders | If room has lights |
| Fan | Bubble Card button with fan speed sub-buttons | If room has a ceiling fan |
| Climate | Bubble Card climate card | If room has a thermostat |
| Media | Bubble Card media-player card | If room has addressable media |
| Sensors | Read-only state buttons or sub-buttons-only | If room has sensors worth surfacing |

---

## Status Chip System

The chip strip section at the top of the Home view uses stacked Mushroom `mushroom-chips-card` cards — one card per strip, stacked vertically. Each chip card uses `alignment: center` and `card_mod` to set chip height (`--chip-height: 30px`) and padding (`--chip-padding: 0 6px`). Chips use `type: conditional` wrappers for visibility and Jinja templates for `icon_color`.

**Two strips organized by function:**

| Strip | Name | Purpose | Visibility |
|---|---|---|---|
| 1 | Controls | Interactive chips — expand inline content or directly toggle a feature | Always visible: Weather, Thermostat, Vacuum, Reminders, Guest |
| 2 | Status & Modes | Status indicators, conditional alerts, and mode chips | 2 anchored (AQI, Alarm) + conditional chips |

**Sub-button visibility conditions:** use the Bubble Card `visibility` property on each sub-button with the same condition logic used for Mushroom chips. `state_not: "off"` for binary sensors (conservative default — surfaces `unknown` as alert).

**Alert chip coloring:** use the Bubble Card JS template system or `icon_color` field for red/orange/green color logic. Do not rely on entity-class default colors for alert chips — explicit color control is required for correct behavior when the entity is in `unknown` or `unavailable` state.

**Icon-only sub-buttons:** omit the `name` field when no label is needed. Do not set `name: ""` — it allocates an empty text area and shifts the icon off-center.

**Hold-to-toggle for sensitive direct-toggle chips:** chips that directly toggle a high-impact feature (guest mode, presence booleans) should use `hold_action: toggle` and `tap_action: none`. This prevents accidental state changes from an unintended tap on a crowded strip.

**Contextual gates for door and garage alerts** (same rule as mobile-3): only alert when the entity is open AND the household is sleeping OR nobody is home. Water leaks and the freezer door are never gated — always alert-worthy.

---

## Inline Toggle Pattern

An alternative to the pop-up pattern for brief content that fits inline on the Home view without a modal overlay. A chip's `tap_action` toggles an `input_boolean` helper; a section uses `visibility` to show or hide its content based on that helper's state.

**When to use:** content is compact (a handful of cards), ephemeral (not requiring sustained focus), and benefits from appearing in-place below the chips. Use pop-ups when the content is extensive or when modal focus is warranted.

**Implementation:**

1. Create `input_boolean.show_<feature>` (initial: `false`; icon matching the feature).
2. Chip `tap_action`:
   ```yaml
   tap_action:
     action: perform-action
     perform_action: input_boolean.toggle
     target:
       entity_id: input_boolean.show_<feature>
   ```
3. Inline section with `visibility` (placed between the chip strip section and the room tile sections):
   ```yaml
   visibility:
     - condition: state
       entity: input_boolean.show_<feature>
       state: "on"
   cards:
     - ...
   ```
4. Optionally set `hold_action: navigate` on the same chip to open the full pop-up if one exists.

**Current uses:** none — the mobile dashboard uses condition-triggered sections (auto-appear based on state) rather than chip-toggled inline sections. The inline toggle pattern is documented for cases where user intent, not device state, should drive visibility.

**Former uses (migrated to condition-triggered):**

| Chip | Was | Now |
|---|---|---|
| Weather | Toggle `input_boolean.show_weather_forecast` | Tap → `more-info` on `weather.apartment` |
| Thermostat | Toggle `input_boolean.show_thermostat_controls` | Tap → navigate `#climate` |
| Vacuum | Toggle `input_boolean.show_vacuum_controls` | Inline section auto-appears on state; chip navigates `#vacuum` |
| Overdue reminders | Toggle `input_boolean.show_reminders` | Inline section auto-appears when count > 0; chip navigates `#reminders` |

**Half-width inline cards:** add `layout_options: {grid_columns: 2}` to each card in the inline section so the sections view renders them two-per-row.

---

## State-Triggered Contextual Controls

An alternative to the inline toggle pattern for controls that should appear automatically when a device is active — no chip or `input_boolean` involved. A Bubble Card `sub-buttons` card sits below a room tile in the same section; its `visibility` is gated on an entity's state.

**When to use:** the controls are tightly coupled to a device with a clear active/inactive state (e.g., TV on/off), and auto-show/hide behavior is preferable to a manual chip toggle. The inline toggle pattern is better when user intent should drive visibility rather than device state.

**Implementation:**

```yaml
type: custom:bubble-card
card_type: sub-buttons
visibility:
  - condition: state
    entity: <triggering entity>
    state: "on"
sub_button:
  bottom:
    - entity: <control 1>
      tap_action: {action: toggle}
      name: <label>
    # additional controls
```

**Current uses:**

| Trigger entity | Location | Controls shown |
|---|---|---|
| `media_player.living_room_tv` | Below Living Room tile | TV Light Sync, Movie Mode, Night Mode, Sonos Volume |

---

## Condition-Triggered Sections

An alternative to the inline toggle pattern when content should appear automatically based on house state, with no user action required. Section-level `visibility` is set directly on an entity state — no chip toggle, no `input_boolean` helper.

**When to use:** there is a clear, unambiguous state that makes the content relevant (vacuum running or ran today; overdue tasks exist). The user should not have to ask for it. Use the inline toggle pattern when user intent — not device state — should drive visibility.

**Implementation:**

```yaml
# Section-level visibility — set on the section object, not on cards within it
visibility:
  - condition: numeric_state
    entity: number.overdue_reminders_count
    above: 0
cards:
  - ...
```

Or with an `or` condition:

```yaml
visibility:
  - condition: or
    conditions:
      - condition: state
        entity: vacuum.roborock_q8_max
        state_not: docked
      - condition: state
        entity: input_select.vacuum_ran_today
        state: "Yes"
```

**Current uses:**

| Section | Visibility condition | Content |
|---|---|---|
| Overdue reminders / trash pickup | `number.overdue_reminders_count` > 0 OR `input_boolean.trash_pickup_pending` = on | Trash card (when pending) + half-width grid of overdue task cards |
| Vacuum controls | vacuum not docked OR `input_select.vacuum_ran_today` = Yes | Vacuum tile with state and commands |

---

## Footer Navigation

A persistent room/area navigation bar at the bottom of the Home view. Implemented as a Bubble Card `card_type: sub-buttons` card with `footer_mode: true` — renders as a fixed-position strip of icon-only sub-buttons.

Each sub-button uses `tap_action: navigate` with a hash to the relevant pop-up. The footer replaces page-level navigation: rather than switching views, the user opens any room's pop-up directly from anywhere on the Home view.

```yaml
type: custom:bubble-card
card_type: sub-buttons
footer_mode: true
sub_button:
  bottom:
    - name: Living Room
      icon: mdi:sofa
      tap_action:
        action: navigate
        navigation_path: "#living-room"
    # additional rooms
```

---

## card-mod Use Cases

card-mod is approved for two use cases:

**1. Vacuum map image crop/zoom** — the Roborock integration bakes excess black padding into map images. card-mod removes the card's default padding and applies CSS transforms to crop and reposition the floor plan:

```yaml
card_mod:
  style: |
    ha-card { padding: 0; overflow: hidden; }
    hui-image {
      transform: scale(1.5) translateX(-3%) translateY(13%);
      transform-origin: center center;
      display: block;
      margin: -12% 0;
    }
```

These values are floor-plan-specific. See `guides/mobile_dashboard.md` → Vacuum Pop-up for technique details.

**2. Any Bubble Card CSS gap** — when a Bubble Card global CSS variable doesn't cover a needed style adjustment, use card-mod as a targeted override. Document the reason at the use site.

Do not use card-mod to replicate styling that Bubble Card's global CSS variables already expose.

---

## Confirmation Dialogs

**Confirmation dialogs must always include descriptive text.** Never use `confirmation: true` (bare boolean). Always use the object form with a `text` field that tells the user exactly what will happen:

```yaml
# Wrong
confirmation: true

# Correct
confirmation:
  text: "Close garage door?"
```

The text should describe the irreversible or consequential action in plain language. Match tense to the action: "Close garage door?", "Reset filter usage counter?", "Mark Car Washed as done today?".

---

## Quick Reference

| Pattern | Bubble Card type | Notes |
|---|---|---|
| Room tile | `button` (`button_type: switch`) | tap=popup, hold=toggle; sub-buttons for key devices |
| Utility tile | `button` (`button_type: name` or `state`) | tap=popup; sub-buttons for status readouts |
| Chip strip | Mushroom `mushroom-chips-card` | One card per strip; `type: conditional` wrappers for visibility; Bubble Card `sub-buttons-only` rejected visually |
| Alert chip | Mushroom chip with explicit `icon_color` | Not entity-class color — explicit red/green/orange required |
| Condition-triggered section | Section with `visibility` on entity state | Auto-appears based on house state; no chip or helper; preferred over inline toggle |
| Inline toggle | chip + `input_boolean` + section `visibility` | Tap chip → show/hide when user intent (not state) should drive visibility |
| State-triggered controls | `sub-buttons` card with `visibility` on entity state | Auto-shows when device is active; no chip or helper needed |
| Footer navigation | `sub-buttons` with `footer_mode: true` | Persistent bottom nav strip; tap → room pop-up via hash |
| Room pop-up | `pop-up` with `cards` array | Hash slug: `#area-name`; placed in dedicated section at view bottom |
| Pop-up trigger | button `tap_action: navigate #hash` | Room tile is the trigger; no secondary trigger needed |
| Light control (popup) | `button` (`button_type: switch`) | No sliders; hold=toggle or sub-button for power |
| Fan control | `button` with speed sub-buttons | |
| Climate control | Bubble Card `climate` card | Fallback to native `tile` with hvac-modes feature if climate card lacks needed UX |
| Media control | Bubble Card `media-player` card | |
| Vacuum controls | `button` with command sub-buttons | |
| Reminder card | `button` or Mushroom `mushroom-template-card` fallback | Template `icon_color` for overdue state |
| Vacuum consumables | `button` or Mushroom `mushroom-template-card` fallback | Template `icon_color` for maintenance-due state |
| Map image crop/zoom | `picture-entity` with `card_mod` | `ha-card {padding:0; overflow:hidden}` + `hui-image {transform:scale/translate; margin:-12% 0}` |
| Separator heading | `separator` | Within pop-up or between inline sections |
| Confirmation dialog | `confirmation: {text: "..."}` | Never bare `confirmation: true` |
| Weather | `button` + Bubble Weather module | |
| Status badges | Bubble Badges 2 | Overlay indicators on card surfaces |
