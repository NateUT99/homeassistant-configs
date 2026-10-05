# Dashboard Design Standard

*Version 1.0.4 — October 2026*

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.0.4 | October 2026 | Alerts use icon colour only — no chip background tint |
| 1.0.3 | October 2026 | Room tiles full width on phone, 4-up on desktop |
| 1.0.2 | October 2026 | Chip strip height `rows: 1.2` |
| 1.0.1 | October 2026 | Views stay visible; Kiosk Mode alone hides the tabs |
| 1.0 | October 2026 | Rewrite for the new house: one responsive dashboard; Bubble Card 3.4 Jinja templates replace CSS-in-JS; Navbar Card + Kiosk Mode replace footer nav and the view header; Mushroom removed; room-tile eligibility rule; shared logic in `custom_templates` macros and Bubble modules; dashboard mirror; AI-content conventions |
| 0.1 | June 2026 | Initial release; Bubble Card primary commitment; inline toggle pattern |

---

## 1. Purpose & Scope

Governs every storage-mode Lovelace dashboard on this instance: dependencies, structure,
layout, the card vocabulary, templating, colour, and how dashboards are mirrored in the repo.

Out of scope: YAML-mode dashboards, the per-dashboard build (entity lists, room inventory,
pop-up contents) — that lives in the dashboard's guide (`guides/home_dashboard.md`), and
the AI generation pipeline (`guides/ai_insights.md`).

---

## 2. Core Principles

- **One responsive dashboard.** `home-main` serves phone, tablet, and desktop from one
  config. Sections views reflow by width; there is no separate mobile dashboard.
- **Glanceable first, detail on demand.** The Home view answers "is anything wrong, and
  what's on?" in one screen. Everything else is one tap away in a pop-up.
- **Bubble Card is the card framework.** Native HA cards (`tile`, `heading`, `markdown`,
  graphs) are fine inside pop-ups and secondary views where they fit better. No Mushroom.
- **Templates, not scripts-in-CSS.** Dynamic text, icons, colours, and visibility use
  Bubble's server-rendered Jinja (§9). JavaScript `${...}` templates are a last resort.
- **Write logic once.** Anything used by more than two cards becomes a Jinja macro or a
  Bubble module (§9.2). Never copy a non-trivial template between cards.
- **Colour means something.** Neutral by default; colour only signals state worth noticing
  (§10).
- **No brightness or colour sliders.** Adaptive Lighting owns brightness and colour
  temperature. Never expose a slider (or `read_only_slider: false`) on a light.
- **Prefer native visibility.** A `visibility` condition (`state`, `numeric_state`,
  `screen`, `template`) over CSS `display: none`.

---

## 3. Dependencies

Frontend resources approved for dashboards. Do not add another without an explicit decision
and an update to this table.

| Resource | Type | Purpose |
|---|---|---|
| Bubble Card (≥ 3.4) | HACS frontend | Card framework: buttons, chips, pop-ups, climate, media, separators |
| Bubble Card Tools | HACS integration | Module storage backend (`/config/bubble_card/modules/`) — must be added as an integration, not only installed |
| Navbar Card | HACS frontend | Navigation: bottom bar on phone, left rail on desktop |
| Kiosk Mode | HACS frontend | Hides the HA header on `home-main` |
| Frosted Glass | HACS theme | Base theme, applied per view |
| UIX | HACS integration | CSS escape hatch for cases Bubble styles can't reach (e.g. vacuum map crop) |
| chore-calendar-card | Bundled with Chore Calendar | Chores view |

> Mushroom is not approved. The view-level `badges` row is not used, which removes the only
> case Mushroom ever covered.

---

## 4. Dashboard Structure

| Property | Value |
|---|---|
| `url_path` | `home-main` (custom paths need a hyphen) |
| `title` | `Home` |
| `icon` | `mdi:home` |
| Views | `home`, `climate`, `energy`, `chores`, `maintenance` |
| View type | `sections`, `max_columns: 4`, `theme: Frosted Glass` |
| View tabs | Left visible — Kiosk Mode hides the header (tabs included). Never `visible: false`: with every view hidden, the bare dashboard URL renders blank |
| Header | Hidden at all widths: `kiosk_mode: {hide_header: true}` at the dashboard root |

**Editing:** append `?disable_km` to the URL to restore the header and its edit pencil.

**Navbar Card** is configured once under `navbar-templates.main` at the dashboard root and
placed in every view as `{type: custom:navbar-card, template: main}` as the first card of
the view's first section. Desktop `position: left`; labels shown on both form factors. The
`maintenance` route is hidden for non-admin users.

