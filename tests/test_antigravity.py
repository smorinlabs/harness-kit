"""Antigravity plugin manifests, managed hooks, and ``.agents/plugins.json`` discovery.

Manifest schema: https://antigravity.google/schemas/v1/plugin.json
Workspace discovery config: ``.agents/plugins.json`` (coexists with Codex's
``.agents/plugins/marketplace.json``).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from harness_kit import cli, manifests

AGY_PLUGINS_CFG = Path(".agents") / "plugins.json"
CODEX_MKT = Path(".agents") / "plugins" / "marketplace.json"

SAMPLE_HOOKS = {
    "policy-guard": {
        "enabled": True,
        "PreToolUse": [
            {
                "matcher": "run_command",
                "hooks": [
                    {
                        "type": "command",
                        "command": "echo '{}'",
                        "timeout": 10,
                    }
                ],
            }
        ],
        "Stop": [
            {
                "type": "command",
                "command": "echo '{}'",
                "timeout": 15,
            }
        ],
    }
}


def _harness(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "harness.toml").write_text(
        "[marketplace]\n"
        'name = "demo-harness"\n'
        'description = "demo marketplace"\n'
        'version = "0.1.0"\n'
        "[marketplace.owner]\n"
        'name = "A"\n'
    )


def _plugin(
    root: Path,
    name: str,
    *,
    extra: str = "",
    author: str = "A",
    keywords: list[str] | None = None,
) -> Path:
    pdir = root / "plugins" / name
    (pdir / "skills" / name).mkdir(parents=True, exist_ok=True)
    (pdir / "skills" / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} skill\n---\n\nRun {name}.\n"
    )
    kw = json.dumps(keywords if keywords is not None else [])
    author_line = f'author = "{author}"\n' if author else ""
    (pdir / "plugin.meta.toml").write_text(
        f'name = "{name}"\nversion = "0.1.0"\ndescription = "Demo {name} plugin."\n'
        f"{author_line}keywords = {kw}\n{extra}"
    )
    return pdir


def _meta_with(tmp_path: Path, extra: str) -> Path:
    p = tmp_path / "plugin.meta.toml"
    p.write_text('name = "demo"\nversion = "0.1.0"\ndescription = "Demo plugin."\n' + extra)
    return p


# --- Per-plugin manifest rendering -------------------------------------------


def test_render_antigravity_plugin_defaults_and_schema():
    meta = manifests.PluginMeta(
        name="repo-hygiene",
        version="1.2.3",
        description="Keep repos clean.",
        author="Alice",
        keywords=["git", "hygiene"],
    )
    doc = manifests.render_antigravity_plugin(meta)
    assert doc["$schema"] == "https://antigravity.google/schemas/v1/plugin.json"
    assert doc["name"] == "repo-hygiene"
    assert doc["displayName"] == "Repo Hygiene"
    assert doc["version"] == "1.2.3"
    assert doc["description"] == "Keep repos clean."
    assert doc["author"] == {"name": "Alice"}
    assert doc["keywords"] == ["git", "hygiene"]
    assert "_generated" not in doc
    assert doc["extensions"] == {"harness-kit": {"generated": manifests._GEN_NOTE}}


def test_render_antigravity_plugin_omits_empty_author_and_keywords():
    meta = manifests.PluginMeta(name="demo", version="0.1.0", description="Demo.")
    doc = manifests.render_antigravity_plugin(meta)
    assert "author" not in doc  # empty author {} would trigger an agy validation warning
    assert "keywords" not in doc
    assert "homepage" not in doc
    assert "repository" not in doc
    assert "license" not in doc


def test_render_antigravity_plugin_display_name_precedence():
    from_interface = manifests.PluginMeta(
        name="demo-one",
        version="0.1.0",
        description="d",
        interface={"displayName": "From Interface"},
    )
    assert manifests.render_antigravity_plugin(from_interface)["displayName"] == "From Interface"

    from_agy = manifests.PluginMeta(
        name="demo-one",
        version="0.1.0",
        description="d",
        interface={"displayName": "From Interface"},
        antigravity_meta={"displayName": "From Antigravity"},
    )
    assert manifests.render_antigravity_plugin(from_agy)["displayName"] == "From Antigravity"


def test_render_antigravity_plugin_optional_metadata_and_table(tmp_path: Path):
    meta = manifests.load_meta(
        _meta_with(
            tmp_path,
            'author = "Alice"\n'
            'keywords = ["tools"]\n'
            'homepage = "https://example.com/docs"\n'
            'repository = "https://github.com/example/demo"\n'
            'license = "MIT"\n'
            'antigravity_hooks = "./hooks/agy.json"\n'
            "[antigravity]\n"
            'displayName = "Demo Tools"\n'
            'logo = "assets/logo.svg"\n'
            'suggestedPrompts = ["Check status", "Run audit"]\n'
            'skills = ["./extra-skills"]\n'
            "disabled = false\n",
        )
    )
    doc = manifests.render_antigravity_plugin(meta)
    assert doc["displayName"] == "Demo Tools"
    assert doc["logo"] == "assets/logo.svg"
    assert doc["suggestedPrompts"] == ["Check status", "Run audit"]
    assert doc["skills"] == ["./extra-skills"]
    assert doc["disabled"] is False
    assert doc["homepage"] == "https://example.com/docs"
    assert doc["repository"] == "https://github.com/example/demo"
    assert doc["license"] == "MIT"
    assert doc["extensions"]["harness-kit"]["hooksSource"] == "./hooks/agy.json"


# --- Schema / load_meta validation -------------------------------------------


@pytest.mark.parametrize(
    "extra, match",
    [
        ('antigravity = "no"\n', "boolean or table"),
        ("antigravity = 1\n", "boolean or table"),
        ("[antigravity]\nunknownKey = true\n", "unknown \\[antigravity\\] keys"),
        ('[antigravity]\nenabled = "yes"\n', "enabled must be a boolean"),
        ('[antigravity]\ndisplayName = "  "\n', "displayName"),
        ('[antigravity]\nlogo = "../escape.svg"\n', "stay inside"),
        ('[antigravity]\nlogo = "/abs/logo.svg"\n', "stay inside"),
        ('[antigravity]\nsuggestedPrompts = ["a", "b", "c", "d"]\n', "suggestedPrompts"),
        ('[antigravity]\nsuggestedPrompts = ["   "]\n', "suggestedPrompts"),
        ('[antigravity]\ndisabled = "no"\n', "disabled must be a boolean"),
        ("[antigravity]\nskills = []\n", "skills"),
        ('[antigravity]\nskills = ["../outside"]\n', "stay inside"),
        ("homepage = 123\n", "homepage must be a string"),
        ("repository = false\n", "repository must be a string"),
        ("license = []\n", "license must be a string"),
        ('antigravity_hooks = "hooks/agy.json"\n', "start with \\./"),
        ('antigravity_hooks = "./../escape.json"\n', "stay inside"),
        ('antigravity_hooks = "./hooks/../../escape.json"\n', "stay inside"),
        ('antigravity_hooks = "./hooks.json"\n', "cannot target hooks.json"),
        ('antigravity_hooks = "./"\n', "stay inside"),
        ('antigravity_hooks = ["./hooks/a.json"]\n', "antigravity_hooks must be"),
        ("antigravity_hooks = 42\n", "antigravity_hooks must be"),
    ],
)
def test_invalid_antigravity_meta_raises(tmp_path: Path, extra: str, match: str):
    with pytest.raises(ValueError, match=match):
        manifests.load_meta(_meta_with(tmp_path, extra))


def test_antigravity_invalid_type_cli_exits_1(tmp_path: Path):
    _harness(tmp_path)
    _plugin(tmp_path, "alpha", extra='antigravity = "no"\n')
    assert cli.main(["gen", "--root", str(tmp_path)]) == 1


# --- Opt-out & pruning -------------------------------------------------------


def test_antigravity_opt_out_omits_manifest_and_excludes_from_plugins_json(tmp_path: Path):
    _harness(tmp_path)
    _plugin(tmp_path, "alpha")
    _plugin(tmp_path, "beta", extra="[antigravity]\nenabled = false\n")
    _plugin(tmp_path, "claude-only", extra="antigravity = false\n")

    assert manifests.write_all(tmp_path)
    assert not manifests.write_all(tmp_path)  # idempotent

    assert (tmp_path / "plugins" / "alpha" / ".antigravity-plugin" / "plugin.json").exists()
    assert not (tmp_path / "plugins" / "beta" / ".antigravity-plugin" / "plugin.json").exists()
    assert not (
        tmp_path / "plugins" / "claude-only" / ".antigravity-plugin" / "plugin.json"
    ).exists()
    # Claude and Codex manifests are still generated unless codex = false.
    assert (tmp_path / "plugins" / "claude-only" / ".claude-plugin" / "plugin.json").exists()
    assert (tmp_path / "plugins" / "claude-only" / ".codex-plugin" / "plugin.json").exists()

    cfg = json.loads((tmp_path / AGY_PLUGINS_CFG).read_text())
    assert cfg == {"entries": [{"path": "plugins", "exclude": ["beta", "claude-only"]}]}
    # Coexists cleanly with Codex's .agents/plugins/marketplace.json.
    assert (tmp_path / CODEX_MKT).is_file()


def test_flipping_to_antigravity_false_prunes_manifest_and_empty_dir(tmp_path: Path):
    _harness(tmp_path)
    pdir = _plugin(tmp_path, "alpha")
    _plugin(tmp_path, "beta")
    manifests.write_all(tmp_path)
    agy = pdir / ".antigravity-plugin" / "plugin.json"
    assert agy.exists()

    (pdir / "plugin.meta.toml").write_text(
        'name = "alpha"\nversion = "0.1.0"\ndescription = "d"\nantigravity = false\n'
    )
    assert manifests.write_all(tmp_path, dry_run=True)  # --check sees stale files
    assert agy.exists()  # dry-run does not delete
    assert manifests.write_all(tmp_path)
    assert not agy.exists()
    assert not agy.parent.exists()  # empty .antigravity-plugin/ removed
    assert not manifests.write_all(tmp_path, dry_run=True)


# --- Repo-level .agents/plugins.json -----------------------------------------


def test_plugins_json_omits_exclude_when_all_enabled(tmp_path: Path):
    _harness(tmp_path)
    _plugin(tmp_path, "alpha")
    _plugin(tmp_path, "beta")
    manifests.write_all(tmp_path)

    raw = (tmp_path / AGY_PLUGINS_CFG).read_bytes()
    doc = json.loads(raw)
    assert doc == {"entries": [{"path": "plugins"}]}
    assert "_generated" not in doc
    assert raw.endswith(b"}\n")
    manifests.write_all(tmp_path)
    assert (tmp_path / AGY_PLUGINS_CFG).read_bytes() == raw  # byte-stable


def test_plugins_json_omitted_and_pruned_when_all_plugins_opt_out(tmp_path: Path):
    _harness(tmp_path)
    pdir = _plugin(tmp_path, "alpha", extra="antigravity = false\n")
    manifests.write_all(tmp_path)
    assert not (tmp_path / AGY_PLUGINS_CFG).exists()
    assert not manifests.write_all(tmp_path, dry_run=True)

    # Enable, generate, then disable again → .agents/plugins.json is pruned cleanly.
    (pdir / "plugin.meta.toml").write_text('name = "alpha"\nversion = "0.1.0"\ndescription = "d"\n')
    manifests.write_all(tmp_path)
    assert (tmp_path / AGY_PLUGINS_CFG).exists()

    (pdir / "plugin.meta.toml").write_text(
        'name = "alpha"\nversion = "0.1.0"\ndescription = "d"\nantigravity = false\n'
    )
    assert manifests.write_all(tmp_path, dry_run=True)
    assert (tmp_path / AGY_PLUGINS_CFG).exists()  # dry-run does not delete
    assert manifests.write_all(tmp_path)
    assert not (tmp_path / AGY_PLUGINS_CFG).exists()
    assert not manifests.write_all(tmp_path, dry_run=True)


def test_plugins_json_check_fails_when_missing_or_stale(tmp_path: Path):
    _harness(tmp_path)
    _plugin(tmp_path, "alpha")
    root = str(tmp_path)
    assert cli.main(["gen", "--root", root]) == 0
    assert cli.main(["gen", "--check", "--root", root]) == 0

    (tmp_path / AGY_PLUGINS_CFG).unlink()
    assert cli.main(["gen", "--check", "--root", root]) == 1
    assert cli.main(["gen", "--root", root]) == 0
    assert cli.main(["gen", "--check", "--root", root]) == 0

    (tmp_path / AGY_PLUGINS_CFG).write_text('{"entries": []}\n')
    assert cli.main(["gen", "--check", "--root", root]) == 1
    assert cli.main(["gen", "--root", root]) == 0
    assert cli.main(["gen", "--check", "--root", root]) == 0


# --- Antigravity hooks rendering, drift, pruning, and safety -----------------


def test_antigravity_hooks_rendered_and_drift_checked(tmp_path: Path, capsys):
    _harness(tmp_path)
    pdir = _plugin(
        tmp_path, "alpha", extra='antigravity_hooks = "./hooks/antigravity-hooks.json"\n'
    )
    (pdir / "hooks").mkdir()
    src = pdir / "hooks" / "antigravity-hooks.json"
    src.write_text(json.dumps(SAMPLE_HOOKS))  # compact input → canonical 2-space output

    assert manifests.write_all(tmp_path)
    dest = pdir / "hooks.json"
    assert dest.is_file()
    raw = dest.read_bytes()
    assert json.loads(raw) == SAMPLE_HOOKS
    assert raw.endswith(b"}\n")
    assert b"\n  " in raw  # canonical 2-space indent
    assert not manifests.write_all(tmp_path)  # idempotent
    assert not manifests.write_all(tmp_path, dry_run=True)

    # Missing destination detected by --check without writing.
    dest.unlink()
    assert manifests.write_all(tmp_path, dry_run=True)
    assert "missing generated hooks" in capsys.readouterr().err
    assert not dest.exists()
    manifests.write_all(tmp_path)
    assert dest.read_bytes() == raw

    # Hand-edited destination detected as stale and repaired.
    dest.write_text("{}\n")
    assert manifests.write_all(tmp_path, dry_run=True)
    assert "stale generated hooks" in capsys.readouterr().err
    manifests.write_all(tmp_path)
    assert dest.read_bytes() == raw

    # Source edit propagates.
    updated = {"policy-guard": {"enabled": False}}
    src.write_text(json.dumps(updated))
    assert manifests.write_all(tmp_path, dry_run=True)
    manifests.write_all(tmp_path)
    assert json.loads(dest.read_text()) == updated


def test_removing_antigravity_hooks_prunes_managed_hooks_json(tmp_path: Path, capsys):
    _harness(tmp_path)
    pdir = _plugin(
        tmp_path, "alpha", extra='antigravity_hooks = "./hooks/antigravity-hooks.json"\n'
    )
    (pdir / "hooks").mkdir()
    (pdir / "hooks" / "antigravity-hooks.json").write_text(json.dumps(SAMPLE_HOOKS))
    manifests.write_all(tmp_path)
    dest = pdir / "hooks.json"
    assert dest.exists()

    (pdir / "plugin.meta.toml").write_text('name = "alpha"\nversion = "0.1.0"\ndescription = "d"\n')
    assert manifests.write_all(tmp_path, dry_run=True)
    assert "orphaned generated hooks" in capsys.readouterr().err
    assert dest.exists()  # dry-run preserves it

    assert manifests.write_all(tmp_path)
    assert not dest.exists()
    agy = json.loads((pdir / ".antigravity-plugin" / "plugin.json").read_text())
    assert "hooksSource" not in agy["extensions"]["harness-kit"]
    assert not manifests.write_all(tmp_path, dry_run=True)


def test_opt_out_prunes_managed_hooks_json(tmp_path: Path):
    _harness(tmp_path)
    pdir = _plugin(
        tmp_path, "alpha", extra='antigravity_hooks = "./hooks/antigravity-hooks.json"\n'
    )
    (pdir / "hooks").mkdir()
    (pdir / "hooks" / "antigravity-hooks.json").write_text(json.dumps(SAMPLE_HOOKS))
    manifests.write_all(tmp_path)
    dest = pdir / "hooks.json"
    assert dest.exists()

    (pdir / "plugin.meta.toml").write_text(
        'name = "alpha"\nversion = "0.1.0"\ndescription = "d"\nantigravity = false\n'
    )
    assert manifests.write_all(tmp_path, dry_run=True)
    assert dest.exists()
    assert manifests.write_all(tmp_path)
    assert not dest.exists()
    assert not (pdir / ".antigravity-plugin" / "plugin.json").exists()
    assert not manifests.write_all(tmp_path, dry_run=True)


def test_hand_written_hooks_json_is_never_touched_or_pruned(tmp_path: Path):
    _harness(tmp_path)
    pdir = _plugin(tmp_path, "alpha")
    hand = pdir / "hooks.json"
    hand.write_text('{"custom": {"enabled": true}}\n')

    manifests.write_all(tmp_path)
    assert hand.read_text() == '{"custom": {"enabled": true}}\n'
    assert not manifests.write_all(tmp_path, dry_run=True)

    # Even opting out of Antigravity must NOT delete a hand-written hooks.json.
    (pdir / "plugin.meta.toml").write_text(
        'name = "alpha"\nversion = "0.1.0"\ndescription = "d"\nantigravity = false\n'
    )
    manifests.write_all(tmp_path)
    assert hand.read_text() == '{"custom": {"enabled": true}}\n'
    assert not manifests.write_all(tmp_path, dry_run=True)


def test_antigravity_hooks_source_validation_errors(tmp_path: Path):
    _harness(tmp_path)
    pdir = _plugin(tmp_path, "alpha", extra='antigravity_hooks = "./hooks/agy.json"\n')

    # Missing source file
    with pytest.raises(ValueError, match="does not exist"):
        manifests.write_all(tmp_path)

    # Invalid JSON
    (pdir / "hooks").mkdir()
    src = pdir / "hooks" / "agy.json"
    src.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        manifests.write_all(tmp_path)

    # Non-object top-level JSON
    src.write_text("[]")
    with pytest.raises(ValueError, match="mapping hook group names"):
        manifests.write_all(tmp_path)

    # Non-object top-level value (e.g. accidental _generated string)
    src.write_text('{"_generated": "nope"}')
    with pytest.raises(ValueError, match="mapping hook group names"):
        manifests.write_all(tmp_path)

    # Non-boolean enabled field
    src.write_text('{"guard": {"enabled": "yes"}}')
    with pytest.raises(ValueError, match="enabled"):
        manifests.write_all(tmp_path)


def test_antigravity_hooks_symlink_containment(tmp_path: Path, capsys):
    _harness(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(SAMPLE_HOOKS))
    pdir = _plugin(tmp_path, "alpha", extra='antigravity_hooks = "./hooks/agy.json"\n')
    (pdir / "hooks").mkdir()

    # Symlinked source file rejected
    (pdir / "hooks" / "agy.json").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        manifests.write_all(tmp_path)

    # Symlinked parent directory rejected
    (pdir / "hooks" / "agy.json").unlink()
    (pdir / "hooks").rmdir()
    outside_dir = tmp_path / "outside-hooks"
    outside_dir.mkdir()
    (outside_dir / "agy.json").write_text(json.dumps(SAMPLE_HOOKS))
    (pdir / "hooks").symlink_to(outside_dir)
    with pytest.raises(ValueError, match="symlink"):
        manifests.write_all(tmp_path)

    # Replace with real source, generate, then test symlinked destination
    (pdir / "hooks").unlink()
    (pdir / "hooks").mkdir()
    (pdir / "hooks" / "agy.json").write_text(json.dumps(SAMPLE_HOOKS))
    manifests.write_all(tmp_path)
    dest = pdir / "hooks.json"
    rendered = dest.read_bytes()

    victim = tmp_path / "victim.json"
    victim.write_bytes(rendered)  # even byte-identical target must be flagged
    dest.unlink()
    dest.symlink_to(victim)
    assert manifests.write_all(tmp_path, dry_run=True)
    assert "symlinked generated hooks" in capsys.readouterr().err

    victim.write_text("precious external file\n")
    manifests.write_all(tmp_path)
    assert victim.read_text() == "precious external file\n"  # never written through
    assert not dest.is_symlink()
    assert dest.read_bytes() == rendered


# --- Empirical integration test with real `agy plugin validate` --------------


@pytest.mark.skipif(shutil.which("agy") is None, reason="agy CLI not installed")
def test_generated_plugins_pass_agy_plugin_validate(tmp_path: Path):
    _harness(tmp_path)

    # 1. Multi-tool plugin without hooks (with optional metadata + logo)
    p_plain = _plugin(
        tmp_path,
        "plain-tools",
        author="Alice",
        keywords=["tools", "demo"],
        extra=(
            'homepage = "https://example.com/plain"\n'
            'repository = "https://github.com/example/plain"\n'
            'license = "MIT"\n'
            "[antigravity]\n"
            'logo = "assets/logo.svg"\n'
            'suggestedPrompts = ["Run plain check"]\n'
        ),
    )
    (p_plain / "assets").mkdir()
    (p_plain / "assets" / "logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>\n")

    # 2. Multi-tool plugin with managed Antigravity hooks (no Claude hooks/hooks.json)
    p_hooks = _plugin(
        tmp_path,
        "hooked-tools",
        author="Alice",
        extra='antigravity_hooks = "./hooks/antigravity-hooks.json"\n',
    )
    (p_hooks / "hooks").mkdir()
    (p_hooks / "hooks" / "antigravity-hooks.json").write_text(json.dumps(SAMPLE_HOOKS))

    # 3. Multi-tool plugin with BOTH Claude hooks/hooks.json AND managed Antigravity hooks.json
    p_multi = _plugin(
        tmp_path,
        "multi-hooks",
        author="",  # also exercises omitted author
        extra=(
            'codex_hooks = "./hooks/codex-hooks.json"\n'
            'antigravity_hooks = "./hooks/antigravity-hooks.json"\n'
        ),
    )
    (p_multi / "hooks").mkdir()
    (p_multi / "hooks" / "hooks.json").write_text('{"hooks": {}}\n')
    (p_multi / "hooks" / "codex-hooks.json").write_text('{"hooks": {}}\n')
    (p_multi / "hooks" / "antigravity-hooks.json").write_text(json.dumps(SAMPLE_HOOKS))

    manifests.write_all(tmp_path)

    # Plain plugin with logo: strict validation passes with 0 findings at all.
    r1 = subprocess.run(
        ["agy", "plugin", "validate", "--strict", "--json", str(p_plain)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r1.returncode == 0, r1.stdout + r1.stderr
    rep1 = json.loads(r1.stdout)
    assert rep1["manifest"] == ".antigravity-plugin/plugin.json"
    assert rep1["components"]["skills"] == 1
    assert rep1["findings"] == []

    # Hooked plugin: strict validation passes with 0 errors and 0 warnings, hooks == 1.
    r2 = subprocess.run(
        ["agy", "plugin", "validate", "--strict", "--json", str(p_hooks)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr
    rep2 = json.loads(r2.stdout)
    assert rep2["components"]["hooks"] == 1
    assert [f for f in rep2["findings"] if f["severity"] in {"error", "warning"}] == []

    # Multi-tool plugin with Claude's hooks/hooks.json: 0 errors, only expected hooks/hooks.json warning.
    r3 = subprocess.run(
        ["agy", "plugin", "validate", "--json", str(p_multi)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r3.returncode == 0, r3.stdout + r3.stderr
    rep3 = json.loads(r3.stdout)
    assert rep3["components"]["hooks"] == 1
    errors = [f for f in rep3["findings"] if f["severity"] == "error"]
    warnings = [f for f in rep3["findings"] if f["severity"] == "warning"]
    assert errors == []
    assert len(warnings) == 1 and warnings[0]["file"] == "hooks/hooks.json"
