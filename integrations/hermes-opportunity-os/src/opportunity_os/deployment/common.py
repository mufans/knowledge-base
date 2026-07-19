"""Shared fixed-argv execution primitives for deployment helpers."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


SAFE_ENV_KEYS = ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def safe_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    values = os.environ if source is None else source
    return {key: values[key] for key in SAFE_ENV_KEYS if key in values}


def require_absolute_path(path: str | Path, *, basename: str | None = None) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("path must be absolute without parent traversal")
    if basename is not None and candidate.name != basename:
        raise ValueError(f"path basename must be {basename}")
    return candidate


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    argv: tuple[str, ...]
    applied: bool
    returncode: int | None = None


def execute(
    argv: Sequence[str],
    *,
    apply: bool,
    runner: Runner = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> ExecutionResult:
    command = [str(part) for part in argv]
    if not apply:
        return ExecutionResult(tuple(command), False)
    result = runner(
        command,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env=safe_environment(environ),
    )
    if result.returncode != 0:
        raise RuntimeError(f"native command failed with exit code {result.returncode}")
    return ExecutionResult(tuple(command), True, result.returncode)
