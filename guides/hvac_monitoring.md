# HVAC Daily Usage Tracking

*Last updated: September 2026*

---

## Overview

Tracks daily HVAC runtime, cycle count, and average cycle length for both cooling and
heating, so usage trends and anomalies (rising runtime at constant outdoor temperature,
short-cycling) become visible over time. The thermostat (Aqara Thermostat Hub W200, over
Matter) exposes no runtime sensor of its own — only a live `hvac_action` attribute —
so this derives the history from that attribute via a `history_stats` chain.

## Architecture

```
climate.living_room_thermostat  (hvac_action attribute: cooling / heating / absent)
        │
        ├─ binary_sensor.household_hvac_cooling   template, device_class: running
        └─ binary_sensor.household_hvac_heating
                │
                ├─ history_stats (type: time)   → runtime hours today
                ├─ history_stats (type: count)  → cycles today
                │       │
                │       └─ template sensor → average cycle length (minutes)
```

### Design decisions

**A template binary-sensor layer, not `history_stats` directly on the climate entity.**
`history_stats` matches on entity *state*, and the climate entity's state is the HVAC
mode (`cool`/`heat`/`off`), not the `hvac_action` attribute that reflects whether the
system is actually running. The template binary sensors translate the attribute into a
matchable state.

**`hvac_action` has no `idle` value.** Confirmed from recorder history: the attribute is
present as `cooling`/`heating` while the system runs and is absent entirely otherwise.
Both binary sensors compare with `==`, so a missing attribute correctly evaluates false
for both.

**`history_stats`, not a Riemann `integration` + `utility_meter` chain.** `history_stats`
accepts `state_class: total_increasing`, which for a fixed daily window generates `sum`
long-term statistics — permanently retained past the recorder's ~10-day history purge,
and directly plottable as daily bars. A three-layer helper chain would add nothing.

**A YAML package, not UI helpers.** `state_class` is not exposed in the `history_stats`
config-flow UI, only in YAML — and YAML keeps the definition under version control.

**Heating and cooling are tracked and reported separately, never summed.** The system is
a gas furnace paired with central AC: heating runtime is a gas proxy (plus a small
electric blower component), cooling runtime is electric. They measure different fuels.

**No cost sensors.** CT clamps (e.g. Emporia Vue) on the condenser and air handler are
planned, which will yield true kWh per circuit. Runtime-based cost estimation would be
thrown away at that point, so it isn't built now. The whole-home Rainforest EAGLE-3
(`guides/energy_monitoring.md`) reads the revenue meter only and cannot decompose the
HVAC load in the meantime.

## Prerequisites

- A `climate` entity that exposes `hvac_action` when actively heating/cooling
- `homeassistant: packages: !include_dir_named packages` already present in
  `configuration.yaml` (established by `guides/litra_glow.md`)

## Steps

1. Add `ha/packages/hvac_monitoring.yaml` (below) to the HA host.

```yaml
# ha/packages/hvac_monitoring.yaml (deployed to /config/packages/hvac_monitoring.yaml)
template:
  - binary_sensor:
      - name: "Household HVAC Cooling"
        unique_id: household_hvac_cooling
        device_class: running
        availability: "{{ has_value('climate.living_room_thermostat') }}"
        state: "{{ state_attr('climate.living_room_thermostat', 'hvac_action') == 'cooling' }}"
      - name: "Household HVAC Heating"
        unique_id: household_hvac_heating
        device_class: running
        availability: "{{ has_value('climate.living_room_thermostat') }}"
        state: "{{ state_attr('climate.living_room_thermostat', 'hvac_action') == 'heating' }}"
  - sensor:
      - name: "Household HVAC Cooling Average Cycle Today"
        unique_id: household_hvac_cooling_average_cycle_today
        unit_of_measurement: min
        state_class: measurement
        availability: "{{ states('sensor.household_hvac_cooling_cycles_today') | int(0) > 0 }}"
        state: >-
          {% set cycles = states('sensor.household_hvac_cooling_cycles_today') | int(1) %}
          {% set hours = states('sensor.household_hvac_cooling_runtime_today') | float(0) %}
          {{ (hours * 60 / cycles) | round(1) }}
      - name: "Household HVAC Heating Average Cycle Today"
        unique_id: household_hvac_heating_average_cycle_today
        unit_of_measurement: min
        state_class: measurement
        availability: "{{ states('sensor.household_hvac_heating_cycles_today') | int(0) > 0 }}"
        state: >-
          {% set cycles = states('sensor.household_hvac_heating_cycles_today') | int(1) %}
          {% set hours = states('sensor.household_hvac_heating_runtime_today') | float(0) %}
          {{ (hours * 60 / cycles) | round(1) }}

sensor:
  - platform: history_stats
    name: "Household HVAC Cooling Runtime Today"
    unique_id: household_hvac_cooling_runtime_today
    entity_id: binary_sensor.household_hvac_cooling
    state: "on"
    type: time
    start: "{{ today_at() }}"
    duration:
      hours: 24
    state_class: total_increasing
  - platform: history_stats
    name: "Household HVAC Heating Runtime Today"
    unique_id: household_hvac_heating_runtime_today
    entity_id: binary_sensor.household_hvac_heating
    state: "on"
    type: time
    start: "{{ today_at() }}"
    duration:
      hours: 24
    state_class: total_increasing
  - platform: history_stats
    name: "Household HVAC Cooling Cycles Today"
    unique_id: household_hvac_cooling_cycles_today
    entity_id: binary_sensor.household_hvac_cooling
    state: "on"
    type: count
    start: "{{ today_at() }}"
    duration:
      hours: 24
    state_class: total_increasing
  - platform: history_stats
    name: "Household HVAC Heating Cycles Today"
    unique_id: household_hvac_heating_cycles_today
    entity_id: binary_sensor.household_hvac_heating
    state: "on"
    type: count
    start: "{{ today_at() }}"
    duration:
      hours: 24
    state_class: total_increasing
```

