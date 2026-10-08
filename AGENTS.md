# RunningHub Local Manager · agent rules

Updated 2026-10-08: responsibility and entry-point documentation cleanup. This file governs the shared technical manager. The parent project's rules govern shared boundaries and project tracking; creative plans and skill selection belong to the owning production child and the user; the manager directory is not a film-production child project.

## Start and locate data

Read [START_HERE.md](START_HERE.md) before acting. This directory is the code root; load `.local/config.json` to locate this machine's data root. Use actual project identity and configuration rather than historical drive paths. API keys come only from RUNNINGHUB_API_KEY; never print or serialize them.

For H3 submission or resumption, read [docs/project-runner.md](docs/project-runner.md) and the applicable parent/child production rules. Retain current local changes when maintaining this repository.

For missing parent/child guidance or cross-machine adaptation, use [the public guidance kit](templates/project-guidance/README.md). Keep real project sources and machine bindings in its private local context. When changing rules, follow the template's downstream documents and existing project-specific references together; do not export local AGENTS or business guides wholesale. Same-account computers need one dispatcher or a verified shared coordinator; local file locks do not coordinate independent machines.

## Responsibilities and completion

The owning child conversation is responsible for its whole film: plan and dependencies, approved execution, original-task receipt, segment/content review, actual-frame continuation, frozen postproduction, full-film review, delivery registration and tracking readback. The supervisor maintains basic rules and tracks cross-project identity, queue/concurrency, omissions, timeouts, blockers and delivery; scripts execute mechanical work and preserve evidence. Creative decisions and content review belong to the owning child.

Use exact project/version/ownerThreadId. All planned segments can be recorded without approving, enqueuing or submitting unapproved work. Only an accepted complete film registered to the child page/presentation and verified through readback may become review-pending; confirmed requires explicit user acceptance of the exact version/hash. Task IDs, URLs, archived segments and technical checks alone are not whole-film completion.

## Approved execution and shared state

New uploads/generation, revised inputs/batches and failed reruns require explicit approval for the exact assets, parameters and counts. Existing approval remains valid within its original scope; setup confirmation is not generation approval. Reconcile existing task IDs and unknown submission outcomes before further generation. Preserve original approvals, hashes, failed/cancelled jobs and task records.

The current account concurrency limit is 3 through the same global FIFO; a later rule change must also reconcile executor configuration and actual account capacity. An owning child with exact batch approval may register and dispatch its project through the established scoped interface. Shared writes use the same process lock and revision/digest checks; preserve other projects, ordering, approval fingerprints and submission counts. Local cross-project assignment records remain on the single coordinator path. Lark business integration is still being defined incrementally by the user: start from the specified video and Lark cell, and do not impose existing adapter fields or writeback as a prerequisite for local production/delivery. Do not create a separate queue or directly overwrite another active child's media, page or approval.

Use manage.py / scripts/hub.py through the verified local entry points, including the scoped adapter when required by the parent project. Do not directly invoke legacy core module main functions. tick and UI resume can submit approved work; fetch-results/collect-results receive existing task IDs only. Check both task scope and page-render side effects before using an entry point. Do not add a billing preflight to approved submission; occupancy reads for concurrency are queue checks.

## Manual finite reception

watch-results is a manually started, finite, foreground, receive-only runner. Closing stops it; restarting resumes durable checkpoints for the same original tasks. It does not upload, create, retry paid generation, wake chats or install services/tasks. The parent project's webpage is manually launched and its supervision dashboard is read-only. Do not infer active services or scheduling authorization from old documentation.

Bind accepted actual frames and evidence before executing segments that depend on prior results. Record missing segments, failures, pending review/approval, owner and next action as durable checkpoints.

## Workflow preparation

New H3 requests must not exceed 15 seconds. The owning child's measured shot/voice plan determines segment boundaries and durations; split at complete phrases and appropriate action states. Record global/segment time and start/end states. Older 10-second defaults and frozen tasks remain historical, not a new-plan requirement; respect a shorter verified workflow limit where applicable.

For workflow 2097955216049131522, read [docs/workflow-rules.md](docs/workflow-rules.md) and verify the actual export/hash. Node 265 controls real reference inputs: bind requested assets and remove unused slots/loader branches. Nodes 307/308/309 are UI group toggles, not API booleans in the verified export. Use actual counts and verified mappings; inactive inputs receive no upload. The bundled helper configures audio/video only; images require separately verified preparation. Check the actual node 265 connections and per-type counts, hashes, order and uploaded file bindings; inspect shared consumers before removing a loader. Save reference changes before approval and preserve internal audio VAE/decoders. Changes to models, sampling, upscale or unrelated wiring require their own approval. Third-party exports need redistribution permission.

## Data and maintenance

Git contains general program code, documentation and synthetic tests only. Machine projects, workflow exports, task IDs, approvals, logs, media, control tokens and real Lark resource identities stay in the configured data root outside this code repository. For optional Lark binding or upgrades, read [docs/supervision-v02.md](docs/supervision-v02.md). Never commit `.local` or force-add ignored business data. No telemetry, cloud data sync or public server deployment; service bindings remain loopback-only.

For executable code changes, stop affected services, test with an isolated temporary data directory via RUNNINGHUB_CONFIG_FILE, run `python -m unittest discover -s tests -v` and compile changed Python files. Never use real project data for tests; no paid/network CI tests. Documentation-only edits require reference/consistency review without production commands. Record material changes in CHANGELOG. Machine data schema changes require backup and documented migration and must not reset records. Public releases use an explicit code file list and inspected archive, following [docs/publishing.md](docs/publishing.md). Machine confirmation applies only to the current code path and configuration.
