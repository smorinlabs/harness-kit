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


def _write_harness(root: Path, *, vendor_namespace: str | None = None) -> None:
    """harness.toml with an optional vendor_namespace (under [marketplace])."""
    root.mkdir(parents=True, exist_ok=True)
    ns = f'vendor_namespace = "{vendor_namespace}"\n' if vendor_namespace else ""
    (root / "harness.toml").write_text(
        "[marketplace]\n"
        'name = "demo-harness"\n'
        'description = "demo marketplace"\n'
        'version = "0.1.0"\n'
        f"{ns}"
        "[marketplace.owner]\n"
        'name = "A"\n'
        'email = "a@example.com"\n'
    )


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


def _vendor_plugin(root: Path, name: str = "vend", pkg: str = "vpkg", skill: str = "vend") -> Path:
    """A [vendor] plugin with a source package under src/myns/<pkg>."""
    src = root / "src" / "myns" / pkg
    src.mkdir(parents=True, exist_ok=True)
    (src / "mod.py").write_text("X = 1\n")
    pdir = root / "plugins" / name
    (pdir / "skills" / skill).mkdir(parents=True, exist_ok=True)
    (pdir / "skills" / skill / "SKILL.md").write_text("---\nname: v\ndescription: v\n---\n")
    (pdir / "plugin.meta.toml").write_text(
        f'name="{name}"\nversion="0.1.0"\ndescription="d"\nauthor="A"\nkeywords=[]\n'
        f'[vendor]\npackage="{pkg}"\nskill="{skill}"\n'
    )
    return pdir


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


def test_load_meta_missing_key_raises(tmp_path: Path):
    p = tmp_path / "plugin.meta.toml"
    p.write_text('version="0.1.0"\ndescription="d"\n')  # no name
    with pytest.raises(KeyError):
        manifests.load_meta(p)


def test_load_marketplace_meta_missing_key_raises(tmp_path: Path):
    (tmp_path / "harness.toml").write_text('[marketplace]\nname="x"\n')  # no description/version
    with pytest.raises(KeyError):
        manifests.load_marketplace_meta(tmp_path)


def test_render():
    meta = manifests.PluginMeta(
        name="demo", version="0.1.0", description="d", author="A", keywords=["x"]
    )
    cl = manifests.render_claude_plugin(meta)
    cx = manifests.render_codex_plugin(meta)
    assert cl["name"] == "demo" and cl["version"] == "0.1.0"
    assert cl["author"] == {"name": "A"}  # object, per Claude Code's plugin schema
    assert cx["skills"] == "./skills/"
    assert cx["interface"]["displayName"] == "Demo"


def test_render_codex_multiword_title_and_interface_override():
    meta = manifests.PluginMeta(
        name="repo-hygiene", version="0.1.0", description="d", interface={"category": "Custom"}
    )
    cx = manifests.render_codex_plugin(meta)
    assert cx["interface"]["displayName"] == "Repo Hygiene"  # multi-word title-cased
    assert cx["interface"]["category"] == "Custom"  # override wins
    assert cx["interface"]["shortDescription"] == "d"  # default retained


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
    assert mk["metadata"] == {"description": "d", "version": "0.1.0"}
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


def test_byte_stability_and_format(tmp_path: Path):
    """The central promise: byte-stable, 2-space-indented, ascii-escaped output."""
    _harness(tmp_path)
    _md_plugin(tmp_path, "demo", skills=("one",))
    manifests.write_all(tmp_path)
    p = tmp_path / "plugins" / "demo" / ".claude-plugin" / "plugin.json"
    raw = p.read_bytes()
    assert raw.startswith(b'{\n  "_generated"')
    assert raw.endswith(b"}\n")
    assert b"\\u2014" in raw  # em-dash ascii-escaped → byte-stable across locales
    assert b'\n  "keywords": [\n    "x"\n  ]' in raw  # 2-space indent, nested 4
    manifests.write_all(tmp_path)
    assert p.read_bytes() == raw  # byte-identical on regeneration


def test_marketplace_has_no_generated_marker(tmp_path: Path):
    """marketplace.json is regenerated wholesale — no _generated marker (docs must match)."""
    _harness(tmp_path)
    _md_plugin(tmp_path, "demo")
    manifests.write_all(tmp_path)
    mk = json.loads((tmp_path / ".claude-plugin" / "marketplace.json").read_text())
    assert "_generated" not in mk
    cl = json.loads((tmp_path / "plugins" / "demo" / ".claude-plugin" / "plugin.json").read_text())
    assert "_generated" in cl  # per-plugin manifests DO carry it


