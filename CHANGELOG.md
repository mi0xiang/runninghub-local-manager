# Changelog

## Unreleased · 2026-09-28
- Clarified workflow 2097955216049131522: node265 input connections, UI-only toggles307/308/309, per-type reference selection, disabling and uploaded file binding. Documentation only; no runtime or workflow changes.

## 0.1.0
- Extracted local project dashboard, FIFO queue, result collector and version controls.
- Separated repository code from machine-local data; blank installation has no projects.
- Added setup, offline environment report and machine/configuration confirmation.
- Documented native reference mapping and explicit generation approval requirements.
- Removed project-specific assets, workflow exports, task history and fixed interpreter paths.
- Local tests do not submit paid requests. Cloud end-to-end validation remains operator-specific.
