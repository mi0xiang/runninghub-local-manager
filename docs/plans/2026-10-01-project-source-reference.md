# Project source reference Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show an optional local source-video player and source/segment metadata on the persistent project tracking page.

**Architecture:** A small renderer reads project-owned `source_reference.json`, validates a project-relative video path, and returns escaped HTML. `scripts/hub.py` injects it after the project heading on each render; no generation, network query, or API permissions change. No source metadata means no change to existing projects.

**Tech Stack:** Python standard library, unittest, existing loopback HTTP server and HTML5 video.

---

### Task 1: Isolated render regression tests

**Files:** Create `tests/test_source_reference.py`.

1. Use a TemporaryDirectory and RUNNINGHUB_CONFIG_FILE with synthetic project metadata and a synthetic local MP4 placeholder. Run the real hub render entry in a subprocess with network access denied.
2. Assert a local source player, escaped title, source links, and A01/A02/A03 source ranges appear. Assert rendering again retains the module.
3. Assert absent metadata leaves old projects unchanged, path traversal cannot expose outside media, and non-HTTP links cannot inject script.
4. Run `python -m unittest discover -s tests -p test_source_reference.py -v`. Observe a failed assertion for the missing source module before implementation.

### Task 2: Minimal read-only renderer

**Files:** Create `scripts/core/project_reference.py`; modify `scripts/hub.py`.

1. Stop the known local web service before editing executable code; do not cancel remote tasks or kill unrelated Python processes.
2. Implement `render(folder)`: absent metadata returns empty string; require existing MP4/WebM inside the project; escape strings and URL-encode the local media path; include only http/https external links. Invalid metadata returns a small unavailable notice.
3. Insert this returned section once after the project heading. The block uses `video controls preload="metadata"`, has no autoplay or submit action, and has separate record/source ranges.
4. Run the new regression suite, then all existing tests; compile all Python files and run git diff --check.

### Task 3: Document and install project data

**Files:** Update `docs/project-format.md` and CHANGELOG.md. Runtime source metadata and media stay in the configured data root, never in Git.

1. Document optional source_reference.json fields: title, video, origin_url, lark_url, record_id, analysis_version, duration_seconds, sha256, note, segments(name/start/end).
2. Attach the actual project-owned source and metadata; verify its SHA256 matches the source archive.
3. Render through the normal hub entry and restart loopback service with a hidden window.
4. Verify HTTP 200 for project page and HTTP range 206 for the source MP4. Inspect resulting rendered page/player. Record the operation in the local project handoff.

No commit is needed for this local change request; preserve pre-existing worktree edits. This turn directly implements the requested feature rather than dispatching another task.
