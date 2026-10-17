# Gas Fireplace
*Last updated: October 2026*

---

## Overview

The living room gas fireplace is mostly decorative, so HA treats it as a plain on/off switch —
Fireplace (`switch.living_room_fireplace`). A Third Reality Zigbee plug energises a relay
that closes the fireplace's call-for-heat circuit; that relay is the fireplace's only on/off
control. The user-facing switch is a template switch that refuses to close the relay while no
one is home or everyone is asleep. A companion automation turns the fireplace off on
departure, at bedtime, and after 4 hours of continuous running.

---

## Architecture

```
dashboard · Assist · Apple Home (MatterHub)
            │
            ▼
┌───────────────────────────────┐
│ switch.living_room_fireplace  │  Template switch — turn_on gated on
└───────────────┬───────────────┘  someone home AND not everyone asleep
                │
                ▼
┌─────────────────────────────────────┐
│ switch.living_room_fireplace_relay  │  ZHA plug → relay → fireplace call-for-heat
└─────────────────────────────────────┘
                ▲
                │ off only
┌───────────────┴─────────────────────────────┐
│ automation.living_room_fireplace_auto_off   │  leave / sleep / 4-hour limit /
└─────────────────────────────────────────────┘  turned on while away or asleep
```

### Design decisions

- **A switch, not a thermostat.** The fireplace is for ambiance. Cycling it against room
  temperature would put the flame out once the room warmed up, which is the opposite of what
  it is for. On means lit until someone turns it off or the auto-off fires.
- **The relay is the only control, so HA state is ground truth.** The fireplace has no
  remote or manual switch of its own, so the switch state always matches what the fireplace
  is doing. Power metering on the plug only measures the relay's own draw and cannot confirm
  the burner is lit.
- **A template switch gates the relay instead of reacting after it closes.** An automation
  can only turn the relay back off after it has already closed (`LESSONS.md` — *An
  automation can't veto a Generic Thermostat's heater* describes the same race). The template
  switch's `turn_on` action stops before the relay when the house is empty or asleep, so the
  relay never closes. Every control surface — dashboard, Assist, Apple Home — goes through it.
- **The auto-off automation stays alongside the gate.** The gate prevents the relay closing;
  the automation turns off a fireplace already running when the house empties or goes to
  sleep, enforces the runtime limit, and pushes a notification saying why. It acts on the
  real relay directly, since it only ever opens it.
- **4-hour runtime limit applies even when someone is home.** It bounds an unattended run if
  the household simply forgets the fireplace is on.
- **Hold to light, tap to turn off.** Dashboard controls need a long press to turn the
  fireplace on, so a stray tap can only ever turn it off.

---

## Prerequisites

- Third Reality 3RSP02064Z plug on ZHA (device name `Fireplace`), wired to the relay that
  closes the fireplace's call-for-heat circuit
- Everyone Sleeping (`input_boolean.everyone_sleeping`) and `zone.home` — see
  `guides/presence_tracking.md`
- MatterHub app with the `matterhub` label, for Apple Home exposure

---

## Steps

### Step 1 — Configure the plug

Rename the plug's switch entity to `switch.living_room_fireplace_relay`, name `Fireplace
Relay`, so the plain `switch.living_room_fireplace` ID is free for the gated switch.

| Entity | Setting | Why |
|---|---|---|
| `switch.living_room_fireplace_relay` | Hidden; Assist exposure off; no `matterhub` label | Direct control bypasses the gate |
| `switch.living_room_fireplace_relay` | No `no_one_home` / `sleeping` labels | The auto-off automation owns these cases |
| `select.living_room_fireplace_power_on_behavior` | `Off` | After a power cut the relay stays open rather than relighting the fireplace unattended |
| `switch.living_room_fireplace_metering_only_mode` | Off | Metering-only mode would stop the relay switching |

Hide the relay — do not disable it. The template switch and automation both need it.

### Step 2 — Create the Fireplace template switch

**Settings → Devices & Services → Helpers → Create Helper → Template → Switch**. Rename the
entity to `switch.living_room_fireplace`, name `Fireplace`, icon `mdi:fireplace`, area Living
Room. Leave it visible, expose it to Assist, and add the `matterhub` label so it appears in
Apple Home.

State template:

```yaml
{{ is_state('switch.living_room_fireplace_relay', 'on') }}
```

Turn-on actions — the two condition steps end the sequence before the relay when either
fails:

```yaml
- alias: Someone is home
  condition: numeric_state
  entity_id: zone.home
  above: 0
