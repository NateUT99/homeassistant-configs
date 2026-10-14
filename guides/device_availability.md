# Device Availability

*Last updated: October 2026*

---

## Overview

Shows which devices have dropped off the network, in one place. A trigger-based template
sensor walks the unavailable entities every minute, groups them by device, and skips
anything expected to be offline. The Availability section at the top of the `home-main`
Maintenance view renders the result, and the navbar's More badge turns red while any device
is fully offline.

## Architecture

```
states (every entity)
   │  unavailable ≥ 5 min, not hidden, no ignore_offline label
   ▼
sensor.household_devices_offline      trigger-based template, every minute + HA start
   │  state      = count of fully offline devices
   │  offline    = [{device_id, name, area, since}]
   │  partial    = [{device_id, name, area, since, entities}]
   │  orphans    = [{entity_id, name, since}]
   │
   ├─ home-main Maintenance view → Availability section (markdown table)
   └─ navbar More + Maintenance badge (red while state > 0)
```

### Design decisions

**Grouped by device, not listed by entity.** A device whose every visible entity is
unavailable has dropped off the network. That is the strong signal, and it goes under
`offline`. A device with only some entities unavailable is usually healthy, with one sensor
that is only available sometimes, so it goes under `partial` and doesn't count toward the
state. Entities with no device (template sensors, helpers) go under `orphans`, so a broken
template still shows up.

**Exclusions are a label, not a list in the template.** `ignore_offline` is applied from
the UI to a device or an entity (`standards/naming.md` §7.6). Hidden entities are skipped
too, so a TV whose only entity is hidden never appears.

**A 5-minute grace period.** An entity counts only once it has been unavailable for 5
minutes. That stops brief network drops and the minutes after a restart from flashing the
section. `since` is the oldest `last_changed` among the device's unavailable entities. HA
resets `last_changed` on restart, so `since` never reaches back past the last restart.

**Refreshed every minute, not on state changes.** A state-based template that reads
`states` re-renders on every state change in the house. A one-minute `time_pattern` trigger
bounds the cost, and only the handful of unavailable entities are walked in detail.

**One `variables` render feeds every field.** The trigger's `action` computes the full
report once, and the state and three attributes read from it, so the grouping logic exists
in one place.

**The navbar badge, not a Home chip.** Home chips cover household status. Maintenance
faults surface on the More badge, alongside updates and generator warnings
(`standards/dashboards.md` §4).

## Prerequisites

- `homeassistant: packages: !include_dir_named packages` already present in
  `configuration.yaml`
- The `ignore_offline` label (Step 1)

## Steps

### 1. Create the label

**Settings → Areas, labels & zones → Labels → Create label:** name *Ignore Offline*, icon
`mdi:eye-off`, colour grey. HA derives the ID `ignore_offline` from the name.

Apply it to:

| Target | Apply to | Current examples |
|---|---|---|
| Entity | A sensor that is only available some of the time, on an otherwise healthy device | iPhone current pace, cadence, in bed; work-laptop Focus |
| Entity | A template sensor that is unavailable by design for part of the day | HVAC average-cycle-today sensors (unavailable before the first cycle) |
| Device | A device that is expected to be offline for long stretches | None yet |

### 2. Deploy the package

