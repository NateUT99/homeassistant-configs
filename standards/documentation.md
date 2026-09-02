# Documentation Standard
*Version 1.0 — September 2026*

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.0 | September 2026 | Initial release. Absorbs the documentation-format content previously inline in `CLAUDE.md`; adds the current-state rule (§5), the rationale-vs-history distinction (§6), the single-owner rule (§7), and length discipline (§8) |

---

## 1. Purpose & Scope

This standard governs every human-readable document in the repo: Reference Standards
(`standards/`), Implementation Guides (`guides/`), supporting files in `scripts/`, and the
root meta files (`README.md`, `CLAUDE.md`, `LESSONS.md`).

It defines each document type's structure, the writing conventions common to all of them,
and — the reason this standard exists as its own document — **what does not belong in a
guide**. Guides written during a buildout tend to accrete the history of the buildout;
§5–§8 draw the line and §9 makes it checkable.

Out of scope: entity/device naming (`standards/naming.md`), automation naming and
organization (`standards/automations.md`), dashboard conventions (`standards/dashboards.md`).

---

## 2. Core Principles

- **A guide documents the current state and how to rebuild it. It is not a record of how
  the build got here.** Git history holds the history. (§5)
- **Rationale is a constraint, not a story.** Keep the reason a value is what it is; cut the
  narrative of how it was found. (§6)
- **Every fact appears once**, in the section that owns it. Everywhere else cites that
  section. (§7)
- **Dead ends live in `LESSONS.md`**, not in guides. A guide links to the lesson; it does
  not retell it. (§7)
- Identify the document type before writing or editing — the types have different shapes and
  lifecycles.
- Technical and direct. Present tense for descriptions, imperative for instructions.
- Explain *why* a non-obvious choice was made — within the length limits in §8.

---

## 3. Document Types

### 3.1 File organization