---

## 5. Layout & Responsiveness

- Sections reflow on content width: roughly 1 column on a phone, 2 near 700 px, 3–4 on a
  desktop. Size cards with `grid_options` (`columns` on the 12-column section grid); never
  `layout_options`.
- Full-width bands (briefing, chip strip) are a section with `column_span: 4`.
- Room tiles sit in one `column_span: 4` section with `grid_options: {columns: 12}` — full
  width on a phone (one tile per row), four per row on desktop.
- Use the `screen` visibility condition only when a card genuinely differs by form factor.
  The default is the same content everywhere.
- Pop-ups use `popup_mode: adaptive-dialog`: fit-content sheet on a phone, centred dialog
  on desktop.

---

## 6. Home View

Sections, in order:

1. **Briefing** — the AI briefing card (§11), full width.
2. **Chip strip** — one Bubble `sub-buttons` card, full width (§7).
3. **Condition-triggered sections** — appear only while relevant (vacuum running, laundry
   running, overdue chores), gated by section-level `visibility` on entity state. No
   helper toggles.
4. **Rooms** — one section of room tiles (§8).
5. **Pop-ups** — one section holding every pop-up card; renders nothing until a hash opens
   one.

---

## 7. Chip Strip

A single Bubble `card_type: sub-buttons` card with `hide_main_background: true`, two
`bottom` groups laid out as rows (`bottom_layout: rows`), each `justify_content: center`,
and `rows: 1.2` — the height that fits two single-line chip rows. See `LESSONS.md` →
*Bubble `sub-buttons` cards anchor their rows to the bottom*.

| Row | Purpose | Contents |
|---|---|---|
| 1 — Status & alerts | Is anything wrong? | Always: weather, AQI, front-door lock, garage. Conditional: alerts that only exist while true |
| 2 — Features | What's running / due? | Thermostat, plus conditional feature chips (fireplace, vacuum, chores, laundry, dishwasher, trash) |

The current chip list and each chip's logic live in the guide.

**Rules:**

- **Neutral background on every chip:** `state_background: false`,
  `light_background: false`. See `LESSONS.md` → *Bubble sub-buttons tint themselves*.
- **Colour the icon, never the chip.** Alerts are carried by icon colour alone (§10); a
  tinted chip background lowers contrast and makes the chip harder to read. Target a chip
  with `css_class` and style it with Jinja in the card's `styles`.
- **Conditional chips use `visibility`**, not CSS.
- **Icon-only chips omit `name`** — never `name: ""`, which reserves an empty text slot.
- **Contextual gating for openings:** a door, window, garage, or unlocked lock is red when
  the household is asleep or away, orange when someone is home and awake. Leaks are always
  red, ungated.
- **Sensitive toggles are hold-only:** `tap_action: none`, `hold_action: toggle` (guest
  mode, presence booleans). A hold that changes a security device (lock, garage) also
  carries a confirmation (§12).
- **Every chip taps through** to the pop-up or view that explains it.

---

## 8. Room Tiles

### 8.1 Which areas get a tile

An area gets a tile only if it has **something a person controls from the dashboard more
than occasionally** — a room light or fan, primary media. Areas that are small, sensor-only,
or fully automated do not get a tile; their content folds into the pop-up that already
owns it (entrance and garage into `#security`, utility room into `#laundry`). The same
tile set appears on every form factor.

The current tile list and fold-in mapping live in the guide. Re-evaluate when an area gains
controllable devices.

### 8.2 Tile pattern

One Bubble `button` card per area:

| Element | Rule |
|---|---|
| `button_type` | `switch` when the area has a primary HA light; `name` when it doesn't |
| `entity` | The area's primary light, if it is in HA |
| `name` / `icon` | The area name and the area registry icon |
| `state_content` | Live summary from the shared macro (§9.2), e.g. `3 lights on · 69°` |
| Tap (`button_action.tap_action` and `tap_action`) | `navigate` to `#<area-slug>` |
| Hold (`button_action.hold_action` and `hold_action`) | `toggle` the primary light; `none` when there is no primary light in HA |
| Sub-buttons | **Primary room controls only**: ceiling fan, primary TV/Apple TV, fireplace. Zero to two. Lamps, accents, key lights, and indicators belong in the pop-up |

Bind actions on both the icon (`tap_action`/`hold_action`) and the body
(`button_action.*`) — see `LESSONS.md` → *Bubble Card icon vs. button action areas*.