```yaml
# ha/packages/device_availability.yaml (deployed to /config/packages/device_availability.yaml)
template:
  - trigger:
      - trigger: time_pattern
        minutes: "/1"
        alias: Recheck every minute
      - trigger: homeassistant
        event: start
        alias: Home Assistant started
    action:
      - variables:
          report: >-
            {%- set grace = 300 -%}
            {%- set ignored = label_entities('ignore_offline') -%}
            {%- set ns = namespace(devs=[], orphans=[], offline=[], partial=[]) -%}
            {%- for s in states | selectattr('state', 'eq', 'unavailable')
                 if s.entity_id not in ignored
                 and not is_hidden_entity(s.entity_id)
                 and (now() - s.last_changed).total_seconds() >= grace -%}
              {%- set d = device_id(s.entity_id) -%}
              {%- if d is none -%}
                {%- set ns.orphans = ns.orphans + [{
                      'entity_id': s.entity_id,
                      'name': s.name,
                      'since': s.last_changed.isoformat()}] -%}
              {%- elif d not in ns.devs and 'ignore_offline' not in labels(d) -%}
                {%- set ns.devs = ns.devs + [d] -%}
              {%- endif -%}
            {%- endfor -%}
            {%- for d in ns.devs -%}
              {%- set live = expand(device_entities(d) | reject('in', ignored)
                    | reject('is_hidden_entity') | list) -%}
              {%- set down = live | selectattr('state', 'eq', 'unavailable') | list -%}
              {%- set item = {
                    'device_id': d,
                    'name': device_attr(d, 'name_by_user') or device_attr(d, 'name'),
                    'area': area_name(d) or '',
                    'since': (down | map(attribute='last_changed') | min).isoformat()} -%}
              {%- if down | count == live | count -%}
                {%- set ns.offline = ns.offline + [item] -%}
              {%- else -%}
                {%- set ns.partial = ns.partial + [dict(item,
                      entities=down | map(attribute='name') | sort | list)] -%}
              {%- endif -%}
            {%- endfor -%}
            {{ {'offline': ns.offline | sort(attribute='area,name'),
                'partial': ns.partial | sort(attribute='area,name'),
                'orphans': ns.orphans | sort(attribute='name')} }}
    sensor:
      - name: "Household Devices Offline"
        unique_id: household_devices_offline
        icon: mdi:lan-disconnect
        state: "{{ report.offline | count }}"
        attributes:
          offline: "{{ report.offline }}"
          partial: "{{ report.partial }}"
          orphans: "{{ report.orphans }}"
```

```bash
scp ha/packages/device_availability.yaml ha:/config/packages/
ssh ha "ha core check"
```

Then run **Developer tools → YAML → Template entities** to reload. The sensor reads
`unknown` until the next minute tick.

### 3. Add the dashboard section

The Availability section is the first expander on the `home-main` Maintenance view
(`guides/home_dashboard.md` §6). It is a single markdown card: a table with a red
`close-circle` row per offline device, an amber `alert-circle` row per partial device (the
unavailable entity names underneath) and per orphan, and the area and time offline on the
right. Each device name links to `/config/devices/device/<id>`. When nothing is offline it
shows one green "All devices online" line. Icon colours come from UIX attribute selectors
(`ha-icon[icon='mdi:alert-circle'] { color: var(--amber-color); }` inside `ha-markdown$`). The heading carries a red count badge while the state
is above 0.

## Triage

| Row | Action |
|---|---|
| Offline device you rely on | Open its device page from the link and fix it: battery, power, or re-pair |
| Offline device that is expected to be offline | Label the device `ignore_offline` |
| Offline device that no longer exists | Remove it from its integration |
| Partial: one sensor that is only available sometimes | Label that entity `ignore_offline` |
| Orphan | Check the template or helper. Label it if it is unavailable by design |

## Related HA Config

| Friendly Name | entity_id | Type |
|---|---|---|
| Household Devices Offline | `sensor.household_devices_offline` | Template sensor (this guide) |
| Ignore Offline | `ignore_offline` | Label |

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/packages/device_availability.yaml` | `/config/packages/device_availability.yaml` on the HA host | The sensor |
| `ha/dashboards/home-main.yaml` | HA dashboard storage (mirror; HA authoritative) | Maintenance view Availability section; navbar badges |

## Related Documents

- `guides/home_dashboard.md` — the Maintenance view and navbar badges
- `standards/naming.md` §7.6 — the `ignore_offline` label
- `standards/dashboards.md` §4 — the navbar badge rule

## Deferred

- **Offline alerts (#17).** An opt-in `alert_offline` label on the devices that matter, plus one
  automation that compares the `offline` attribute against `label_devices('alert_offline')`
  and pushes once per outage past a threshold. Waits on about a week of watching this section
  to learn which devices drop briefly. The fridge-plug alert can move onto it.
