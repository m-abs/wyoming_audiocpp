#!/usr/bin/env python3
"""Update the project version in pyproject.toml.

The version is the single source of truth for releases; CI reads it from
`pyproject.toml`. Use this to set or bump the base version (e.g. `0.2.0`) as
part of a release PR. RC versions (`0.2.0-rc1`) are computed by the Docker
workflow on push to the `rc` branch, so they are not managed here.

Usage:
    python scripts/bump_version.py --show
    python scripts/bump_version.py --set 0.3.0
    python scripts/bump_version.py --bump minor
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def find_pyproject() -> Path:
    # scripts/ lives in the repo root; pyproject.toml is its parent.
    return Path(__file__).resolve().parent.parent / "pyproject.toml"


def read_version(pyproject: Path) -> str:
    import tomllib

    data = tomllib.load(pyproject.open("rb"))
    version = data["project"]["version"]
    if not isinstance(version, str):
        raise SystemExit(f"Version in {pyproject} is not a string: {version!r}")
    return version


def write_version(pyproject: Path, version: str) -> None:
    text = pyproject.read_text()
    new_text, n = re.subn(r'(version\s*=\s*)"([^"]+)"', rf'\1"{version}"', text)
    if n != 1:
        raise SystemExit(f"Could not find a single `version = \"...\"` in {pyproject}")
    pyproject.write_text(new_text)


def bump(version: str, kind: str) -> str:
    # Operate on the base version; strip any -rcN suffix.
    base = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not base:
        raise SystemExit(f"Cannot parse version {version!r} (expected MAJOR.MINOR.PATCH)")
    major, minor, patch = int(base.group(1)), int(base.group(2)), int(base.group(3))
    if kind == "major":
        major, minor, patch = major + 1, 0, 0
    elif kind == "minor":
        minor, patch = minor + 1, 0
    else:  # patch
        patch += 1
    return f"{major}.{minor}.{patch}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Update the project version in pyproject.toml")
    parser.add_argument("--pyproject", type=Path, default=None,
                        help="Path to pyproject.toml (default: repo root)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--set", metavar="VERSION",
                       help="Set the version explicitly (e.g. 0.3.0)")
    group.add_argument("--bump", choices=["patch", "minor", "major"],
                       help="Bump the base version")
    parser.add_argument("--show", action="store_true",
                        help="Print the current version and exit")
    args = parser.parse_args()

    pyproject = args.pyproject or find_pyproject()
    if not pyproject.exists():
        raise SystemExit(f"{pyproject} does not exist")
    current = read_version(pyproject)

    if args.show:
        print(current)
        return

    if args.set:
        new = args.set
    elif args.bump:
        new = bump(current, args.bump)
    else:
        parser.print_help()
        raise SystemExit(1)

    write_version(pyproject, new)
    print(f"version: {current} -> {new}")


if __name__ == "__main__":
    main()
