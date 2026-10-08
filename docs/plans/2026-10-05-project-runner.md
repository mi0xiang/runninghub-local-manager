# Existing-task supervision and branch delivery implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let each video-owning conversation use persistent shared interfaces to receive existing tasks, finish its film, and verify registration, while a finite manually started worker supervises selected tasks without any generation permission.

**Architecture:** Existing batch task_state.json, archives, postproduction.json, delivery.json and presentation.json remain authoritative. A versioned execution-plan.json enumerates the whole film (including unapproved dependencies); finite receive-run checkpoints contain polling/error budgets, never another generation queue. All branches use the existing FIFO/three slots for generation and compare-before-write APIs for their own records.

**Tech Stack:** Python standard library, existing JSON store/Windows process locks, existing collector, ffmpeg and ffprobe, unittest fixtures.

## Task 1: Establish preservation boundary and baseline
- Read root/manager AGENTS and production/page rules; resolve this machine's data root.
- Record only selected owners/tasks. Back up exact current code and selected records; preserve dirty Git files.
- Stop the identified dashboard before executable changes. Run existing tests with RUNNINGHUB_CONFIG_FILE pointing to a temporary data root.
- No credentials, real paid fixture calls, automatic re-generation or unrelated page rendering.

## Task 2: Test durable plan, selected reception, recovery and ownership
Files: tests/test_project_runner.py, scripts/core/project_runner.py, scripts/core/durable_store.py.
- RED: absent runner API must fail a feature assertion.
- Fixtures verify full segment visibility, DAG cycles, <=15s, known-task identity, unchanged unrelated states, idempotent plan registration, expected revision rejection, restart/backoff/error budget, OS lock competition, cancelled/failed no revival and no submit calls.
- Implement register_plan(root, project_id, record, expected_revision), selection validation, step/run and read-only project_status.
- Run: python -m unittest discover -s tests -p test_project_runner.py -v.

## Task 3: Test output collection and deterministic assembly
Files: tests/test_project_runner.py, tests/test_postproduction_executor.py, scripts/core/collector.py, scripts/core/postproduction_executor.py.
- RED fixtures cover multiple video/audio nodes, preserved node identity, actual durations and stale-success URL refresh without create.
- Assembly reads only a frozen READY postproduction.json; validates ordered task inputs and trim bounds; preserves raw files.
- Real tiny color fixtures verify order, total duration, audio mode, full decode and repeated execution idempotency.
- Never infer content acceptance from container checks; absent content/final review remains a branch/user todo.

## Task 4: Integrate CLI, supervision and project registration
Files: manage.py, scripts/core/supervision.py, scripts/core/responsibility.py, scripts/core/postproduction_records.py.
- Expose execution-plan, watch-results, project-status, assemble-project and delivery-register.
- Branch ownership is preserved; shared writer API accepts own project registration, while locks serialize actual writes.
- Supervision reads execution-plan segment union and original task records; label approval/dependency/content-review waits honestly.
- Delivery registration requires exact file/hash/version, technical and content evidence, presentation/page binding and snapshot readback. Human confirmation is separate.
- Run targeted tests, then full unittest suite and Python compile checks.

## Task 5: Document and reconcile the selected original tasks
Files: root AGENTS.md, manager AGENTS.md, docs/project-runner.md, CHANGELOG.md.
- Document submission is not completion, branch end-to-end owner, explicit dependencies and finite manual execution. No automatic agent wake-up claim.
- Production migration lives in a data-root repair report, not hard-coded source or long-term rules.
- Back up selected project records and use revisions/locks to receive only original task IDs. Record platform failures; don't submit blocked future segments.
- Restore the same read-only dashboard manually; verify GET, supervision readback and media Range.
- Report changed files, test counts, before/after task differences and remaining branch content review/approval work.
