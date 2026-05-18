# CLAUDE.md

This file defines the project context, conventions, and working preferences Claude should follow when assisting with this repository.

---

## Project Overview

This repository is the version-controlled home for documentation, standards, and supporting scripts for a personal Home Assistant instance. It is **not** a complete mirror of HA — see [Source of Truth](#source-of-truth) below.

The repository serves three purposes:

1. **Reference standards** that govern how the HA instance is structured (see `standards/naming.md`)
2. **Implementation guides** for custom integrations, written for the author's future reference and for sharing in HA community forums
3. **Supporting scripts** that aren't UI-editable and live outside HA's entity registry (shell scripts, complex templates)

The author has a security engineering background; security controls in any proposed implementation should be thorough, scoped to least privilege, and clearly explained — never glossed over.

---

## Source of Truth

**HA is the live runtime.** The entity registry, area registry, device assignments, and operational state all live in HA and are read live via the Home Assistant MCP server.

**The repo is the disaster recovery artifact.** For any configuration created or modified in our workflow, the repo maintains enough to fully rebuild the HA instance from scratch. This means:

- Implementation guides contain complete, copy-pasteable YAML for automations, scripts, `configuration.yaml` entries, and template definitions — not design excerpts
- Shell scripts invoked by HA `shell_command` integrations live in `scripts/` as the authoritative source
- Changes to HA and the repo happen in the same session and are kept in sync

**Sync discipline:** When we make changes together, the repo is updated in the same commit. When you make changes in the HA UI between sessions, bring those changes back to the relevant guide before the end of the next session.

When a guide references a HA-resident artifact by name, use the format:

> Friendly Name (`entity_id`)

For example: *Water Leak Alerting (`automation.water_leak_alerting`)*.

This gives a human-readable handle while preserving the machine identifier needed to query HA directly.

**Migration scope:** The repo is not retroactively mirroring everything from HA. Only artifacts touched as part of work going forward are added. Don't propose bulk dumps of existing HA state into the repo.

---

## Environment Context

- **HA instance:** Home Assistant OS on Home Assistant Green
- **Primary Mac:** Mac Mini running macOS (always-on), referenced as `mac-mini`; secondary MacBook Pro
- **HA Companion App** is installed on Mac Mini, MacBook Pro, and iPhone
- **Zigbee devices** are managed via Zigbee2MQTT (Sonoff EFR32MG24 coordinator) on channel 11
- **Hue devices** are managed via the Hue bridge on channel 20 (cleanly separated from Z2M)
- **Matter/HomeKit bridging** via Matter Hub (RiDDiX fork) add-on
- **Notification targets:** `notify.mobile_app_nates_iphone`, `notify.mobile_app_nate_s_mac_mini`, `notify.mobile_app_nates_macbook_pro`
- **Media targets:** HomePods in kitchen and master bedroom for TTS announcements

For current migration progress, settled areas, and the state of in-flight work, ask the author or read recent commits — this file intentionally does not track state that changes.

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

## Automation & YAML Conventions

These conventions apply to all automations, scripts, and templates in this repo (including those that live in HA but are designed or modified through this repo's workflow). They are firm standards, not suggestions.

### Aliases everywhere

Every trigger, condition, action, `choose` branch, and `repeat` block gets an `alias` field. Aliases make automations readable in the HA UI trace view and make debugging far easier.

```yaml
trigger:
  - alias: "Motion detected in office"
    platform: state
    entity_id: binary_sensor.office_motion
    to: "on"
condition:
  - alias: "Only during work hours"
    condition: time
    after: "08:00:00"
    before: "18:00:00"
action:
  - alias: "Turn on key light"
    service: light.turn_on
    target:
      entity_id: light.office_key_light
```

### Parallel vs. sequential actions

- Use **parallel blocks** for independent actions where ordering doesn't matter and concurrent execution is faster.
- Use **sequential ordering** when actions depend on each other or when perceptible-impact actions should fire first and background housekeeping should fire last.

### Choose blocks

- Every `choose` branch gets an `alias` describing the condition it handles.
- Include a `default` branch with an alias when the absence of a match is meaningful; omit it when no action is the intended outcome.

### Guards on restoration branches

Automations that restore a prior state (e.g., turning a thermostat back on after a door closes) should verify the current state before restoring. Don't assume that because the automation turned something off, it can blindly turn it back on — the user may have changed it in the interim.

### Templated entity IDs in conditions

`condition: state` does not accept templated entity IDs. Use `condition: template` with `states()` instead.

```yaml
# Wrong — fails silently
- condition: state
  entity_id: "light.{{ states('input_text.target_light') }}"
  state: "on"

# Right
- condition: template
  value_template: "{{ is_state('light.' ~ states('input_text.target_light'), 'on') }}"
```

### Mode and concurrency

Specify `mode` explicitly on every automation (`single`, `restart`, `queued`, `parallel`). Don't rely on the default. For automations that respond to fast-firing triggers, `restart` is usually correct; for alert-style automations, `parallel` with `max:` set is safer.

### Inline documentation

- Add a `description` field to every automation explaining what it does and when it fires.
- Use comments above non-obvious lines to explain reasoning.
- Document any "magic numbers" (delays, thresholds) with a comment explaining why that value was chosen.

### Entity targeting

- Prefer label-targeted actions when broadcasting to a group of devices (e.g., `label.all_lights_off`).
- Use `target:` syntax over `data: entity_id:` in service calls — it's the modern form.

---

## Naming Standard

All entity and device naming follows `standards/naming.md`. When proposing new entities or renaming existing ones, that document is the source of truth. If a situation isn't covered, flag the gap rather than improvising — the author will extend the standard.

Key principles to internalize without re-reading every time:

- **Location first** — entity IDs always start with the area
- **No platform names** in entity IDs (no `zigbee_`, `hue_`, etc.)
- **Snake_case for IDs, Title Case for friendly names**
- **Apostrophes dropped** in IDs (`avery_room` not `avery_s_room`)
- **Position qualifiers after object** (`window_left`, not `left_window`)
- **`_lamp` reserved for portable lamps**; `_accent` for decorative backlighting
- **`_sensor` suffix dropped** when implied by the domain

---

## Lessons & Gotchas

Hard-won knowledge about HA quirks, integration behavior, and patterns that didn't work is captured in `LESSONS.md`. Read it before proposing a workaround to something that's "obviously" broken — there's a good chance the workaround is documented there, or the obvious solution was already tried and rejected.

When you discover a new gotcha during work, propose adding it to `LESSONS.md`.

---

## Documentation Standards

Documentation in this repo falls into two distinct types. They have different shapes, different lifecycles, and different conventions. Identify which type a document is before writing or editing it.

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
└── scripts/
    └── <name>.<ext>       ← Shell scripts and non-UI-editable YAML
```

**Root-level meta files** (`README.md`, `CLAUDE.md`, `LESSONS.md`) use `ALLCAPS.md`. These are repo metadata, not content.

**Standards, guides, and scripts** use `snake_case` filenames inside their respective directories. The directory tells you the type; the filename names the topic. Don't prefix filenames with the type (`standards/naming.md`, not `standards/naming_standard.md`).

### Type 1 — Reference Standards (`standards/`)

Rules, conventions, and policies that govern how things in the repo or HA instance are built. Examples: entity naming, automation conventions, security baselines.

**Structure:**

1. **Title and current version** — top of the document
2. **Changelog table** — versioned history (see below)
3. **Purpose & Scope** — what this standard covers and what it does not
4. **Core Principles** — the high-level rules in bullet form
5. **Topical sections** — detailed rules organized by area, with examples
6. **Quick Reference** (if applicable) — a table summarizing the rules for at-a-glance use

**Versioning:**

Reference Standards follow semver-adapted versioning: `MAJOR.MINOR.PATCH`. Bump major for breaking changes that contradict prior versions; bump minor for additive rules or new sections; bump patch for clarifications or examples added inline. Use judgment on what merits a changelog entry — bulk small patches together rather than churning the changelog.

**Changelog format:**

```markdown
| Version | Date | Changes |
|---|---|---|
| 1.1 | April 2026 | Added position qualifier rules for left/right pairs |
| 1.0 | March 2026 | Initial release |
```

Dates use `Month YYYY` granularity.

### Type 2 — Implementation Guides (`guides/`)

Technical reconstruction documents for custom integrations and configurations. Examples: a Litra Glow integration, a water leak alerting setup, a Matter/HomeKit bridge configuration. Written so the author or someone reading along in an HA community forum could fully recreate the build from scratch.

**Structure:**

1. **Title and "Last updated" line** — `*Last updated: Month YYYY*` directly under the title
2. **Overview** — one paragraph describing what the integration does and how it works at a high level
3. **Architecture** — a text-based diagram showing the component chain, followed by a brief explanation of key design decisions
4. **Prerequisites** — bulleted list of required hardware, software, and existing setup
5. **Numbered Steps** — one step per major phase of the implementation, in order
6. **Scale Conversions or Formula Reference** (if applicable) — table documenting any non-obvious math
7. **Security Summary** (if applicable) — table summarizing all security controls applied
8. **Related HA Config** (if applicable) — table of every HA-resident artifact the guide creates, with friendly name, entity_id, and type
9. **Related Files** (if applicable) — table of every on-disk file created or modified, with repo path, deployed location, and purpose; omit if the guide creates no on-disk files
10. **Related Documents** (if applicable) — list of other repo docs this guide depends on, references, or coordinates with
11. **Troubleshooting** (if applicable) — advanced, non-obvious issues only; assume basic troubleshooting (restart, reload, check logs, verify entity exists) has already been done

**Referencing HA-resident artifacts:** Use the *Friendly Name (`entity_id`)* format throughout. Guides include complete, copy-pasteable YAML for every automation, script, and `configuration.yaml` entry they create — this is the disaster recovery record for those artifacts.

**No changelog table.** Implementation Guides describe a build at a point in time. Git history captures what changed and when; the `Last updated` line tells the reader how stale the document might be. Update the date when the build itself changes (not for typo fixes).

### Scripts (`scripts/`)

Files that don't fit the standards/guides model but belong in version control: shell scripts called by HA's `shell_command` integration, complex Jinja templates referenced by multiple automations, packages YAML not managed via the UI.

These files don't have a prescribed structure — they are what they are (a `.sh` file, a `.yaml` snippet). The conventions that apply:

- **Filename matches purpose:** `scripts/litra_dispatch.sh`, not `scripts/script1.sh`
- **Header comment explains intent:** every script starts with a comment block describing what it does, what calls it, and any prerequisites
- **Security-relevant scripts cross-reference their guide:** a comment near the top points to the guide documenting the security model

### Writing style (both doc types)

- Technical and direct — no conversational filler
- Present tense for descriptions, imperative for instructions
- Explain *why* a decision was made, not just *what* was done — especially for non-obvious choices
- Include relevant caveats and gotchas inline where they apply
- Troubleshooting is optional — see structure item 11. Dead ends, abandoned approaches, and historical context still don't belong in guides; git history captures those.

### Coordinated change callouts (Implementation Guides)

When a value, entity ID, or configuration in a guide depends on or coordinates with something configured elsewhere — another integration's baseline, a value shared across multiple automations, an entity controlled by more than one system — add a blockquote callout immediately adjacent to that value (above or below the YAML block or table row):

> **Coordinated change:** `<what the dependency is>`. If `<upstream thing>` changes, update `<this value/section>` to match.

### Code blocks (both doc types)

- Every command the user must run goes in a `bash` code block
- Every configuration snippet goes in a `yaml` code block with correct indentation
- Include comments in code blocks where the purpose of a line is not self-evident
- Do not truncate code — include complete, copy-pasteable blocks

### Placeholders (Implementation Guides)

All environment-specific values must be replaced with clearly marked placeholders. Do not include real IP addresses, usernames, API keys, or device serial numbers.

| Value type | Placeholder format |
|---|---|
| IP addresses | `<mac-mini-ip>`, `<ha-ip>`, etc. |
| macOS username | `<your_username>` |
| SSH public key | `AAAA...your-key...` |

**Exception:** Entity IDs inside HA YAML code (automations, scripts, shell commands, template definitions) retain their actual values. These documents may be used to recreate configurations, and generic placeholders in HA code would make them non-functional.

Reference Standards don't typically need placeholders — they describe rules, not specific environments.

### Formatting (both doc types)

- Use tables for reference data (commands, files, security controls, scale conversions)
- Use `---` horizontal rules between major sections
- Use `>` blockquotes for important notes or caveats within a section
- Avoid bold emphasis mid-paragraph — use it only for UI navigation paths (e.g. **Settings → Devices & Services**)
- Architecture diagrams use plain ASCII/Unicode box-drawing characters; no embedded images

### Security documentation (Implementation Guides)

Any guide for an integration involving network access, credentials, or elevated permissions must include a Security Summary section covering:

- Authentication mechanism
- Access restrictions applied
- Principle of least privilege controls (e.g. sudo scope, SSH key restrictions)
- Worst-case impact if credentials were compromised
