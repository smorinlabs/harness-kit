# harness-kit

Shared, anti-drift manifest generator for **harness**-style plugin marketplaces
(Claude Code + Codex). Extracted from
[`smorin-harness`](https://github.com/smorin/smorin-harness) so the generator is
*depended on, never copied* — used across `smorin-harness`, `smorinlabs-harness`,
and `banksheets-harness`.

## What it does

Each plugin owns one `plugin.meta.toml`; each harness repo owns one `harness.toml`.
From these, `harness-kit gen` renders byte-stable manifests — the per-plugin ones carry a
`_generated` marker; `marketplace.json` is regenerated wholesale:

- `.claude-plugin/marketplace.json` — repo-level, lists every plugin (no marker)
- `plugins/<name>/.claude-plugin/plugin.json` — `_generated`-marked
- `plugins/<name>/.codex-plugin/plugin.json` — `_generated`-marked

`harness-kit gen --check` exits 1 if anything is stale — including orphaned vendored code — so
manifests can't drift.

## Usage in a harness repo

```toml
# harness.toml  (repo root — the marketplace identity)
[marketplace]
name = "smorinlabs-harness"
description = "Public cross-platform (Claude Code + Codex) plugin marketplace for smorinlabs"
version = "0.1.0"
# vendor_namespace = "smorinlabs_harness"  # only if a plugin declares [vendor]

[marketplace.owner]
name = "Steve Morin"
email = "steve.morin@gmail.com"
```

```toml
# plugins/<name>/plugin.meta.toml  (one per plugin)
name = "repo-hygiene"
version = "0.1.0"
description = "…"
author = "Steve Morin"
keywords = ["…"]
```

```bash
harness-kit gen              # write/update manifests
harness-kit gen --check      # CI: fail if stale
harness-kit gen --root PATH  # target a repo root (default: cwd)
```

Plugins are markdown-only by default (any number of skills under `skills/`). A plugin
that declares a `[vendor]` table also gets its Python runtime vendored into the skill's
`scripts/_vendor/` — that path requires `vendor_namespace` in `harness.toml`.

## Develop

```bash
just all   # fmt, lint, typecheck, test
```

Tooling: `uv` (deps/build), `ruff` (format+lint), `ty` (typecheck), `pytest`. Zero
runtime dependencies (stdlib `tomllib` + `json`).

## License

MIT — © 2026 Steve Morin.
