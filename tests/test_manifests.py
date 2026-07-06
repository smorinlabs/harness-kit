import json
from pathlib import Path

import pytest

from harness_kit import manifests

HARNESS_TOML = (
    "[marketplace]\n"
    'name = "demo-harness"\n'
    'description = "demo marketplace"\n'
    'version = "0.1.0"\n'
    "[marketplace.owner]\n"
    'name = "A"\n'
    'email = "a@example.com"\n'
)


def _harness(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "harness.toml").write_text(HARNESS_TOML)


def _md_plugin(root: Path, name: str = "demo", skills: tuple[str, ...] = ("one", "two")) -> Path:
    """A markdown-only, multi-skill plugin (no [vendor])."""
    pdir = root / "plugins" / name
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "plugin.meta.toml").write_text(
        f'name="{name}"\nversion="0.1.0"\ndescription="d"\nauthor="A"\nkeywords=["x"]\n'
    )
    for s in skills:
        sd = pdir / "skills" / s
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "SKILL.md").write_text(f"---\nname: {s}\ndescription: {s}\n---\n")
    return pdir / "plugin.meta.toml"


def test_load_meta(tmp_path: Path):
    meta = manifests.load_meta(_md_plugin(tmp_path, "demo"))
    assert meta.name == "demo"
    assert meta.version == "0.1.0"
    assert meta.keywords == ["x"]
    assert meta.vendor == {}


def test_load_marketplace_meta(tmp_path: Path):
    _harness(tmp_path)
    mkt = manifests.load_marketplace_meta(tmp_path)
    assert mkt.name == "demo-harness"
    assert mkt.owner == {"name": "A", "email": "a@example.com"}
    assert mkt.vendor_namespace == ""


def test_render():
    meta = manifests.PluginMeta(
        name="demo", version="0.1.0", description="d", author="A", keywords=["x"]
    )
    cl = manifests.render_claude_plugin(meta)
    cx = manifests.render_codex_plugin(meta)
    assert cl["name"] == "demo" and cl["version"] == "0.1.0"
    assert cx["skills"] == "./skills/"
    assert cx["interface"]["displayName"] == "Demo"


def test_render_marketplace_parameterized():
    mkt = manifests.MarketplaceMeta(
        name="demo-harness", description="d", version="0.1.0", owner={"name": "A"}
    )
    metas = [
        manifests.PluginMeta(name="a", version="0.1.0", description="da"),
        manifests.PluginMeta(name="b", version="0.2.0", description="db"),
    ]
    mk = manifests.render_marketplace(metas, mkt)
    assert mk["name"] == "demo-harness"  # parameterized, not hard-coded
    assert mk["owner"] == {"name": "A"}
    assert [p["name"] for p in mk["plugins"]] == ["a", "b"]
    assert mk["plugins"][0]["source"] == "./plugins/a"


def test_write_all_markdown_only_multiskill(tmp_path: Path):
    """The key generalization: a markdown-only, multi-skill plugin generates cleanly."""
    _harness(tmp_path)
    _md_plugin(tmp_path, "demo", skills=("one", "two"))
    changed1 = manifests.write_all(tmp_path)
    changed2 = manifests.write_all(tmp_path)
    assert changed1 and not changed2  # idempotent
    cl = tmp_path / "plugins" / "demo" / ".claude-plugin" / "plugin.json"
    cx = tmp_path / "plugins" / "demo" / ".codex-plugin" / "plugin.json"
    mk = tmp_path / ".claude-plugin" / "marketplace.json"
    assert cl.exists() and cx.exists() and mk.exists()
    assert json.loads(mk.read_text())["name"] == "demo-harness"
    assert json.loads(cx.read_text())["skills"] == "./skills/"
    # markdown-only → no vendoring occurred
    assert not (tmp_path / "plugins" / "demo" / "skills" / "one" / "scripts").exists()


def test_write_all_dry_run_does_not_write(tmp_path: Path):
    _harness(tmp_path)
    _md_plugin(tmp_path, "demo")
    assert manifests.write_all(tmp_path, dry_run=True)
    assert not (tmp_path / ".claude-plugin" / "marketplace.json").exists()


def test_vendor_plugin_with_namespace(tmp_path: Path):
    _harness(tmp_path)
    pkg = tmp_path / "src" / "myns" / "demo_pkg"
    pkg.mkdir(parents=True)
    (pkg / "mod.py").write_text("X = 1\n")
    pl = tmp_path / "plugins" / "demo"
    pl.mkdir(parents=True)
    (pl / "plugin.meta.toml").write_text(
        'name="demo"\nversion="0.1.0"\ndescription="d"\nauthor="A"\nkeywords=[]\n'
        '[vendor]\npackage="demo_pkg"\nskill="demo"\n'
    )
    meta = manifests.load_meta(pl / "plugin.meta.toml")
    base = pl / "skills" / "demo" / "scripts" / "_vendor" / "myns"
    assert manifests.vendor_plugin(tmp_path, meta, "myns") is True
    assert (base / "demo_pkg" / "mod.py").read_text() == "X = 1\n"
    assert manifests.vendor_plugin(tmp_path, meta, "myns") is False  # idempotent
    (pkg / "mod.py").unlink()
    assert manifests.vendor_plugin(tmp_path, meta, "myns") is True  # prunes stale
    assert not (base / "demo_pkg" / "mod.py").exists()


def test_vendor_requires_namespace(tmp_path: Path):
    pl = tmp_path / "plugins" / "demo"
    pl.mkdir(parents=True)
    (pl / "plugin.meta.toml").write_text(
        'name="demo"\nversion="0.1.0"\ndescription="d"\n[vendor]\npackage="p"\nskill="demo"\n'
    )
    meta = manifests.load_meta(pl / "plugin.meta.toml")
    with pytest.raises(ValueError):
        manifests.vendor_plugin(tmp_path, meta, "")
