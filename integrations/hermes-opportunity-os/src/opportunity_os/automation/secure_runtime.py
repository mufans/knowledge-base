"""Small POSIX helpers for no-follow runtime directories and serialized locks."""

from __future__ import annotations

import fcntl
import json
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping

from opportunity_os.errors import BoundaryError, CapacityError, ValidationError


SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _safe_name(name: str) -> None:
    if not SAFE_NAME.fullmatch(name) or name in {".", ".."}:
        raise BoundaryError("runtime name is not a safe single path component")


def open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or ".." in path.parts:
        raise BoundaryError("runtime directory must be an absolute traversal-free path")
    current_fd = os.open(path.anchor, DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            try:
                next_fd = os.open(part, DIRECTORY_FLAGS, dir_fd=current_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                try:
                    next_fd = os.open(part, DIRECTORY_FLAGS, dir_fd=current_fd)
                except OSError as error:
                    raise BoundaryError("runtime directory could not be created safely") from error
            except OSError as error:
                raise BoundaryError("runtime path contains a symlink or non-directory") from error
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def open_child_directory(parent_fd: int, name: str) -> int:
    _safe_name(name)
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    try:
        return os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as error:
        raise BoundaryError(f"runtime child directory is unsafe: {name}") from error


def atomic_json_at(
    directory_fd: int,
    name: str,
    payload: Mapping[str, object],
    *,
    mode: int = 0o600,
    max_bytes: int = 1_048_576,
) -> None:
    _safe_name(name)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
    if max_bytes < 2 or len(rendered) > max_bytes:
        raise CapacityError("runtime JSON exceeds its encoded size limit")
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        mode,
        dir_fd=directory_fd,
    )
    try:
        written = 0
        while written < len(rendered):
            written += os.write(descriptor, rendered[written:])
        os.fsync(descriptor)
        os.fchmod(descriptor, mode)
    finally:
        os.close(descriptor)
    try:
        os.rename(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def read_json_at(
    directory_fd: int,
    name: str,
    *,
    max_bytes: int = 1_048_576,
) -> dict[str, object]:
    _safe_name(name)
    if max_bytes < 2:
        raise ValidationError("runtime JSON size limit is invalid")
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise BoundaryError("runtime JSON path is unsafe") from error
    try:
        stat_result = os.fstat(descriptor)
        if stat_result.st_size > max_bytes:
            raise ValidationError("runtime JSON exceeds its size limit")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        rendered = b"".join(chunks)
        if len(rendered) > max_bytes:
            raise ValidationError("runtime JSON exceeds its size limit")
        payload = json.loads(rendered)
    finally:
        os.close(descriptor)
    if not isinstance(payload, dict):
        raise ValidationError("runtime JSON must contain an object")
    return payload


@contextmanager
def exclusive_arbitration(directory_fd: int, name: str) -> Iterator[None]:
    _safe_name(name)
    descriptor = None
    for _ in range(3):
        try:
            descriptor = os.open(name, os.O_RDWR | os.O_NOFOLLOW, dir_fd=directory_fd)
            break
        except FileNotFoundError:
            try:
                descriptor = os.open(
                    name,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory_fd,
                )
                break
            except FileExistsError:
                continue
            except OSError as error:
                raise BoundaryError("runtime arbitration file is unsafe") from error
        except OSError as error:
            raise BoundaryError("runtime arbitration file is unsafe") from error
    if descriptor is None:
        raise BoundaryError("runtime arbitration file could not be opened")
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