def test_write_all_with_vendor_integration(tmp_path: Path):
    _write_harness(tmp_path, vendor_namespace="myns")
    _vendor_plugin(tmp_path)
    assert manifests.write_all(tmp_path)  # changed
    vend = tmp_path / "plugins" / "vend" / "skills" / "vend" / "scripts" / "_vendor" / "myns"
    assert (vend / "vpkg" / "mod.py").read_text() == "X = 1\n"
    assert (vend / "__init__.py").exists()
    assert not manifests.write_all(tmp_path)  # idempotent through the full pipeline


def test_vendor_recursive_subpackage(tmp_path: Path):
    _write_harness(tmp_path, vendor_namespace="myns")
    _vendor_plugin(tmp_path)
    sub = tmp_path / "src" / "myns" / "vpkg" / "sub"
    sub.mkdir(parents=True)
    (sub / "deep.py").write_text("Y = 2\n")
    manifests.write_all(tmp_path)
    vend = tmp_path / "plugins" / "vend" / "skills" / "vend" / "scripts" / "_vendor" / "myns"
    assert (vend / "vpkg" / "sub" / "deep.py").read_text() == "Y = 2\n"  # nested vendored


def test_vendor_prunes_stale_file_keeps_others(tmp_path: Path):
    _write_harness(tmp_path, vendor_namespace="myns")
    pdir = _vendor_plugin(tmp_path)
    (tmp_path / "src" / "myns" / "vpkg" / "extra.py").write_text("Y = 2\n")
    manifests.write_all(tmp_path)
    base = pdir / "skills" / "vend" / "scripts" / "_vendor" / "myns" / "vpkg"
    assert (base / "extra.py").exists()
    (tmp_path / "src" / "myns" / "vpkg" / "extra.py").unlink()
    manifests.write_all(tmp_path)
    assert not (base / "extra.py").exists()  # stale file pruned
    assert (base / "mod.py").exists()  # sibling kept


def test_vendor_missing_source_raises(tmp_path: Path):
    _write_harness(tmp_path, vendor_namespace="myns")
    pdir = tmp_path / "plugins" / "vend"
    pdir.mkdir(parents=True)
    (pdir / "plugin.meta.toml").write_text(
        'name="vend"\nversion="0.1.0"\ndescription="d"\n[vendor]\npackage="ghost"\nskill="vend"\n'
    )
    with pytest.raises(ValueError, match="missing or has no .py"):
        manifests.write_all(tmp_path)


def test_orphan_vendor_swept(tmp_path: Path):
    """F1: dropping [vendor] must prune the orphaned _vendor tree — and --check must see it."""
    _write_harness(tmp_path, vendor_namespace="myns")
    pdir = _vendor_plugin(tmp_path)
    manifests.write_all(tmp_path)
    vend = pdir / "skills" / "vend" / "scripts" / "_vendor" / "myns"
    assert vend.is_dir()
    # drop the [vendor] table → plugin becomes markdown-only
    (pdir / "plugin.meta.toml").write_text(
        'name="vend"\nversion="0.1.0"\ndescription="d"\nauthor="A"\nkeywords=[]\n'
    )
    assert manifests.write_all(tmp_path, dry_run=True)  # --check DETECTS the orphan
    assert vend.is_dir()  # dry-run did not delete
    manifests.write_all(tmp_path)  # real run prunes it
    assert not vend.exists()
    assert not manifests.write_all(tmp_path)  # now clean


def test_write_all_vendor_without_namespace_raises(tmp_path: Path):
    _write_harness(tmp_path)  # no vendor_namespace
    _vendor_plugin(tmp_path)
    with pytest.raises(ValueError, match="vendor_namespace"):
        manifests.write_all(tmp_path)


def test_vendor_requires_namespace(tmp_path: Path):
    pl = tmp_path / "plugins" / "demo"
    pl.mkdir(parents=True)
    (pl / "plugin.meta.toml").write_text(
        'name="demo"\nversion="0.1.0"\ndescription="d"\n[vendor]\npackage="p"\nskill="demo"\n'
    )
    meta = manifests.load_meta(pl / "plugin.meta.toml")
    with pytest.raises(ValueError):
        manifests.vendor_plugin(tmp_path, meta, "")
