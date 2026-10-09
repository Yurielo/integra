#!/usr/bin/env python3
"""Reject retained Candidate bytes as executable/importable test workspaces.

This is an offline, read-only guard, not archive verification or an ownership
grant. Validate before importing Candidate code. Execute retained bytes only
from a separate admitted, owned execution copy; never relax archive inventory
or permission modes to make a test run.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys

MANAGED_NAMES = ("Build Archive", "Recovery Archive", "Build Archive Recovery",
                 "Candidate Builds", "Validation")


def managed_roots(environment: dict[str, str]) -> tuple[Path, ...]:
    base = Path.home() / "Library/Application Support/Integra"
    roots = [base / name for name in MANAGED_NAMES]
    configured = environment.get("INTEGRA_RETENTION_ARCHIVE_ROOT")
    if configured:
        roots.append(Path(configured).expanduser())
    return tuple(roots)


def _within(path: Path, root: Path) -> bool:
    # Existing filesystem identity handles case aliases on macOS, while
    # unresolved suffixes retain exact path-component containment semantics.
    path, root = path.expanduser().resolve(), root.expanduser().resolve()
    anchor = root
    missing: tuple[str, ...] = ()
    while not anchor.exists():
        missing = (anchor.name, *missing)
        anchor = anchor.parent
    for ancestor in (path, *path.parents):
        try:
            if ancestor.samefile(anchor):
                return path.relative_to(ancestor).parts[:len(missing)] == missing
        except (FileNotFoundError, NotADirectoryError):
            continue
    return False


def require_execution_path(path: Path, *, roots: tuple[Path, ...] | None = None,
                           environment: dict[str, str] | None = None) -> None:
    environment = dict(os.environ) if environment is None else environment
    resolved = path.expanduser().resolve()
    try:
        for root in managed_roots(environment) if roots is None else roots:
            if _within(resolved, root):
                raise ValueError("PROTECTED_ARCHIVE_EXECUTION_REJECTED: " + str(resolved))
        # Custom historical/test archives outside the managed base remain
        # protected. Even interrupted packages are not executable workspaces.
        for ancestor in (resolved, *resolved.parents):
            inventory = (ancestor / "inventory.json").is_file()
            completion = (ancestor / "COMPLETE.json").is_file()
            candidate = ((ancestor / "Integra.app").is_dir()
                         or (ancestor / "candidate-manifest.json").is_file())
            if ((inventory and completion) or (candidate and (inventory or completion))):
                raise ValueError("PROTECTED_ARCHIVE_EXECUTION_REJECTED: " + str(resolved))
    except OSError as error:
        raise ValueError("ARCHIVE_EXECUTION_GUARD_UNAVAILABLE: " + str(error)) from error


def validate_review_execution(repo: Path, interpreter: str, arguments: list[str],
                              environment: dict[str, str] | None = None) -> None:
    environment = dict(os.environ) if environment is None else environment
    paths = [repo, Path.cwd()]
    executable = shutil.which(interpreter, path=environment.get("PATH"))
    if executable is None:
        raise ValueError("TEST_INTERPRETER_UNAVAILABLE: " + interpreter)
    paths.append(Path(executable))
    for key in ("PYTHONPATH", "INTEGRA_TEST_REVIEW_PYTHONPATH"):
        if key in environment:
            paths.extend(Path(value or ".") for value in environment[key].split(os.pathsep))
    for key in ("INTEGRA_CANDIDATE_APP", "INTEGRA_OWNED_WORKSPACE"):
        if environment.get(key):
            paths.append(Path(environment[key]))
    for argument in arguments:
        if argument.startswith("--"):
            value = argument.split("=", 1)[-1]
        elif argument.startswith(("-s", "-t")) and len(argument) > 2:
            # argparse also accepts attached short options: -s/path, -t/path.
            value = argument[2:]
        else:
            value = argument
        if value and ("/" in value or Path(value).exists()):
            paths.append(Path(value))
    for path in paths:
        require_execution_path(path, environment=environment)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--interpreter", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        validate_review_execution(args.repo, args.interpreter, args.arguments)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
