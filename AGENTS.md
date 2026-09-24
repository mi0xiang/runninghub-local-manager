# RunningHub Local Manager · agent rules

Read START_HERE.md before acting. Code root is this file's directory; load `.local/config.json` to locate THIS machine's data root. Never infer a historical drive path. API keys come only from RUNNINGHUB_API_KEY; never print or serialize them.

## Local data boundary
Git contains program code, documentation and synthetic tests only. Projects, workflows, task IDs, approval records, logs, media and control tokens belong outside the repository. Do not copy data into examples/tests, commit `.local`, or force-add ignored files. Public releases must be built from an explicit code file list and inspected before upload. No telemetry, cloud data sync or public server deployment.

## API actions
New uploads/generation, revised versions and failed reruns require explicit user approval for exact assets/batches/parameters. Setup confirmation is not generation approval. Existing task IDs must be reconciled, never blindly submitted again. Unknown submission outcomes stop automatic generation. Maximum account concurrency3, global FIFO. Retain native approval hashes and original task records.

Use manage.py / scripts/hub.py as entry points; do not directly invoke legacy core module main functions. tick and UI resume/fetch can advance approved work and are not read-only. No paid/network tests in CI. Confirmation applies only to the current machine, code path and configuration.

## Workflows
Read docs/workflow-rules.md for workflow 2097955216049131522. Use actual reference counts and verified node mapping; inactive inputs receive no upload. Never invent switch fields. No changes to models, sampling, upscale or wiring beyond explicitly permitted reference switches without approval. The bundled helper configures audio/video only; images need separate verified preparation. Do not distribute workflow exports without redistribution permission.

## Maintenance
Test modifications in an isolated temporary data directory using RUNNINGHUB_CONFIG_FILE. Never point tests at real project data. Run `python -m unittest discover -s tests -v`, compile Python files, and inspect the public archive. Stop services before changing executable code. Record material changes in CHANGELOG. Existing machine data schema changes require backup and documented migration; updates must never reset records. Keep all service bindings loopback-only.
