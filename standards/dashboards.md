# Dashboard Design Standard

Version 0.4

| Version | Date | Changes |
|---|---|---|
| 0.4 | June 2026 | Pivot to Bubble Card as primary framework. Full rewrite. Standard now governs mobile and future desktop dashboards. Mushroom retained as documented fallback. |
| 0.3 | June 2026 | Icon-only chip centering rule added; card-mod scope expanded to cover non-chip element transforms; Quick Reference updated |
| 0.2 | June 2026 | Native-first principle: tile cards are default in subviews; Mushroom exceptions documented with justification; Room Subview Structure and Quick Reference updated accordingly |
| 0.1 | June 2026 | Initial draft — patterns established during Mobile 3.0 build |

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
- **Sub-buttons are the chip equivalent.** The Home view chip strips are implemented as Bubble Card `sub-buttons-only` cards — visually equivalent to the Mushroom chip row but driven by Bubble Card sub-button visibility conditions and Bubble Badges 2 indicators.
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

1. **Chip strips** — no section title; one `sub-buttons-only` card per strip stacked vertically
2. **Room tiles** — one section per room (no section title); each section contains one Bubble Card `button` card
3. **Utility tiles** — one section per utility area (Reminders, Vacuum, Climate, Water Leaks); same button card pattern as rooms
4. **Pop-up definitions** — one section per area at the bottom of the view; these render invisibly until triggered by their hash

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
button_type: switch                    # shows entity state color in background
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

The chip strip section at the top of the Home view uses stacked `sub-buttons-only` cards — one card per strip, each with a sub-button array. Sub-buttons handle conditional visibility, icon color, and tap actions.

**Four strips (carry over from mobile-3, same logic):**

| Strip | Name | Visibility |
|---|---|---|
| 1 | Environment | Always visible: Weather, AQI, Thermostat |
| 2 | Status & Alerts | 4 anchored chips + conditional alert chips |
| 3 | Modes | All conditional (sleeping, movie mode, quiet mode, light sync) |
| 4 | Presence | Always visible: Nate, Guest |

**Sub-button visibility conditions:** use the Bubble Card `visibility` property on each sub-button with the same condition logic used for Mushroom chips. `state_not: "off"` for binary sensors (conservative default — surfaces `unknown` as alert).

**Alert chip coloring:** use the Bubble Card JS template system or `icon_color` field for red/orange/green color logic. Do not rely on entity-class default colors for alert chips — explicit color control is required for correct behavior when the entity is in `unknown` or `unavailable` state.

**Icon-only sub-buttons:** omit the `name` field when no label is needed. Do not set `name: ""` — it allocates an empty text area and shifts the icon off-center.

**Contextual gates for door and garage alerts** (same rule as mobile-3): only alert when the entity is open AND the household is sleeping OR nobody is home. Water leaks and the freezer door are never gated — always alert-worthy.

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
| Chip strip | `sub-buttons-only` | One card per strip; sub-button `visibility` for conditional chips |
| Alert chip | sub-button with explicit `icon_color` | Not entity-class color — explicit red/green/orange required |
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
