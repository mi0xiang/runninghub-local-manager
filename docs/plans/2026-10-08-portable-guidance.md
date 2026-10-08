# Portable project guidance implementation plan

**Goal:** Publish reusable parent/child guidance without publishing machine configuration, business sources or production history.

**Architecture:** A small, closed bundle of generic Markdown guides is installed outside the manager repository. A private local context supplies the actual project role, manager location, source/product references and project-specific choices. Installation previews by default; updates compare recorded hashes and preserve customized files. No production adapter, queue, approval or cloud data is changed.

**Tech stack:** Python standard library, Markdown, Git index inspection, existing Windows offline CI.

The user requested planning and implementation in this session. Retain the existing task branch and complete the following work without adding a separate planning approval or mandatory skill chain.

1. Add `tests/test_project_guidance.py` and `tests/test_public_tree.py`. Verify failure before adding implementations. Cover different paths, fresh installation, preview/idempotence, customized rules and private context preservation, unsafe paths, staged private files and secret-like content.
2. Add `templates/project-guidance/`: parent entry, child entry, responsibilities, replication consultation, optional audio/visual checks, page boundaries and conditional H3 execution. Publish only generic examples; no copied local production documents. Add a private-context example and an installation/update guide.
3. Add `scripts/project_guidance.py`: explicit file list, no imports of manager runtime, no network, preview by default, guarded writes outside the code repository, hash-based update conflicts, private context and ignore rule creation.
4. Add `scripts/check_public_tree.py`: inspect staged bytes and file modes; flag excluded paths, binaries, common credential/resource patterns and personal paths without printing matched values. Document the limits of pattern checks; inspect the full release archive separately.
5. Reconcile `AGENTS.md`, `START_HERE.md`, `README.md`, `docs/publishing.md`, `docs/project-runner.md`, `docs/supervision-v02.md`, `CHANGELOG.md`, `.gitignore` and CI. Include templates in publication scope; explain same-account cross-computer coordination, local adaptation and manual merge of customized guidance.
6. Run focused tests, then the isolated complete offline suite and Python compilation. Verify every bundled Markdown link after installation, test two different project directories, inspect all staged bytes and a commit archive. Audit the existing local guide chain without copying business files into Git.
7. Update the existing pull request around the final scope, verify CI for its exact head, publish to main and confirm the remote commit. Keep local configuration, historical approvals and task data unchanged. Other machines pull code/templates, then adapt their own local context; no automatic data migration or services.

Verification commands (from the manager repository):

```powershell
python -m unittest discover -s tests -p 'test_project_guidance.py' -v
python -m unittest discover -s tests -p 'test_public_tree.py' -v
# Full suite uses RUNNINGHUB_CONFIG_FILE with an isolated temporary data root.
python -m unittest discover -s tests -v
python scripts/check_public_tree.py
git diff --cached --check
```
