"""harness-kit CLI: generate/check plugin manifests for a harness repo."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from harness_kit import manifests


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="harness-kit")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("gen", help="write/update plugin manifests")
    gen.add_argument("--check", action="store_true", help="fail (exit 1) if anything is stale")
    gen.add_argument("--root", default=".", help="harness repo root (default: cwd)")
    args = parser.parse_args(argv)

    # args.command is always "gen" here (single, required subcommand).
    root = Path(args.root).resolve()
    try:
        changed = manifests.write_all(root, dry_run=args.check)
    except FileNotFoundError as e:
        print(f"harness-kit: file not found: {e.filename}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"harness-kit: missing required config key {e}", file=sys.stderr)
        return 1
    except (ValueError, tomllib.TOMLDecodeError) as e:
        print(f"harness-kit: {e}", file=sys.stderr)
        return 1
    if args.check and changed:
        print("manifests out of date — run `harness-kit gen`", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
