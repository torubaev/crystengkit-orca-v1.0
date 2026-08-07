# Repository working rules

- Treat all pre-existing files and directories under `tmp/` as user-owned.
- Put Codex-generated disposable probes, test outputs, and build artifacts only
  under `tmp/codex_work/`.
- Never clean or remove content outside `tmp/codex_work/` unless the user
  explicitly identifies the exact target.