**Light counts** come from the shared macro, which filters `area_entities(...)` with
`reject('is_hidden_entity')`. Hide an indicator or group member in the entity registry
instead of excluding it in a template. See `LESSONS.md` → *An area's `light.*` entities
include indicator LEDs*.

---

## 9. Templates & Shared Logic

### 9.1 Where templates go

| Need | Use |
|---|---|
| Dynamic text, icon | Jinja in `name`, `icon`, `state_content` (quoted) |
| Dynamic icon colour | Jinja inside `styles`, targeting a `css_class` |
| Show/hide | `visibility` with native conditions; `condition: template` only when no native one fits |
| Something Jinja can't reach | JavaScript `${...}` in `styles` — comment why |

Always quote a template (`name: "{{ ... }}"`). Bubble renders templates on the HA server,
so every HA function and every `custom_templates` macro is available.

### 9.2 Write it once

- **Logic** (counts, summaries, gating rules) used by more than two cards is a Jinja macro
  in `ha/custom_templates/dashboard.jinja`, imported with
  `{% from 'dashboard.jinja' import <macro> %}`. Pass entity IDs and areas as arguments —
  an imported macro cannot see the card's `entity` variable.
- **Look** (a tile's styles, a consumable's icon colour) used by more than two cards is a Bubble
  module in `ha/bubble_modules/<id>.yaml`, applied by ID.
- When an alert condition already exists as a helper (a group, a threshold, a template
  binary sensor), the chip reads the helper — don't re-derive it in the dashboard.

---

## 10. Colour

| Meaning | Colour | Variable |
|---|---|---|
| Normal / secured | Green icon | `--green-color` |
| Attention — home and awake | Orange icon | `--orange-color` |
| Alert — asleep, away, leak, fault | Red icon | `--red-color` |
| Active / running | Theme accent | entity state colour |
| Neutral / informational | Theme default | — |

Use theme variables, never hex values, so light and dark modes both work.

---

## 11. AI-Generated Content

Cards that show Claude-generated text (briefing, house summary, weekly digest):

- Read from the `ai_insights` sensors; never call `ai_task` from a card. Generation is
  owned by scripts (see `guides/ai_insights.md`).
- Show the content's age (`last-updated` in `state_content` or "Updated 7:00").
- A Refresh action calls the generating script with a confirmation-free tap. The script
  enforces its own cooldown.
- When the sensor is `unknown` or unavailable, show a neutral placeholder, never an error.

---

## 12. Confirmation Dialogs

Every confirmation uses the object form with text describing the consequence — never
`confirmation: true`:

```yaml
confirmation:
  text: "Close the garage door?"
```

Required for: lock/unlock, garage open/close, consumable resets, anything that turns off a
device someone may be using.

---

## 13. Mirror & Maintenance

| Artifact | Repo path | Authority | Deploy |
|---|---|---|---|
| Dashboard config | `ha/dashboards/<url_path>.yaml` | HA | Export via `ha_config_get_dashboard` after every change |
| Jinja macros | `ha/custom_templates/<name>.jinja` | Repo | `scp` to `/config/custom_templates/`, then `homeassistant.reload_custom_templates` |
| Bubble modules | `ha/bubble_modules/<id>.yaml` | Repo | `scp` to `/config/bubble_card/modules/`, then reload the dashboard |

Don't edit modules in the Bubble module editor — the repo copy is the source.

---

## 14. Quick Reference

| Pattern | Implementation | Section |
|---|---|---|
| Navigation | Navbar Card template `main`; views stay visible | §4 |
| Hide header | `kiosk_mode: {hide_header: true}`; `?disable_km` to edit | §4 |
| Chip strip | `sub-buttons`, 2 centred rows, neutral chips, icon colour | §7 |
| Alert chip | `css_class` + Jinja icon colour in `styles` | §7, §10 |
| Room tile | Bubble `button`; tap → pop-up, hold → primary light; ≤ 2 primary sub-buttons | §8 |
| Room eligibility | Controllable from the dashboard more than occasionally | §8.1 |
| Light count | Shared macro with `reject('is_hidden_entity')` | §8.2, §9.2 |
| Pop-up | `pop-up`, `popup_mode: adaptive-dialog`, `popup_style: bubble` | §5 |
| Dynamic text/icon | Quoted Jinja | §9.1 |
| Shared logic / look | `custom_templates` macro / Bubble module | §9.2 |
| No sliders on lights | Adaptive Lighting owns brightness | §2 |
| Confirmation | `confirmation: {text: ...}` | §12 |
