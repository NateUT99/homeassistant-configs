# Gas Fireplace Thermostat
*Last updated: October 2026*

---

## Overview

The living room gas fireplace is exposed to HA as a thermostat — Fireplace
(`climate.living_room_fireplace`) — so it can be set to a target temperature and shown
alongside the house thermostat. A Third Reality Zigbee plug energises a relay that closes the
fireplace's call-for-heat circuit; that relay is the fireplace's only on/off control. A
Generic Thermostat helper cycles the relay against the living room temperature, through a
template switch that refuses to close the relay while no one is home or everyone is asleep.
A companion automation turns the fireplace off on departure, at bedtime, and after 4 hours
of continuous running.

---

## Architecture

```
sensor.living_room_thermostat_temperature
            │
            ▼
┌───────────────────────────────┐
│ climate.living_room_fireplace │  Generic Thermostat (heat / off)
└───────────────┬───────────────┘
                │ turn_on / turn_off
                ▼
┌─────────────────────────────────────────────┐
│ switch.living_room_fireplace_call_for_heat  │  Template switch — turn_on gated on
└───────────────┬─────────────────────────────┘  someone home AND not everyone asleep
                │
                ▼
┌───────────────────────────────┐
│ switch.living_room_fireplace  │  ZHA plug → relay → fireplace call-for-heat
└───────────────────────────────┘
                ▲
                │ off only
┌───────────────┴─────────────────────────────┐
│ automation.living_room_fireplace_auto_off   │  leave / sleep / 4-hour limit /
└─────────────────────────────────────────────┘  turned on while away or asleep
```

### Design decisions

- **The relay is the only control, so HA state is ground truth.** The fireplace has no
  remote or manual switch of its own, so the climate entity's state always matches what the
  fireplace is doing. Power metering on the plug only measures the relay's own draw and
  cannot confirm the burner is lit.
- **A template switch gates the relay instead of reacting after it closes.** An automation
  can only turn the heater back off after the thermostat has already closed it (`LESSONS.md`
  — *An automation can't veto a Generic Thermostat's heater*). The template switch's
  `turn_on` action stops before the relay when the house is empty or asleep, so the relay
  never closes.
- **The auto-off automation stays alongside the gate.** The gate prevents the relay closing;
  the automation also moves the thermostat out of heat mode (so the UI reflects reality) and
  pushes a notification saying why. It acts on the real relay directly, since it only ever
  opens it.
- **10-minute minimum cycle.** A gas fireplace has an ignition sequence and blower delay;
  short cycles waste gas and wear the valve and igniter.
- **4-hour runtime limit applies even when someone is home.** It bounds an unattended run if
  the household simply forgets the fireplace is on.
- **The real relay is hidden and not exposed to Assist.** Any direct control of
  `switch.living_room_fireplace` bypasses the gate; voice and dashboard control go through
  the thermostat.

---

## Prerequisites

- Fireplace (`switch.living_room_fireplace`) — Third Reality 3RSP02064Z plug on ZHA, wired
  to the relay that closes the fireplace's call-for-heat circuit
- Thermostat Temperature (`sensor.living_room_thermostat_temperature`)
- Everyone Sleeping (`input_boolean.everyone_sleeping`) and `zone.home` — see
  `guides/presence_tracking.md`

---

## Steps

### Step 1 — Configure the plug

| Entity | Setting | Why |
|---|---|---|
| `switch.living_room_fireplace` | Hidden; Assist exposure off | Direct control bypasses the gate |
| `switch.living_room_fireplace` | No `no_one_home` / `sleeping` labels | Broadcast turn-offs would fight the thermostat; the auto-off automation owns these cases |
| `select.living_room_fireplace_power_on_behavior` | `Off` | After a power cut the relay stays open rather than relighting the fireplace unattended |
| `switch.living_room_fireplace_metering_only_mode` | Off | Metering-only mode would stop the relay switching |

Hide the switch — do not disable it. The template switch and automation both need it.

### Step 2 — Create the call-for-heat template switch

**Settings → Devices & Services → Helpers → Create Helper → Template → Switch**, named
`Fireplace Call for Heat`. Rename the entity to `switch.living_room_fireplace_call_for_heat`,
set the area to Living Room, hide it, and turn Assist exposure off.

State template:

```yaml
{{ is_state('switch.living_room_fireplace', 'on') }}
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
    entity_id: switch.living_room_fireplace
```

Turn-off actions:

