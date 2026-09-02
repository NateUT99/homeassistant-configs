# CLAUDE.md

This file defines the project context, conventions, and working preferences Claude should follow when assisting with this repository.

---

## Project Overview

This repository is the version-controlled home for documentation, standards, and supporting scripts for a personal Home Assistant instance. It is **not** a complete mirror of HA — see [Source of Truth](#source-of-truth) below.

The repository serves four purposes:

1. **Reference standards** that govern how the HA instance is structured (see `standards/naming.md` for entities, `standards/automations.md` for automations, `standards/documentation.md` for how the docs themselves are written)
2. **Implementation guides** for custom integrations, written for the author's future reference and for sharing in HA community forums
3. **Supporting scripts** that aren't UI-editable and live outside HA's entity registry (shell scripts, complex templates)
4. **Living automation/script mirror** (`ha/`) — version-controlled YAML exports of every automation and script, kept in sync with HA each session

The author has a security engineering background; security controls in any proposed implementation should be thorough, scoped to least privilege, and clearly explained — never glossed over.

---

## Source of Truth

**HA is the live runtime.** The entity registry, area registry, device assignments, and operational state all live in HA and are read live via the Home Assistant MCP server.

**The repo is the design and recovery reference.** HA is the authoritative source for automation and script YAML. The repo documents enough to understand, audit, and recreate each integration. This means:

- **Implementation guides** explain architecture, design decisions, and the rationale behind non-obvious choices. They reference automations and scripts by entity ID; the live YAML is always retrievable via MCP. Guides do **not** embed automation/script YAML — that belongs in `ha/`.
- **`configuration.yaml` entries** (not stored in HA, not retrievable via MCP) are documented in full in the relevant guide — these are the only YAML blocks that belong in a guide.
- **Shell scripts** invoked by HA `shell_command` integrations live in `scripts/` as the authoritative source.
- Changes to HA and the repo happen in the same session and are kept in sync.

**Automation/script mirror (`ha/`):** Every automation and script is also mirrored as YAML in `ha/automations/` and `ha/scripts/`. HA remains authoritative; the mirror is a downstream, human-readable, version-controlled copy used for recovery and diffing. The mirror is updated in the same session as any automation or script change (export via MCP → write file → commit). Updating the mirror is part of "done" for any automation/script work.

**Snapshot (`snapshot/2026-07-27-pre-move/`):** A frozen, read-only point-in-time export from the old apartment captured before the move. It is a rebuild reference — consult it freely when replicating prior functionality. **Never write to it or update it.**

**Sync discipline:** When we make changes together, the repo is updated in the same session. When you make changes in the HA UI between sessions, bring the relevant guide up to date before the end of the next session — architecture notes, org settings, and entity IDs, not YAML.

When a guide references a HA-resident artifact by name, use the format:

> Friendly Name (`entity_id`)

For example: *Water Leak Alerting (`automation.water_leak_alerting`)*.

This gives a human-readable handle while preserving the machine identifier needed to query HA directly.

**Migration scope:** The repo is not retroactively mirroring everything from HA. Only artifacts touched as part of work going forward are added. Don't propose bulk dumps of existing HA state into the repo.

---

## Environment Context

- **HA instance:** Home Assistant OS on Home Assistant Green
- **Primary Mac:** Mac Mini running macOS (always-on), referenced as `mac-mini`; secondary MacBook Pro (referenced as `work-laptop` in HA)
- **HA Companion App** is installed on Mac Mini, work laptop, and iPhone
- **Zigbee devices** are managed via ZHA (USB coordinator; channel TBD)
- **Thread network:** OpenThread Border Router (official core add-on) acts as the Thread border router, registered in the same Thread fabric as the Apple Thread network (HomePods). Thread and Matter-over-Thread devices are reachable from both HA and Apple Home via this shared fabric.
- **Matter support** via the official Matter Server core add-on
- **Notification targets:** `notify.nates_iphone`, `notify.nates_mac_mini`, `notify.nates_work_laptop`
- **TTS media targets:** `media_player.kitchen_homepod`, `media_player.master_bedroom_homepod`, `media_player.office_homepod`, `media_player.averys_room_homepod`

For current rebuild progress, installed integrations, and in-flight work, ask the author or read recent commits — this file intentionally does not track state that changes. Consult `snapshot/2026-07-27-pre-move/` for the full pre-move configuration as a rebuild reference.

---

## Working Preferences

### Decision-making

- **Propose and justify**, don't punt every decision to the author. The author prefers concise, opinionated recommendations with reasoning over "here are five options, which do you want?"
- When tradeoffs are genuinely close or the decision is reversible at low cost, pick one and explain the choice; the author will push back if they disagree.
- When tradeoffs are genuinely complex or hard to reverse, surface the tradeoff briefly and ask before committing.
- Ask clarifying questions when the requirements are ambiguous or when a design choice has implications the author may not have considered.

### Scope of changes

- Make small, focused changes that can be reviewed independently. Avoid sweeping refactors mixed with feature work.
- Migrate incrementally — don't change entity IDs in bulk if it will break running automations. Stage the work.
- When proposing changes that affect multiple files or systems, list the affected components first so the author can scope-check before implementation.

### Output format

- Provide **complete YAML output** for automations and scripts after the design is confirmed. Partial snippets that require manual stitching are error-prone.
- Inline comments explain *why* a non-obvious choice was made, not what the code does.
- Use Markdown for human-readable artifacts; reserve DOCX for documents that must be shared as Word files.

### Suggested model

Tasks in this repo tend to involve reasoning across the repo, HA state, and standards documents simultaneously. The `opusplan` mode (Opus for planning, Sonnet for execution) generally fits well. Plain `sonnet` is sufficient for straightforward edits. The author chooses per session; this is a suggestion, not a default.

---

## HA Access Boundaries

The Home Assistant MCP server provides both read and write tool surfaces. Claude operates under these boundaries:

- **Read operations are unrestricted.** Querying entity state, fetching automations, inspecting the entity registry, reading history and traces, evaluating templates — all proactive and routine.
- **Write operations to HA require explicit confirmation.** Before calling any tool that creates, modifies, or removes automations, scripts, scenes, helpers, dashboards, areas, labels, devices, or zones, or before calling services that change device state, present the proposed change and wait for explicit approval. Never assume permission from earlier in the session.
- **System operations require confirmation regardless of context.** Restarts, reloads, backup creation/restore, integration enable/disable, and any tool that mutates HA system state need explicit approval each time.

Repository writes (commits, pushes, PRs) do not require this confirmation pattern — those are version-controlled, easily reverted, and part of normal workflow. See [Commit Discipline](#commit-discipline) below for how to commit.

---

## Commit Discipline

Be proactive about committing repository changes — work isn't done until it's committed. Don't accumulate unstaged changes across multiple unrelated tasks.

### Granularity

Use a mixed strategy based on the size and nature of the change:

- **Batch small related changes** into a single commit. Three typo fixes across two files, or a doc tweak plus a related code comment update — one commit.
- **Give large or structural changes their own commit.** Renaming a file, restructuring a directory, adding a new standard or guide, or any change that touches multiple sections of a document — separate commit.
- **When in doubt, prefer smaller commits.** A commit history with many focused commits is easier to read and revert than one with sweeping commits.

### Commit messages

Format: a one-line subject (50-72 chars), optionally followed by a blank line and a body explaining *why* the change was made.

**Style:**
- Imperative mood: "Add water leak guide" not "Added" or "Adds"
- Concrete and specific: "Fix entity_id reference in naming standard" not "Fix typo"
- No trailing period on the subject line
- Body explains rationale and context, not what the diff already shows

**Examples:**

```
Add Litra Glow integration guide

Documents the architecture, security model, and SSH dispatch
pattern used to control the Mac-attached key light from HA.
```

```
Move naming standard to standards/ directory

Follows the documentation organization in CLAUDE.md. Filename
changed from HA_Naming_Standard.md to standards/naming.md.
```

```
Fix entity_id placeholder rule in naming standard
```

(No body when the subject is sufficient.)

### Issue references

When a commit resolves an open issue, include `Fixes #N` or `Closes #N` on its own line in the body. GitHub closes the issue automatically on merge to default branch.

### Pushing

Push after each commit unless explicitly working on a sequence of related commits to push together. Don't accumulate unpushed commits across sessions.

---

## Mirror Discipline

The `ha/` directory contains version-controlled YAML mirrors of every automation and script. This is downstream from HA — HA remains authoritative, the mirror is a copy for recovery and diffing.

**What's mirrored:** `ha/automations/` and `ha/scripts/` only. Helpers, scenes, and dashboards are not mirrored (they're either UI-editable in HA or covered by guides).

**File naming:** `automation.<object_id>.yaml` and `script.<object_id>.yaml` — matching the frozen snapshot convention for easy comparison.

**When to update:** Anytime an automation or script is created, modified, or deleted in HA, update the mirror in the same session:
1. Export from HA via `ha_config_get_automation` or `ha_config_get_script`
2. Write/update/delete the corresponding file in `ha/automations/` or `ha/scripts/`
3. Include the mirror update in the same commit as any guide or standards changes for that automation

**What does NOT belong in `ha/`:** Do not write `configuration.yaml` entries, template sensors, or helper definitions here — those belong in the relevant guide or are HA-only artifacts.

**Snapshot boundary:** `snapshot/2026-07-27-pre-move/` is a frozen archive of the old instance. It is a reference, not a mirror. Do not copy snapshot files into `ha/` as-is — the entity IDs and area names are from the old house. When replicating prior functionality, read the snapshot for logic and intent, then build fresh in the new HA and mirror the result.

---

## Issue Tracking

GitHub Issues are an active part of the workflow for this repo. Use them to capture context that doesn't belong in commit messages or `LESSONS.md` — proposed changes under discussion, deferred work, failed approaches with reasoning, and questions awaiting decisions.

### When to open an issue

Apply critical thinking, not a checklist. If during a conversation it becomes clear that something should be tracked — a deferred fix, an architectural question, a proposed change worth discussion before implementation — **say so and ask before opening the issue**. Don't open issues proactively; raise the suggestion and let the author confirm.

Reasonable triggers for *suggesting* an issue:

- A proposed change is large enough that it warrants discussion before implementation
- A bug or limitation is identified but not being fixed in the current session
- A "for later" item comes up that would otherwise be forgotten
- An attempted approach fails and the failure is worth preserving so it isn't retried

When suggesting an issue, briefly describe what the issue would cover and which label fits. Don't draft the full body until the author confirms.

### Labels

Use the labels already present in the GitHub repo. Do not create new labels without asking. Pull the current list from the repo when classifying.

### Closing the loop

When a commit resolves an open issue, reference it in the commit message (`Fixes #N` or `Closes #N`) so GitHub closes it automatically. When work is abandoned, close the issue with a brief comment explaining why rather than leaving it open indefinitely.

### Comments and discussion

Use issue comments for ongoing discussion about an open item. If a conversation in chat covers material that belongs in an issue, propose moving the relevant summary into a comment — the author will confirm before posting.

---

## Automation Standard

All automation naming, organization (categories, labels, area assignment), and YAML content requirements follow `standards/automations.md`. That document is the source of truth. If a situation isn't covered, flag the gap rather than improvising — extend the standard.

Key principles to internalize without re-reading every time:

- **Aliases everywhere** — every trigger, condition, action, choose branch, and repeat block
- **Mode always explicit** — never omit `mode:`
- **Description always present** — what it does, when it fires, why it exists
- **Purpose-based entity IDs** — `area_id`, integration code, or `household` prefix; no trigger-type prefixes
- **7 approved categories** — Lighting, Climate, Security, Person, Entertainment, Routines, Maintenance
- **Labels are orthogonal** — `scope_*` for multi-area; `int_*` for guide-documented integrations; `notification` for any automation that sends a push or TTS notification

---

## Naming Standard

All entity and device naming follows `standards/naming.md`. All automation naming and organization follows `standards/automations.md`. When proposing new entities, renaming existing ones, or creating automations, those documents are the source of truth. If a situation isn't covered, flag the gap rather than improvising — the author will extend the standard.

Key principles to internalize without re-reading every time:

- **Location first** — entity IDs always start with the area; the area registry does not inject the area prefix automatically — it must be in the device Name
- **No platform names** in entity IDs (no `zigbee_`, `hue_`, `homekit_`, etc.)
- **Snake_case for IDs, Title Case for friendly names**
- **Apostrophes dropped** in IDs (`averys_room` not `avery_s_room`)
- **Position qualifiers after object** (`window_left`, not `left_window`)
- **`_lamp` reserved for portable lamps**; `_accent` for decorative backlighting
- **`_sensor` suffix dropped** when implied by the domain
- **Anti-doubling** — when an integration names its device after the room, add a type qualifier to prevent `area_area_*` stutter (see §4.3)
- **Area-less imports** — always rename area-free device Names before anything else (see §4.4)

---

## Lessons & Gotchas

Hard-won knowledge about HA quirks, integration behavior, and patterns that didn't work is captured in `LESSONS.md`. Read it before proposing a workaround to something that's "obviously" broken — there's a good chance the workaround is documented there, or the obvious solution was already tried and rejected.

When you discover a new gotcha during work, propose adding it to `LESSONS.md`.

---

## Documentation Standards

`standards/documentation.md` is the source of truth for how every document in this repo is
structured and written — the two document types (Reference Standards, Implementation Guides),
their required sections, the writing/formatting conventions, and the pre-commit checklist.
Read it before writing or editing any standard or guide.

### Guides document the current state, not the history of the build

This is the rule that keeps getting broken. A guide describes what exists now and how to
rebuild it — nothing more.

- **No build history.** No prior attempts, reverts, "an earlier version…", regressions, or
  old-apartment / pre-move comparisons. Git history holds all of that.
- **Keep the constraint, cut the story.** "Cluster 8 emits no Move/Step at `Instant`, so a
  non-`Instant` value is required" — yes. "`3s` was tried and regressed, so we reverted" — no.
- **Dead ends go in `LESSONS.md`.** The guide links to the lesson; it does not retell it.
- **Every fact appears once**, in the section that owns it. Design Decisions entries are 2–4
  sentences.
- **`Last updated: Month YYYY`** — a bare month, no parenthetical describing what changed.
- Deferred / future-work sections are fine — that is scope, not history.

Full rules, worked examples, and the pre-commit checklist: `standards/documentation.md` §5–§9.

### File organization

```
/
├── README.md              ← Repo intro
├── CLAUDE.md              ← This file
├── LESSONS.md             ← Hard-won gotchas
├── standards/
│   └── <topic>.md         ← Reference Standards
├── guides/
│   └── <topic>.md         ← Implementation Guides
├── scripts/
│   └── <name>.<ext>       ← Shell scripts and non-UI-editable YAML
├── ha/
│   ├── README.md          ← Mirror purpose, sync rule, snapshot distinction
│   ├── automations/
│   │   └── automation.<object_id>.yaml   ← Living mirror, kept in sync
│   └── scripts/
│       └── script.<object_id>.yaml       ← Living mirror, kept in sync
└── snapshot/
    └── 2026-07-27-pre-move/  ← Frozen pre-move export (READ-ONLY — never modify)
```

**Root-level meta files** (`README.md`, `CLAUDE.md`, `LESSONS.md`) use `ALLCAPS.md`. These are repo metadata, not content.

**Standards, guides, and scripts** use `snake_case` filenames inside their respective directories. The directory tells you the type; the filename names the topic. Don't prefix filenames with the type (`standards/naming.md`, not `standards/naming_standard.md`).

Everything else — the required sections for each document type, versioning, coordinated-change callouts, code-block and placeholder rules, security-summary requirements, and the pre-commit checklist — is in `standards/documentation.md`.
