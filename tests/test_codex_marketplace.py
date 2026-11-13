"""Repo-level Codex marketplace: ``.agents/plugins/marketplace.json``.

Schema source: https://developers.openai.com/plugins/build/plugins#marketplace-metadata
(checked against codex-cli 0.167.2). Every plugin entry needs ``name``,
``source`` ({source: "local", path}), ``policy`` (installation, authentication)
and ``category``; the marketplace needs ``name`` and ``interface.displayName``.
"""

import json
from pathlib import Path

from harness_kit import cli, manifests

CODEX_MKT = Path(".agents") / "plugins" / "marketplace.json"


def _harness(root: Path, extra: str = "") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "harness.toml").write_text(
        "[marketplace]\n"
        'name = "demo-harness"\n'
        'description = "demo marketplace"\n'
        'version = "0.1.0"\n'
        f"{extra}"
        "[marketplace.owner]\n"
        'name = "A"\n'
    )


def _plugin(root: Path, name: str, extra: str = "") -> Path:
    pdir = root / "plugins" / name
    (pdir / "skills" / name).mkdir(parents=True, exist_ok=True)
    (pdir / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
    (pdir / "plugin.meta.toml").write_text(
        f'name="{name}"\nversion="0.1.0"\ndescription="d"\nauthor="A"\nkeywords=[]\n{extra}'
    )
    return pdir


def _fixture(root: Path) -> None:
    """2 Codex-capable plugins + 1 Claude-only plugin (codex = false)."""
    _harness(root)
    _plugin(root, "alpha")
    _plugin(root, "beta", extra='[interface]\ncategory = "Productivity"\n')
    _plugin(root, "claude-only", extra="codex = false\n")


def _assert_codex_marketplace_shape(doc: dict) -> None:
    """Structural pin of the documented Codex marketplace schema."""
    assert set(doc) == {"name", "interface", "plugins"}
    assert isinstance(doc["name"], str) and doc["name"]
    assert isinstance(doc["interface"]["displayName"], str) and doc["interface"]["displayName"]
    for p in doc["plugins"]:
        assert set(p) == {"name", "source", "policy", "category"}
        assert p["source"]["source"] == "local"
        assert p["source"]["path"].startswith("./")
        assert p["policy"]["installation"] in {"AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"}
        assert p["policy"]["authentication"] in {"ON_INSTALL", "ON_USE"}
        assert isinstance(p["category"], str) and p["category"]


# TS01
def test_lists_exactly_codex_capable_plugins(tmp_path: Path):
    _fixture(tmp_path)
    manifests.write_all(tmp_path)
    doc = json.loads((tmp_path / CODEX_MKT).read_text())
    assert [p["name"] for p in doc["plugins"]] == ["alpha", "beta"]
    # The Claude marketplace still lists all three.
    claude = json.loads((tmp_path / ".claude-plugin" / "marketplace.json").read_text())
    assert [p["name"] for p in claude["plugins"]] == ["alpha", "beta", "claude-only"]
    # A Claude-only plugin gets no Codex plugin manifest either.
    assert not (tmp_path / "plugins" / "claude-only" / ".codex-plugin" / "plugin.json").exists()


def test_entry_defaults_and_category_follows_codex_plugin(tmp_path: Path):
    _fixture(tmp_path)
    manifests.write_all(tmp_path)
    doc = json.loads((tmp_path / CODEX_MKT).read_text())
    alpha, beta = doc["plugins"]
    assert alpha == {
        "name": "alpha",
        "source": {"source": "local", "path": "./plugins/alpha"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }
    assert beta["category"] == "Productivity"  # same value as its .codex-plugin/plugin.json
    cx = json.loads((tmp_path / "plugins" / "beta" / ".codex-plugin" / "plugin.json").read_text())
    assert cx["interface"]["category"] == beta["category"]


def test_display_name_default_and_override(tmp_path: Path):
    _fixture(tmp_path)
    manifests.write_all(tmp_path)
    doc = json.loads((tmp_path / CODEX_MKT).read_text())
    assert doc["name"] == "demo-harness"
    assert doc["interface"] == {"displayName": "Demo Harness"}

    _harness(tmp_path, extra='display_name = "Demo Plugins"\n')
    manifests.write_all(tmp_path)
    doc = json.loads((tmp_path / CODEX_MKT).read_text())
    assert doc["interface"] == {"displayName": "Demo Plugins"}


# TS02
def test_check_fails_when_missing_or_stale(tmp_path: Path):
    _fixture(tmp_path)
    root = str(tmp_path)
    assert cli.main(["gen", "--root", root]) == 0
    assert cli.main(["gen", "--check", "--root", root]) == 0

    (tmp_path / CODEX_MKT).unlink()
    assert cli.main(["gen", "--check", "--root", root]) == 1
    assert cli.main(["gen", "--root", root]) == 0
    assert cli.main(["gen", "--check", "--root", root]) == 0

    (tmp_path / CODEX_MKT).write_text('{"name": "stale"}\n')
    assert cli.main(["gen", "--check", "--root", root]) == 1
    assert cli.main(["gen", "--root", root]) == 0
    assert cli.main(["gen", "--check", "--root", root]) == 0


def test_flipping_to_claude_only_prunes_codex_plugin_manifest(tmp_path: Path):
    _harness(tmp_path)
    pdir = _plugin(tmp_path, "alpha")
    manifests.write_all(tmp_path)
    cx = pdir / ".codex-plugin" / "plugin.json"
    assert cx.exists()

    (pdir / "plugin.meta.toml").write_text(
        'name="alpha"\nversion="0.1.0"\ndescription="d"\nauthor="A"\nkeywords=[]\ncodex = false\n'
    )
    assert manifests.write_all(tmp_path, dry_run=True)  # --check sees the leftover
    assert cx.exists()  # dry run does not delete
    assert manifests.write_all(tmp_path)
    assert not cx.exists()
    assert not manifests.write_all(tmp_path, dry_run=True)


def test_codex_key_must_be_boolean(tmp_path: Path):
    _harness(tmp_path)
    _plugin(tmp_path, "alpha", extra='codex = "no"\n')
    assert cli.main(["gen", "--root", str(tmp_path)]) == 1


# TS03
def test_output_matches_codex_schema_and_is_byte_stable(tmp_path: Path):
    _fixture(tmp_path)
    manifests.write_all(tmp_path)
    raw = (tmp_path / CODEX_MKT).read_bytes()
    _assert_codex_marketplace_shape(json.loads(raw))
    assert raw.endswith(b"}\n")
    manifests.write_all(tmp_path)
    assert (tmp_path / CODEX_MKT).read_bytes() == raw