```
/
├── README.md              ← Repo intro
├── CLAUDE.md              ← Project context and working preferences
├── LESSONS.md             ← Hard-won gotchas, dead ends, integration quirks
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

**Root-level meta files** (`README.md`, `CLAUDE.md`, `LESSONS.md`) use `ALLCAPS.md` — they
are repo metadata, not content.

**Standards, guides, and scripts** use `snake_case` filenames inside their directories. The
directory tells you the type; the filename names the topic. Don't prefix the filename with
the type (`standards/naming.md`, not `standards/naming_standard.md`).

### 3.2 Type 1 — Reference Standards (`standards/`)

Rules, conventions, and policies that govern how things in the repo or HA instance are
built. Examples: entity naming, automation conventions, this document.

**Structure:**

1. **Title and current version** — top of the document
2. **Changelog table** — versioned history (see below)
3. **Purpose & Scope** — what this standard covers and what it does not
4. **Core Principles** — the high-level rules in bullet form
5. **Topical sections** — detailed rules organized by area, with examples
6. **Quick Reference** (if applicable) — a table or checklist summarizing the rules for
   at-a-glance use

**Versioning:** semver-adapted `MAJOR.MINOR.PATCH`. Bump major for breaking changes that
contradict prior versions; minor for additive rules or new sections; patch for
clarifications or inline examples. Bulk small patches together rather than churning the
changelog.

**Changelog format:**

```markdown
| Version | Date | Changes |
|---|---|---|
| 1.1 | April 2026 | Added position qualifier rules for left/right pairs |
| 1.0 | March 2026 | Initial release |
```

Dates use `Month YYYY` granularity.

### 3.3 Type 2 — Implementation Guides (`guides/`)

Technical reconstruction documents for custom integrations and configurations. Written so
the author — or someone reading along in an HA community forum — could fully understand the
design and recreate it, without needing raw YAML pasted in.

**Structure:**

1. **Title and "Last updated" line** — `*Last updated: Month YYYY*` directly under the
   title. A bare month and year — no parenthetical describing what changed (§5).
2. **Overview** — one paragraph: what the integration does and how it works at a high level
3. **Architecture** — a text-based diagram of the component chain, followed by a brief
   explanation of key design decisions
4. **Prerequisites** — bulleted list of required hardware, software, and existing setup
5. **Numbered Steps** — one step per major phase of the implementation, in order
6. **Scale Conversions or Formula Reference** (if applicable) — table documenting non-obvious
   math or lookup values
7. **Security Summary** (if applicable) — table summarizing all security controls applied
8. **Related HA Config** (if applicable) — table of every HA-resident artifact the guide
   creates: friendly name, entity_id, type
9. **Related Files** (if applicable) — table of every on-disk file created or modified: repo
   path, deployed location, purpose. Omit if the guide creates no on-disk files.
10. **Related Documents** (if applicable) — other repo docs this guide depends on or
    coordinates with
11. **Troubleshooting** (if applicable) — advanced, non-obvious issues only; assume basic
    troubleshooting (restart, reload, check logs, verify entity exists) is already done

**Referencing HA-resident artifacts:** use the *Friendly Name (`entity_id`)* format
throughout. HA is authoritative for automation and script YAML — do not reproduce it in
guides; reference by entity ID and let the reader retrieve it via MCP or the `ha/` mirror.
**`configuration.yaml` entries are the exception:** they live outside HA storage and are not
retrievable via MCP, so include them in full in the relevant guide.

**No changelog table.** A guide describes a build at a point in time. Git history captures
what changed and when; the `Last updated` line tells the reader how stale the document might
be. Update the date when the build itself changes — not for typo fixes.

### 3.4 Scripts (`scripts/`)

Files that don't fit the standards/guides model but belong in version control: shell scripts
called by HA's `shell_command` integration, complex Jinja templates referenced by multiple
automations, packages YAML not managed via the UI.

No prescribed structure — they are what they are. The conventions that apply:

- **Filename matches purpose:** `scripts/litra_dispatch.sh`, not `scripts/script1.sh`
- **Header comment explains intent:** what it does, what calls it, any prerequisites
- **Security-relevant scripts cross-reference their guide:** a comment near the top points
  to the guide documenting the security model

---

## 4. Writing Conventions (all types)

### 4.1 Style

- Technical and direct — no conversational filler
- Present tense for descriptions, imperative for instructions
- Include relevant caveats and gotchas inline where they apply — subject to §7 (link to
  `LESSONS.md`, don't retell it)

### 4.2 Coordinated change callouts (Guides)

When a value, entity ID, or configuration depends on or coordinates with something
configured elsewhere — another integration's baseline, a value shared across automations, an
entity controlled by more than one system — add a blockquote immediately adjacent to that
value:

> **Coordinated change:** `<what the dependency is>`. If `<upstream thing>` changes, update
> `<this value/section>` to match.

### 4.3 Code blocks (all types)

- Every command the user must run goes in a `bash` code block
- Every configuration snippet goes in a `yaml` code block with correct indentation
- Comment lines whose purpose is not self-evident
- Do not truncate code — include complete, copy-pasteable blocks

### 4.4 Placeholders (Guides)

Replace environment-specific values with clearly marked placeholders. No real IP addresses,
usernames, API keys, or device serial numbers.

| Value type | Placeholder format |
|---|---|
| IP addresses | `<mac-mini-ip>`, `<ha-ip>`, etc. |
| macOS username | `<your_username>` |
| SSH public key | `AAAA...your-key...` |

**Exception:** entity IDs inside HA YAML (automations, scripts, shell commands, template
definitions) retain their actual values — generic placeholders would make the code
non-functional. Reference Standards rarely need placeholders; they describe rules, not
environments.

### 4.5 Formatting (all types)

- Tables for reference data (commands, files, security controls, scale conversions)
- `---` horizontal rules between major sections
- `>` blockquotes for important notes or caveats within a section
- Avoid bold mid-paragraph — use it only for UI navigation paths (e.g. **Settings →
  Devices & Services**)
- Architecture diagrams use plain ASCII/Unicode box-drawing characters; no embedded images

### 4.6 Security documentation (Guides)

Any guide for an integration involving network access, credentials, or elevated permissions
must include a Security Summary covering: authentication mechanism; access restrictions
applied; least-privilege controls (sudo scope, SSH key restrictions); worst-case impact if
credentials were compromised.

---

## 5. Current State Only — No Build History

**A guide documents what exists now and how to rebuild it.** It is not a changelog, a
post-mortem, or a record of the path taken. Git history is the record of the path; the
`Last updated` line is the staleness signal. Nothing in a guide should require the reader to
care what a previous version did.

### 5.1 What never belongs in a guide

| Category | Example of what to cut |
|---|---|
| Prior attempts and reverts | "`3s` was tried first and intermittently regressed, so it was reverted to `2s`" |
| "An earlier version / draft…" | "An earlier design left the bar steadily lit; after living with the night-only blip for a few days, resting-dark was preferred" |
| Old-apartment / pre-move comparisons | "The pre-move design cleared status on a bare door edge; four days of live history here showed two problems with that" |
| Dated incident narratives | "On 2026-08-27 this cut a daytime vacuum run short — 26 minutes into the job" |
| Re-narration of a `LESSONS.md` entry | A paragraph re-explaining why a commanded dock cancels a Roborock job, when `LESSONS.md` already has it |
| Rejected-alternative essays | "Why four copies, not a blueprint"; "Why two fixed zones instead of one adaptive schedule" |
| Changelog text in the date line | `*Last updated: September 2026 (Immediate Departure override added)*` |
| Duplicated facts | The blip hue/hold table restated in Design Decisions, Steps, Scale Reference, and Replicating |

### 5.2 What to keep

The current value, the current design, the steps to rebuild it, and — bounded by §6 and
§8 — the reason each non-obvious choice is what it is.

### 5.3 Forward-looking content is allowed

A "Not built — deferred" or "Future improvements" section is scope, not history — keep it.
A `> **Deprecated <Month YYYY>.**` marker on a section that is genuinely superseded is
allowed as a short pointer, but the deprecated *content* itself comes out (git history holds
it); don't carry a 200-line appendix of a replaced design.

---

## 6. Rationale vs. History

Rationale earns its place in a guide; history does not. The test: **does the sentence help
someone rebuilding from scratch make the right choice, or does it only describe a choice
already made and undone?**

| Keep — the constraint | Cut — the history of finding it |
|---|---|
| "Cluster 8 emits no Move/Step at `Instant`, so a non-`Instant` value is required." | "`3s` regressed intermittently and was reverted; `500ms`–`1s` ramp too fast to land a level." |
| "The blip lives in a per-room script because the automation is `mode: queued` and an inline `delay` would stall tap handling." | "This is the same failure that made the earlier bare-`state` + 1 s delay version stick on one colour." |
| "Retrieval clears on sustained occupancy (`for: 15s`), not a bare door edge — casual opens run 3–24 s and the door is often left open for hours." | "The pre-move design cleared on a bare edge. Four days of live history in this house show two problems with that…" |

**Worked example.** Before:

> Dimming Speed (Simulated): `2s`. Cluster 8 only emits Move/Step while non-`Instant`. `2s`
> is the value in use on both rooms; `3s` regressed intermittently and `500ms`–`1s` ramp too
> fast to land a level. An earlier version used a bare `state` trigger plus a 1 s delay;
> under `mode: queued` those delayed runs piled up…

After:

> Dimming Speed (Simulated): `2s`. Cluster 8 emits no Move/Step at `Instant`, so a
> non-`Instant` value is required. (`LESSONS.md` — other values tested and rejected.)

When the rejected values genuinely matter to a future rebuilder ("don't bother trying `3s`"),
that belongs in `LESSONS.md` as a dead-end entry, and the guide links to it — see §7.

---

## 7. Single-Owner Rule

Every fact has exactly one section that owns it. Every other mention cross-references that
section rather than restating the fact. When the owned fact changes, there is one place to
edit.

| Fact type | Canonical owner |
|---|---|
| A current parameter value | the Step where it is set (usually a table) |
| Scale, threshold, band-edge, or lookup data | the Scale / Formula Reference section |
| An integration quirk, dead end, or "we already tried X" | a `LESSONS.md` entry — the guide links to it |
| Live automation / script YAML | the `ha/` mirror — never reproduced in the guide |
| A value shared with another system | one guide owns it; the other adds a Coordinated-change callout pointing there |

A guide's Design Decisions section explains *why* the design is shaped as it is. It does not
re-list the values from the Steps, and it does not re-derive a `LESSONS.md` entry. If a
design decision's full reasoning runs long, the reasoning is a `LESSONS.md` entry and the
decision bullet is two sentences plus a link.

---

## 8. Length Discipline

- **Design Decisions entries: 2–4 sentences each.** If an entry needs more, the surplus is a
  `LESSONS.md` entry and the guide links to it.
- **Overview: one paragraph.** It says what the thing does and how it works at a high level —
  not how it came to be built that way.
- **Replicating / per-instance sections** reference the Steps for shared values ("every value
  in Steps 2–3 is identical across rooms; only the table below varies") rather than
  re-listing them.

---

## 9. Pre-Commit Checklist

Before committing a new or edited guide, run through this. Any hit is presumed a violation
until justified.

1. **Grep the diff** for: `earlier`, `originally`, `previously`, `was tried`, `used to`,
   `reverted`, `the old apartment`, `pre-move`, `initially`, `turned out`, `briefly`,
   `dropped once`, `for a few days`. Each hit is build history — cut it or move it to
   `LESSONS.md`.
2. **Dates in prose.** Grep for `20[0-9]{2}-[0-9]{2}-[0-9]{2}` and spelled-out dates. The
   only date in a guide is the `Last updated` line.
3. **Every dead end referenced is in `LESSONS.md`**, and the guide links to it rather than
   retelling it. No dangling "see `LESSONS.md`" pointing at content that was never added
   there.
4. **No fact appears in two sections.** Blip tables, parameter values, thresholds — one
   owner, everywhere else cites it.
5. **Every Design Decisions entry is ≤ 4 sentences.**
6. **The `Last updated` line is a bare `Month YYYY`** — no parenthetical.
7. **Cross-references still land.** A section this edit deleted is not linked from elsewhere
   in the repo.

---

## 10. Quick Reference

| Rule | Where |
|---|---|
| Current state only — no prior attempts, reverts, old-apartment comparisons | §5 |
| `Last updated: Month YYYY` — no parenthetical changelog | §3.3, §9.6 |
| Keep the constraint, cut the story of finding it | §6 |
| Dead ends → `LESSONS.md`; guide links, doesn't retell | §2, §7 |
| Every fact has one owning section | §7 |
| Design Decisions entries: 2–4 sentences | §8 |
| Deferred / future-work sections are fine (that's scope, not history) | §5.3 |
| Run the pre-commit checklist | §9 |
