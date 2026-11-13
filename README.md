# harness-kit

Shared, anti-drift manifest generator for **harness**-style plugin marketplaces
(Claude Code + Codex). Extracted from
[`smorin-skills`](https://github.com/smorin/smorin-skills) so the generator is
*depended on, never copied* — used across `smorin-skills`, `smorinlabs-skills`,
and `banksheets-harness`.

## What it does

Each plugin owns one `plugin.meta.toml`; each harness repo owns one `harness.toml`.
From these, `harness-kit gen` renders byte-stable manifests — the per-plugin ones carry a
`_generated` marker; the two `marketplace.json` files are regenerated wholesale:

- `.claude-plugin/marketplace.json` — repo-level Claude marketplace, lists every plugin (no marker)
- `.agents/plugins/marketplace.json` — repo-level Codex marketplace, lists every plugin
  except those with `codex = false` (no marker)
- `plugins/<name>/.claude-plugin/plugin.json` — `_generated`-marked
- `plugins/<name>/.codex-plugin/plugin.json` — `_generated`-marked; not generated (and
  pruned if present) for a `codex = false` plugin

The Codex marketplace makes a harness repo installable straight from GitHub:

```bash
codex plugin marketplace add <owner>/<repo>
codex plugin add <plugin>@<marketplace-name>
```

Each Codex entry uses `source = {source: "local", path: "./plugins/<name>"}`,
`policy = {installation: "AVAILABLE", authentication: "ON_INSTALL"}`, and the same
`category` as the plugin's `.codex-plugin/plugin.json` (default `"Developer Tools"`,
overridable with `[interface] category`). The schema follows
[OpenAI's marketplace metadata docs](https://developers.openai.com/plugins/build/plugins#marketplace-metadata).
Without this file, Codex falls back to reading `.claude-plugin/marketplace.json`, which
cannot express install policy or category.

`harness-kit gen --check` exits 1 if anything is stale — including orphaned vendored code — so
manifests can't drift.

## Usage in a harness repo

```toml
# harness.toml  (repo root — the marketplace identity)
[marketplace]
name = "smorinlabs-skills"
description = "Public cross-platform (Claude Code + Codex) plugin marketplace for smorinlabs"
version = "0.1.0"
# vendor_namespace = "smorinlabs_skills"  # only if a plugin declares [vendor]
# display_name = "smorinlabs skills"       # Codex marketplace title; default: title-cased name

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
# codex = false   # Claude-only: leave out of the Codex marketplace and skip .codex-plugin/
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
