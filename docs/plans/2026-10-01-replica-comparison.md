# Replica comparison presentation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Put the local source and assembled recreation side by side as the first content of recreation project pages, with production information collapsed by default.

**Architecture:** Extend the optional source-reference renderer and reuse the existing tracker inside a closed production-details section. A new optional project-local presentation.json points to an existing assembled video and Chinese voiceover text; it never changes approvals, queue state, generation inputs or cloud tasks. Existing projects without source metadata keep the legacy page.

**Tech Stack:** Python stdlib HTML rendering, existing vanilla browser controls, isolated unittest fixtures.

---

### Task 1: Lock presentation and safety behavior with tests

**Files:** Modify tests/test_source_reference.py.

1. Add synthetic assembled video and presentation metadata fixtures. Assert both players, equal-column class, comparison preceding closed production details, escaped voiceover and preserved technical history.
2. Test absent result, missing result, path traversal, malformed presentation and legacy projects.
3. Run `python -m unittest discover -s tests -p test_source_reference.py -v`; observe new assertions fail before implementation.

### Task 2: Render the comparison-first page

**Files:** Modify scripts/core/project_reference.py, scripts/hub.py, web/ui_controls.js.

1. Stop the verified local control service before executable changes; preserve the existing dirty checkout rather than create a clean worktree that loses the in-progress source-player feature.
2. Validate local media paths; show original and assembled result or an honest empty state. Move source IDs, hashes, ranges and notes into closed source details. Add compact optional Chinese voiceover.
3. Wrap existing tracker content in closed production details for source-reference projects; put injected local controls/queue inside that section, preserving their behavior. User refined scope: native independent playback only, no sync toolbar, no forced muting, no autoplay.
4. Run targeted tests, then all `python -m unittest discover -s tests -v` and compile modified Python. No network/paid tests; all fixtures use RUNNINGHUB_CONFIG_FILE and temporary data roots.

### Task 3: Apply and verify locally

**Files:** Document presentation.json in docs/project-format.md; update CHANGELOG.md. Save current project's presentation metadata outside the repository and update the local production guide.

1. Back up any existing presentation metadata and preview page before edits. Keep all media and approval/task records unchanged. Make the earlier preview URL lead to the main comparison page.
2. Render with scripts/hub.py render only (not tick/fetch/resume). Restart the existing loopback web service hidden.
3. Verify HTTP pages and both media/range routes; inspect desktop and narrow layouts in the browser and exercise only playback/detail controls.
4. Record the reusable comparison-first rule in the local production guide and handoff. Report the result, tests and any limits; no Git commit/push or new task submission.
