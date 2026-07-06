from pathlib import Path

from harness_kit import cli

HARNESS = (
    "[marketplace]\n"
    'name = "demo-harness"\n'
    'description = "d"\n'
    'version = "0.1.0"\n'
    "[marketplace.owner]\n"
    'name = "A"\n'
    'email = "a@example.com"\n'
)


def _repo(root: Path) -> Path:
    (root / "harness.toml").write_text(HARNESS)
    pdir = root / "plugins" / "demo"
    (pdir / "skills" / "s").mkdir(parents=True)
    (pdir / "skills" / "s" / "SKILL.md").write_text("---\nname: s\ndescription: s\n---\n")
    (pdir / "plugin.meta.toml").write_text(
        'name="demo"\nversion="0.1.0"\ndescription="d"\nauthor="A"\nkeywords=[]\n'
    )
    return root


def test_cli_gen_writes_and_returns_0(tmp_path: Path):
    _repo(tmp_path)
    assert cli.main(["gen", "--root", str(tmp_path)]) == 0
    assert (tmp_path / ".claude-plugin" / "marketplace.json").exists()


def test_cli_check_clean_returns_0(tmp_path: Path):
    _repo(tmp_path)
    cli.main(["gen", "--root", str(tmp_path)])
    assert cli.main(["gen", "--check", "--root", str(tmp_path)]) == 0


def test_cli_check_stale_returns_1(tmp_path: Path):
    _repo(tmp_path)  # never generated → stale
    assert cli.main(["gen", "--check", "--root", str(tmp_path)]) == 1


def test_cli_root_default_is_cwd(tmp_path: Path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["gen"]) == 0
    assert (tmp_path / ".claude-plugin" / "marketplace.json").exists()


def test_cli_missing_harness_toml_is_friendly(tmp_path: Path, capsys):
    (tmp_path / "plugins").mkdir()
    rc = cli.main(["gen", "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "harness-kit:" in err and "Traceback" not in err


def test_cli_missing_config_key_is_friendly(tmp_path: Path, capsys):
    (tmp_path / "harness.toml").write_text('[marketplace]\nname="x"\n')  # no description/version
    rc = cli.main(["gen", "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "missing required config key" in err and "Traceback" not in err


def test_cli_vendor_without_namespace_is_friendly(tmp_path: Path, capsys):
    (tmp_path / "harness.toml").write_text(HARNESS)  # no vendor_namespace
    pdir = tmp_path / "plugins" / "vend"
    pdir.mkdir(parents=True)
    (pdir / "plugin.meta.toml").write_text(
        'name="vend"\nversion="0.1.0"\ndescription="d"\n[vendor]\npackage="p"\nskill="vend"\n'
    )
    rc = cli.main(["gen", "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "vendor_namespace" in err and "Traceback" not in err