2. Restart Home Assistant. The `template:` platform reloads via `template.reload` or
   `homeassistant.reload_all`, but `history_stats` (a legacy `sensor:` platform) does
   not support any reload path — a full restart is required for the four `history_stats`
   sensors to appear.

Since these are not device-attached (no host device to inherit an area from), and the
`name` fields already carry the `household_` scope prefix directly, HA's slugified
entity_ids match the target names with no post-creation registry fix needed — unlike the
area-less case in `guides/generac.md`.

## Formula Reference

Average cycle length (minutes) = runtime hours × 60 ÷ cycle count, computed per mode:

| Sensor | Formula |
|---|---|
| `sensor.household_hvac_cooling_average_cycle_today` | `cooling_runtime_today (h) × 60 ÷ cooling_cycles_today` |
| `sensor.household_hvac_heating_average_cycle_today` | `heating_runtime_today (h) × 60 ÷ heating_cycles_today` |

Both report `unavailable` before the first cycle of the day, rather than dividing by zero.

## Related HA Config

| Friendly Name | entity_id | Type |
|---|---|---|
| Household HVAC Cooling | `binary_sensor.household_hvac_cooling` | Template sensor (this guide) |
| Household HVAC Heating | `binary_sensor.household_hvac_heating` | Template sensor (this guide) |
| Household HVAC Cooling Runtime Today | `sensor.household_hvac_cooling_runtime_today` | `history_stats` (this guide) |
| Household HVAC Heating Runtime Today | `sensor.household_hvac_heating_runtime_today` | `history_stats` (this guide) |
| Household HVAC Cooling Cycles Today | `sensor.household_hvac_cooling_cycles_today` | `history_stats` (this guide) |
| Household HVAC Heating Cycles Today | `sensor.household_hvac_heating_cycles_today` | `history_stats` (this guide) |
| Household HVAC Cooling Average Cycle Today | `sensor.household_hvac_cooling_average_cycle_today` | Template sensor (this guide) |
| Household HVAC Heating Average Cycle Today | `sensor.household_hvac_heating_average_cycle_today` | Template sensor (this guide) |

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/packages/hvac_monitoring.yaml` | `/config/packages/hvac_monitoring.yaml` on the HA host | Runtime/cycle template and `history_stats` sensors |

## Related Documents

- `guides/energy_monitoring.md` — whole-home electricity monitoring; the EAGLE-3 cannot
  isolate the HVAC load, which is why this guide exists as a separate, indirect signal
- `standards/naming.md` §274 — `household_` scope prefix for entities not tied to one area

## Troubleshooting

**Runtime and cycle counts read `0` all day despite the system running.** Confirm
`climate.living_room_thermostat`'s `hvac_action` attribute is actually populated during
a call for heat/cool — check via `ha_get_state` while the system is actively running. A
firmware update or re-pairing could change or drop the attribute.

**Heating sensors are unverified.** All values above were confirmed against live cooling
data; heating runtime/cycles/average depend on `hvac_action: heating` being reported the
same way, which hasn't yet been observed on this thermostat. Check on the first day the
furnace runs.

**Accuracy limits.** Runtime hours assume constant draw for the duration of each cycle —
a two-stage or variable-speed system would be misrepresented, though this system is
single-stage. A Matter subscription drop on the thermostat is indistinguishable from
"idle" and will silently undercount runtime for the outage's duration.

## Deferred

- **CT clamps** on the condenser and air handler for true per-circuit kWh, added to the
  Energy Dashboard's individual-devices section once installed.
- **Outdoor-temperature normalization.** Runtime vs. daily mean outdoor temperature is
  the more useful trend signal once enough history accumulates.
  `sensor.outside_home_generator_generac_959903_outdoor_temperature` already produces
  long-term statistics, so no new sensor is needed to build that comparison later.
- **Dashboard surface.** Sensors only for now; HA's built-in History/Statistics panel is
  sufficient until there's enough data to justify designing a dedicated view.
