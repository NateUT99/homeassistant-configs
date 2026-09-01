# Cable Modem Auto-Recovery

*Last updated: September 2026*

## Overview

Power-cycles the cable modem through a smart plug (`switch.utility_room_cable_modem`) when the
internet has been down for 15 minutes, and protects that plug from being switched off by accident.
Recovery is capped at 4 power-cycles per outage plus a circuit breaker; a maintenance override lets
the plug be powered off deliberately without either automation fighting it.

"Internet is down" is read from Firewalla Gold SE System Status
(`binary_sensor.utility_room_firewalla_gold_se_system_status`, the `firewalla_local` integration's
local API) going `unavailable` — the state observed when the WAN drops and the Firewalla stops
responding.

---

## Architecture

```
binary_sensor.utility_room_firewalla_gold_se_system_status
        |  unavailable >= 15 min
        v
automation.household_cable_modem_auto_power_cycle   (mode: single)
        |
        |-- maintenance on? .......... stop
        |-- plug unavailable? ........ push + stop
        |-- counter >= 8? ............ circuit breaker: push + persistent notice + stop
        |
        |-- set input_boolean.utility_room_cable_modem_power_cycle_active   (guard flag)
        |-- persistent notice: "auto-recovery in progress"
        |-- repeat up to 4x:
        |       switch OFF -> 10 s -> switch ON -> wait <= 8 min for `on` -> 2 min buffer
        |       until connectivity back OR 4 attempts used
        |-- clear guard flag, dismiss the in-progress notice
        |-- restored  -> iPhone push
        |-- still down -> iPhone push + persistent notice
        |
        |-- (connectivity `on` for 6 h) -> reset counter, dismiss failure notice, clear guard flag
        |-- (HA start)                  -> clear guard flag

switch.utility_room_cable_modem  ->  off
        v
automation.utility_room_cable_modem_keep_powered   (mode: restart)
        |  stand down if: maintenance on, OR (guard flag on AND recovery automation running)
        |-- wait 20 s, re-check every condition, still off -> switch ON + iPhone push
```

Key decisions:

- **Trigger on `unavailable`, not `off`.** For this connectivity sensor `off` would mean "reachable
  but no WAN"; in practice the Firewalla local API stops answering entirely when the line drops, so
  the entity goes `unavailable`. A 15-minute `for:` rides out DHCP renewals and brief WAN blips and
  outlasts the momentary `unavailable` of an HA restart.
- **4 attempts, then stop.** While the sensor stays `unavailable` the trigger cannot re-fire, so one
  continuous outage produces at most 4 power-cycles (~40 min of cycling, escalation ~55 min after
  the outage began). A genuine recovery followed by a fresh 15-minute outage gets a new budget.
- **Circuit breaker at counter >= 8.** `counter.utility_room_cable_modem_power_cycles` increments on
  every power-cycle and only resets after 6 h of stable `on`. Once it reaches 8 (~two full failed
  outages), the recovery automation escalates instead of cycling — a fault that survives that many
  reboots is not one a reboot fixes.
- **Guard-flag mutex.** The recovery automation raises
  `input_boolean.utility_room_cable_modem_power_cycle_active` around its deliberate power-off so the
  keep-powered guardian ignores it. The guardian also checks the recovery automation's `current`
  attribute, so an HA restart that leaves the flag stuck `on` cannot disable the guardian
  permanently. The recovery automation additionally clears the flag on HA start and after 6 h stable.
