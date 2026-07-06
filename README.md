# harness-kit

Shared, anti-drift manifest generator for **harness**-style plugin marketplaces
(Claude Code + Codex). Extracted from
[`smorin-harness`](https://github.com/smorin/smorin-harness) so the generator is
*depended on, never copied* — used across `smorin-harness`, `smorinlabs-harness`,
and `banksheets-harness`.

## What it does

Each plugin owns one `plugin.meta.toml`; each harness repo owns one `harness.toml`.
From these, `harness-kit gen` renders byte-stable, `_generated`-marked manifests:

- `.claude-plugin/marketplace.json` — repo-level, lists every plugin
- `plugins/<name>/.claude-plugin/plugin.json`
- `plugins/<name>/.codex-plugin/plugin.json`

`harness-kit gen --check` exits 1 if anything is stale, so manifests can't drift.

## Usage in a harness repo

```toml
# harness.toml  (repo root — the marketplace identity)
[marketplace]
name = "smorinlabs-harness"
description = "Public cross-platform (Claude Code + Codex) plugin marketplace for smorinlabs"
version = "0.1.0"

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
harness-kit gen           # write/update manifests
harness-kit gen --check   # CI: fail if stale
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
