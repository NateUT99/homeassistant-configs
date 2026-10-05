# HA Mirror

This directory contains version-controlled copies of everything that has a real, deployed
location on the HA host: automations, scripts, and dashboards (`automations/`, `scripts/`,
`dashboards/`), and packages and dashboard support files (`packages/`, `custom_templates/`,
`bubble_modules/`). The first group is a **living mirror** — updated in the same session as
any HA change. The second runs the opposite direction — see below.

## Relationship to HA

**For `automations/`, `scripts/`, and `dashboards/`: HA is authoritative.** This directory is downstream.
When the two disagree, HA wins. The mirror exists for:

- **Recovery:** paste a YAML file back into HA after a rebuild, adjusting entity IDs for any room or device changes
- **Diffing:** `git diff` shows exactly what changed in an automation across sessions
- **Audit:** the full history of what an automation looked like at any point in time is preserved in git

**For `packages/`: the repo is authoritative — the reverse direction.** Packages
(template sensors, `history_stats`, and other YAML not manageable via the HA UI config
flow) have no entry in HA's storage registry, so there's nothing for MCP to fetch back.
The file in `ha/packages/` is the source; it's deployed to `/config/packages/<name>.yaml`
on the host via `scp`, then loaded with a config reload or restart (packages aren't
covered by any single reload service — see the relevant guide's Steps section). Update
the file here first, then redeploy — never edit the deployed copy on the host directly.

**`custom_templates/` and `bubble_modules/` follow the same repo-authoritative rule.** Jinja
macros deploy to `/config/custom_templates/` (then `homeassistant.reload_custom_templates`);
Bubble Card modules deploy to `/config/bubble_card/modules/` (then reload the dashboard).
Don't edit modules in the Bubble module editor. See `standards/dashboards.md` §13.

## Relationship to the snapshot

`../snapshot/2026-07-27-pre-move/` is a **frozen archive** of the old apartment instance, captured before the 2026 house move. It is read-only — never modify it. Use it as a reference when rebuilding prior functionality, but do not copy its YAML directly here: entity IDs and area names are from the old house and must be rebuilt fresh.

## Sync rule

Whenever an automation, script, or dashboard is created, modified, or deleted in HA:

1. Export from HA via `ha_config_get_automation`, `ha_config_get_script`, or `ha_config_get_dashboard` (MCP tools)
2. Write or update the corresponding file here
3. Commit the mirror update in the same commit as any guide or standards changes for that automation

Updating the mirror is part of "done" for any automation/script work — don't leave the two out of sync.

## File naming

```
automations/automation.<object_id>.yaml
scripts/script.<object_id>.yaml
dashboards/<url_path>.yaml
packages/<name>.yaml
custom_templates/<name>.jinja
bubble_modules/<id>.yaml
```

The object_id is the entity_id without the domain: `automation.bathroom_ambient_lamp` → `automation.bathroom_ambient_lamp.yaml`. Package filenames match the deployed name under `/config/packages/`.

## What's NOT here

- Helpers and scenes — HA-only or covered by guides
- Throwaway test dashboards (e.g. `home-test`)
- `configuration.yaml` entries — in the relevant guide
- Snapshot files from the old house — in `../snapshot/`