- **Guardian delay-and-recheck.** 20 s (must exceed the recovery automation's 10 s power-off), then
  it re-tests every condition, so a quick manual off/on or the recovery power-cycle never trips a
  spurious restore.
- **Maintenance override.** `input_boolean.utility_room_cable_modem_maintenance` on -> both
  automations stand down. Flip it on before cutting power for modem or plug work.

> **Coordinated change:** the recovery power-off is 10 s and the guardian recheck delay is 20 s. If
> the power-off is lengthened, lengthen the guardian delay to stay above it.

---

## Prerequisites

- Firewalla Gold SE on the LAN with the `firewalla_local` integration configured, exposing
  `binary_sensor.utility_room_firewalla_gold_se_system_status`
- A smart plug powering the cable modem, exposed as `switch.utility_room_cable_modem`, with its
  power-on behaviour set to `on` so it self-restores after any power loss
- `notify.nates_iphone` (HA Companion App)

---

## Steps

### 1. Create the helpers

**Settings -> Devices & Services -> Helpers -> Create Helper.** The names below are chosen so the
generated entity ID slugs match; rename the entity ID afterward if a slug differs.

| Helper name | Type | Config | Target entity ID |
|---|---|---|---|
| Cable Modem Maintenance | Toggle | icon `mdi:wrench-clock` | `input_boolean.utility_room_cable_modem_maintenance` |
| Cable Modem Power-Cycle Active | Toggle | icon `mdi:restart-alert` | `input_boolean.utility_room_cable_modem_power_cycle_active` |
| Cable Modem Power-Cycles | Counter | minimum 0, step 1, no maximum, initial 0, restore on | `counter.utility_room_cable_modem_power_cycles` |

### 2. Create the recovery automation

Create Household: Cable Modem Auto Power-Cycle (`automation.household_cable_modem_auto_power_cycle`),
`mode: single`. Category **Maintenance**; labels **Whole Home** and **Notification**; no area.

Triggers (the IDs are consumed by the action `choose`):

| ID | Platform | Entity | Config |
|---|---|---|---|
| `connection_lost` | state | `binary_sensor.utility_room_firewalla_gold_se_system_status` | to `unavailable`, for 15 min |
| `connection_stable` | state | same | to `on`, for 6 h |
| `ha_started` | homeassistant | — | event: start |

Per-branch behaviour is the Architecture diagram above. Full YAML:
`ha/automations/automation.household_cable_modem_auto_power_cycle.yaml`.

### 3. Create the keep-powered guardian

Create Utility Room: Cable Modem Keep Powered (`automation.utility_room_cable_modem_keep_powered`),
`mode: restart`. Category **Maintenance**; label **Notification**; area **Utility Room**.

Trigger: `switch.utility_room_cable_modem` state to `off`. The stand-down conditions and the 20 s
delay-and-recheck are in the Architecture diagram. Full YAML:
`ha/automations/automation.utility_room_cable_modem_keep_powered.yaml`.

### 4. Verify

- Healthy state: toggle `switch.utility_room_cable_modem` off in Developer Tools -> the guardian
  restores it within ~25 s and sends a push.
- Turn on `input_boolean.utility_room_cable_modem_maintenance`, toggle the plug off -> it stays off.
  Turn the override back off when done.
- Rehearse recovery without a real outage: temporarily lower the `connection_lost` trigger `for:` to
  a few seconds (or point it at a spare `input_boolean`), watch one full power-cycle loop in the
  trace, then revert.

---

## Known limitations

- **Notifications cannot leave the house during an outage.** HA pushes through Apple's servers,
  which are unreachable while the WAN is down, and HA does not retry a failed push. The in-progress
  step therefore writes a `persistent_notification` (LAN-visible); the "restored" / "still down"
  pushes are sent after connectivity is decided and deliver then (the "still down" one lands late).
  For a real-time "the house is offline" alert, rely on Firewalla's own app notification (sent from
  its cloud) or an external uptime monitor.
- **Self-recovering outages are still power-cycled.** The outages that prompted this cleared on
  their own in 33–54 minutes; with a 15-minute trigger the automation will power-cycle a similar
  outage before it would have recovered. Raise the trigger `for:` if that is undesirable.
- **The power-cycle is a band-aid.** Repeated power-cycles (watch the counter) point to a line or
  hardware fault — check coax connectors and splitters, have the ISP pull DOCSIS signal and error
  stats, or replace the modem. The durable fix for uptime is WAN failover (the Gold SE supports
  dual-WAN / USB-LTE), not a reboot loop.

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Firewalla Gold SE System Status | `binary_sensor.utility_room_firewalla_gold_se_system_status` | Binary sensor (`firewalla_local`) |
| Cable Modem | `switch.utility_room_cable_modem` | Switch (smart plug) |
| Cable Modem Maintenance | `input_boolean.utility_room_cable_modem_maintenance` | Input boolean helper |
| Cable Modem Power-Cycle Active | `input_boolean.utility_room_cable_modem_power_cycle_active` | Input boolean helper |
| Cable Modem Power-Cycles | `counter.utility_room_cable_modem_power_cycles` | Counter helper |
| Household: Cable Modem Auto Power-Cycle | `automation.household_cable_modem_auto_power_cycle` | Automation |
| Utility Room: Cable Modem Keep Powered | `automation.utility_room_cable_modem_keep_powered` | Automation |

---

## Related Files

| Repo path | Purpose |
|---|---|
| `ha/automations/automation.household_cable_modem_auto_power_cycle.yaml` | Mirror of the recovery automation |
| `ha/automations/automation.utility_room_cable_modem_keep_powered.yaml` | Mirror of the keep-powered guardian |

---

## Related Documents

- `standards/automations.md` — the automation naming, category, and label conventions applied here
