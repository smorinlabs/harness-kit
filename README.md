# harness-kit

Shared, anti-drift manifest generator for **harness**-style plugin marketplaces
(Claude Code + Codex + Antigravity). Extracted from
[`smorin-skills`](https://github.com/smorin/smorin-skills) so the generator is
*depended on, never copied* — used across `smorin-skills`, `smorinlabs-skills`,
and `banksheets-harness`.

## What it does

Each plugin owns one `plugin.meta.toml`; each harness repo owns one `harness.toml`.
From these, `harness-kit gen` renders byte-stable manifests — the Claude and Codex
per-plugin manifests carry a `_generated` marker, the Antigravity per-plugin manifest
carries `extensions["harness-kit"]["generated"]` (because Antigravity's schema sets
`additionalProperties: false`), and the repo-level discovery/marketplace files are
regenerated wholesale:

- `.claude-plugin/marketplace.json` — repo-level Claude marketplace, lists every plugin (no marker)
- `.agents/plugins/marketplace.json` — repo-level Codex marketplace, lists every plugin
  except those with `codex = false` (no marker)
- `.agents/plugins.json` — repo-level Antigravity plugin discovery config pointing at
  `plugins` (with `exclude` for any plugin setting `antigravity = false`; omitted and
  pruned when all plugins opt out). Coexists cleanly with Codex's
  `.agents/plugins/marketplace.json`
- `plugins/<name>/.claude-plugin/plugin.json` — `_generated`-marked
- `plugins/<name>/.codex-plugin/plugin.json` — `_generated`-marked; not generated (and
  pruned if present) for a `codex = false` plugin. With `codex_hooks` set, it carries a
  `hooks` entry, so Codex loads those files instead of the default `hooks/hooks.json`
  (which Claude Code also loads)
- `plugins/<name>/.antigravity-plugin/plugin.json` — conforms to
  `https://antigravity.google/schemas/v1/plugin.json`; not generated (and pruned if
  present) for an `antigravity = false` (or `[antigravity] enabled = false`) plugin
- `plugins/<name>/hooks.json` — generated only when `antigravity_hooks` is set, by
  validating and rendering that source JSON file into `<plugin-root>/hooks.json`
  (Antigravity's runtime hook location). Ownership is recorded in
  `extensions["harness-kit"]["hooksSource"]` so removing `antigravity_hooks` or opting
  out prunes generated `hooks.json` files cleanly without ever touching hand-written ones

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

For Antigravity, `.agents/plugins.json` enables automatic workspace discovery for every
Antigravity-enabled plugin under `plugins/`, and each plugin can be validated directly with:

```bash
agy plugin validate --strict ./plugins/<name>
```

(In multi-tool plugins that also ship Claude's `hooks/hooks.json`, use `agy plugin validate`
without `--strict` or filter the expected `hooks/hooks.json` warning via `--json`.)

`harness-kit gen --check` exits 1 if anything is stale — including orphaned vendored code,
shared references, opted-out manifests, or managed hooks — so manifests can't drift.

## Usage in a harness repo

```toml
# harness.toml  (repo root — the marketplace identity)
[marketplace]
name = "smorinlabs-skills"
description = "Public cross-platform (Claude Code + Codex + Antigravity) plugin marketplace for smorinlabs"
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
# homepage = "https://example.com/docs"      # optional metadata (rendered in Antigravity manifest)
# repository = "https://github.com/org/repo"
# license = "MIT"
# codex = false   # leave out of the Codex marketplace and skip .codex-plugin/
# codex_hooks = "./hooks/codex-hooks.json"   # Codex-only hook file(s): a ./-prefixed path or a list
# antigravity = false   # exclude from .agents/plugins.json and skip .antigravity-plugin/
# antigravity_hooks = "./hooks/antigravity-hooks.json"   # rendered into <plugin-root>/hooks.json
#
# Optional Antigravity-specific manifest fields (cannot be combined with `antigravity = false`;
# set `enabled = false` inside the table to opt out while keeping config):
# [antigravity]
# displayName = "Repo Hygiene"  # avoid leading "Antigravity"/"Gemini"/"Claude"/"Cursor"
# logo = "assets/logo.svg"
# suggestedPrompts = ["Audit this repository for hygiene issues"]
# skills = ["./extra-skills"]
# disabled = false
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