```yaml
- alias: Open the fireplace relay
  action: switch.turn_off
  target:
    entity_id: switch.living_room_fireplace
```

> **Coordinated change:** the gate conditions match the block conditions in
> `automation.living_room_fireplace_auto_off`. If the definition of "unattended" changes in
> one, update the other to match.

### Step 3 — Create the Generic Thermostat

**Settings → Devices & Services → Helpers → Create Helper → Generic thermostat**, named
`Fireplace`, area Living Room. Confirm the entity ID is `climate.living_room_fireplace` and
rename it if not (see `LESSONS.md` — *A helper named with its room and assigned that area at
creation gets the room twice in its entity ID*).

| Field | Value |
|---|---|
| Heater | `switch.living_room_fireplace_call_for_heat` |
| Sensor | `sensor.living_room_thermostat_temperature` |
| AC mode | Off |
| Minimum cycle duration | 10 minutes |
| Cold tolerance | 0.5 |
| Hot tolerance | 0.5 |
| Minimum temperature | 60 |
| Maximum temperature | 80 |

Set the entity icon to `mdi:fireplace`. The first target defaults to the minimum (60 °F), so
the fireplace will not light until the target is raised above room temperature.

### Step 4 — Create the auto-off automation

Living Room: Fireplace Auto Off (`automation.living_room_fireplace_auto_off`) — mirrored at
`ha/automations/automation.living_room_fireplace_auto_off.yaml`. Category Climate, area
Living Room, labels `notification` and `presence`.

| Trigger | Action |
|---|---|
| Everyone leaves (`zone.home` → `0`) | Thermostat off, relay open, push |
| Everyone asleep (`input_boolean.everyone_sleeping` → on) | Thermostat off, relay open, push |
| Heat mode, or relay closed, for 4 hours | Thermostat off, relay open, push |
| Heat mode set, or relay closed, while no one is home or everyone is asleep | Thermostat off, relay open, "Fireplace Blocked" push |

A shared condition skips every branch when the fireplace is already off, so departures and
bedtimes with the fireplace off send nothing.

---

## Safety Summary

| Risk | Control |
|---|---|
| Fireplace left running when everyone leaves or goes to sleep | Auto-off on the `zone.home` → `0` and `everyone_sleeping` → on edges |
| Fireplace turned on remotely while the house is empty or asleep | Template switch gate (relay never closes) plus auto-off block branch |
| Fireplace forgotten while someone is home | 4-hour runtime limit |
| HA restart restores heat mode while away or asleep | Block branch fires on the restored `heat` state; the gate refuses the relay |
| Power cut while running | Plug power-on behavior `Off` |
| Direct relay control bypassing the gate | Relay hidden and unexposed to Assist; no automation or dashboard targets it except the auto-off |
| Rapid cycling of the gas valve | 10-minute minimum cycle; ±0.5 °F tolerance |
| HA down or the Zigbee link lost with the relay closed | **Not covered** — see Deferred |

The 4-hour `for:` timers reset on an HA restart, so a restart mid-run extends that run by up
to another 4 hours.

---

## Related HA Config

| Friendly name | Entity ID | Type |
|---|---|---|
| Fireplace | `climate.living_room_fireplace` | Generic Thermostat helper |
| Fireplace Call for Heat | `switch.living_room_fireplace_call_for_heat` | Template switch helper |
| Fireplace | `switch.living_room_fireplace` | ZHA plug (relay) |
| Living Room: Fireplace Auto Off | `automation.living_room_fireplace_auto_off` | Automation |

---

## Related Documents

- `guides/presence_tracking.md` — `zone.home` and `input_boolean.everyone_sleeping`, which
  define "unattended" for the gate and the automation
- `guides/home_dashboard.md` — the `#climate` pop-up and Fireplace chip

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Heat mode on, fireplace not lit, `hvac_action: idle` | Target is at or below room temperature |
| Heat mode flips straight back to off with a "Fireplace Blocked" push | No one is home, or `everyone_sleeping` is still on. A stale `everyone_sleeping` clears at 9 AM via `automation.household_clear_stale_sleeping_mode` |
| Fireplace blocked every morning | `everyone_sleeping` is not being turned off on wake |

---

## Deferred

- **Device-side failsafe for HA outages.** The plug's `number.living_room_fireplace_countdown_to_turn_off`
  could cap each relay closure on the plug itself, independent of HA. Its behavior across
  repeated thermostat cycles is untested.
- **Dashboard card.** A Bubble Card climate card in the mobile dashboard's `#thermostat`
  pop-up.