- alias: Not everyone is asleep
  condition: state
  entity_id: input_boolean.everyone_sleeping
  state: "off"
- alias: Close the fireplace relay
  action: switch.turn_on
  target:
    entity_id: switch.living_room_fireplace_relay
```

Turn-off actions:

```yaml
- alias: Open the fireplace relay
  action: switch.turn_off
  target:
    entity_id: switch.living_room_fireplace_relay
```

The template helper stores these entity IDs in its config entry, so renaming the relay does
not update them — edit the helper's options after any relay rename.

> **Coordinated change:** the gate conditions match the block conditions in
> `automation.living_room_fireplace_auto_off`. If the definition of "unattended" changes in
> one, update the other to match.

### Step 3 — Create the auto-off automation

Living Room: Fireplace Auto Off (`automation.living_room_fireplace_auto_off`) — mirrored at
`ha/automations/automation.living_room_fireplace_auto_off.yaml`. Category Climate, area
Living Room, labels `notification` and `presence`.

| Trigger | Action |
|---|---|
| Everyone leaves (`zone.home` → `0`) | Relay open, push |
| Everyone asleep (`input_boolean.everyone_sleeping` → on) | Relay open, push |
| Relay closed for 4 hours | Relay open, push |
| Relay closed while no one is home or everyone is asleep | Relay open, "Fireplace Blocked" push |

A shared condition skips every branch when the relay is already open, so departures and
bedtimes with the fireplace off send nothing.

### Step 4 — Dashboard controls

Three `home-main` cards control `switch.living_room_fireplace`, all with hold → `turn_on`,
tap → `turn_off`, double-tap disabled (see `guides/home_dashboard.md`):

- Home view, Living Room section — an `apple_tile` tile beside Ceiling Light and Fan
- `#hvac` and `#living-room` pop-ups — a tile styled like the thermostat hero, showing
  `On · shuts off in 3h 12m` (time left on the 4-hour limit) or `Off · hold to light`

---

## Safety Summary

| Risk | Control |
|---|---|
| Fireplace left running when everyone leaves or goes to sleep | Auto-off on the `zone.home` → `0` and `everyone_sleeping` → on edges |
| Fireplace turned on remotely (dashboard, Assist, Apple Home) while the house is empty or asleep | Template switch gate (relay never closes) plus auto-off block branch |
| Fireplace forgotten while someone is home | 4-hour runtime limit |
| Relay restored on after an HA restart while away or asleep | Block branch fires on the relay's `on` edge |
| Accidental tap on a dashboard control | Turning on needs a long press |
| Power cut while running | Plug power-on behavior `Off` |
| Direct relay control bypassing the gate | Relay hidden, unexposed to Assist and Apple Home; nothing targets it except the template switch and the auto-off |
| HA down or the Zigbee link lost with the relay closed | **Not covered** — see Deferred |

The 4-hour `for:` timer resets on an HA restart, so a restart mid-run extends that run by up
to another 4 hours.

---

## Related HA Config

| Friendly name | Entity ID | Type |
|---|---|---|
| Fireplace | `switch.living_room_fireplace` | Template switch helper |
| Fireplace Relay | `switch.living_room_fireplace_relay` | ZHA plug (relay) |
| Living Room: Fireplace Auto Off | `automation.living_room_fireplace_auto_off` | Automation |

---

## Related Documents

- `guides/presence_tracking.md` — `zone.home` and `input_boolean.everyone_sleeping`, which
  define "unattended" for the gate and the automation
- `guides/home_dashboard.md` — the `#hvac` and `#living-room` pop-ups and the Living Room
  section

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Turning the fireplace on does nothing, no push | The gate refused: no one is home, or `everyone_sleeping` is on. A stale `everyone_sleeping` clears at 9 AM via `automation.household_clear_stale_sleeping_mode` |
| Fireplace comes on then straight back off with a "Fireplace Blocked" push | The relay closed while unattended without going through the gate (direct relay control) |
| Fireplace blocked every morning | `everyone_sleeping` is not being turned off on wake |

---

## Deferred

- **Device-side failsafe for HA outages.** The plug's `number.living_room_fireplace_countdown_to_turn_off`
  could cap each relay closure at 4 hours on the plug itself, independent of HA. With no
  thermostat cycling the relay, one closure is one run, so this maps directly onto the
  runtime limit.
