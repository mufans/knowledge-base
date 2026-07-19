"""Safe dashboard launchd asset and official ngrok service adapter."""

from __future__ import annotations

import os
import plistlib
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from opportunity_os.deployment.common import ExecutionResult, Runner, execute, require_absolute_path


_EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_SERVICE_ACTIONS = frozenset({"install", "start", "restart", "status"})


def render_github_policy(identity: str) -> str:
    if not isinstance(identity, str) or len(identity) > 254 or not _EMAIL.fullmatch(identity):
        raise ValueError("GitHub OAuth identity must be one safe email address")
    return (
        "on_http_request:\n"
        "  - actions:\n"
        "      - type: oauth\n"
        "        config:\n"
        "          provider: github\n"
        "          idle_session_timeout: 15m\n"
        "          max_session_duration: 8h\n"
        "  - expressions:\n"
        f"      - \"!(actions.ngrok.oauth.identity.email in ['{identity}'])\"\n"
        "    actions:\n"
        "      - type: deny\n"
        "        config:\n"
        "          status_code: 403\n"
    )


def write_github_policy(destination: str | Path, identity: str, *, apply: bool = False) -> InstallResult:
    target = require_absolute_path(destination)
    if target.suffix not in {".yml", ".yaml"}:
        raise ValueError("traffic policy destination must be YAML")
    rendered = render_github_policy(identity).encode("utf-8")
    if not apply:
        return InstallResult(target, False)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise ValueError("traffic policy parent must be a non-symlink directory")
    if target.exists() and not stat.S_ISREG(target.lstat().st_mode):
        raise ValueError("traffic policy destination must be a regular file")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = ""
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return InstallResult(target, True)


@dataclass(frozen=True, slots=True)
class InstallResult:
    destination: Path
    applied: bool


class DashboardLaunchAgent:
    LABEL = "com.opportunity-os.dashboard"

    def __init__(self, *, executable: str | Path, private_home: str | Path, port: int = 8765) -> None:
        self.executable = require_absolute_path(executable, basename="opportunity-os")
        self.private_home = require_absolute_path(private_home)
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("dashboard port must be between 1024 and 65535")
        self.port = port

    def render(self) -> bytes:
        payload = {
            "Label": self.LABEL,
            "ProgramArguments": [
                str(self.executable), "dashboard", "serve",
                "--home", str(self.private_home),
                "--host", "127.0.0.1",
                "--port", str(self.port),
            ],
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ProcessType": "Background",
            "ThrottleInterval": 10,
            "WorkingDirectory": str(self.private_home),
        }
        return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)

    def install(self, destination: str | Path, *, apply: bool = False) -> InstallResult:
        target = require_absolute_path(destination)
        if target.name != f"{self.LABEL}.plist" or target.parent.name != "LaunchAgents":
            raise ValueError("LaunchAgent destination must use the standard label under LaunchAgents")
        if not apply:
            return InstallResult(target, False)
        if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
            raise ValueError("opportunity-os executable must exist and be executable")
        if not self.private_home.is_dir() or self.private_home.is_symlink():
            raise ValueError("private home must be an existing non-symlink directory")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.parent.is_symlink() or not target.parent.is_dir():
            raise ValueError("LaunchAgent parent must be a non-symlink directory")
        if target.exists() and not stat.S_ISREG(target.lstat().st_mode):
            raise ValueError("LaunchAgent destination must be a regular file")
        descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(self.render())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            temporary = ""
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
        return InstallResult(target, True)


class NgrokService:
    """Call ngrok's native service manager; never synthesize an ngrok plist."""

    def __init__(
        self,
        *,
        executable: str | Path,
        config: str | Path,
        runner: Runner = subprocess.run,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.executable = require_absolute_path(executable, basename="ngrok")
        self.config = require_absolute_path(config)
        self.runner = runner
        self.environ = environ

    def command(self, action: str) -> list[str]:
        if action not in _SERVICE_ACTIONS:
            raise ValueError("unsupported ngrok service action")
        command = [str(self.executable), "service", action]
        if action == "install":
            command.extend(["--config", str(self.config)])
        return command

    def check_command(self) -> list[str]:
        return [str(self.executable), "config", "check", "--config", str(self.config)]

    def run(self, action: str, *, apply: bool = False) -> ExecutionResult:
        if apply and action in {"install", "start", "restart"}:
            self._validate_config()
        if apply and action == "install":
            execute(self.check_command(), apply=True, runner=self.runner, environ=self.environ)
        return execute(self.command(action), apply=apply, runner=self.runner, environ=self.environ)

    def _validate_config(self) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.config, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 262_144:
                raise ValueError("ngrok config must be a small regular file")
            if info.st_mode & 0o077:
                raise ValueError("ngrok config permissions must be 0600 or stricter")
            with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as handle:
                rendered = handle.read()
        finally:
            os.close(descriptor)
        if not re.search(r"(?m)^\s*url:\s*http://127\.0\.0\.1:[0-9]{4,5}\s*$", rendered):
            raise ValueError("ngrok upstream must target the loopback dashboard")
        required = (
            "version: 3",
            "authtoken:",
            "name: opportunity-os-dashboard",
            "url: https://",
            "provider: github",
            "type: oauth",
            "actions.ngrok.oauth.identity.email",
            "type: deny",
        )
        if any(item not in rendered for item in required):
            raise ValueError("ngrok config must enforce GitHub OAuth and deny unauthorized users")
        if "__NGROK_AUTHTOKEN__" in rendered or "__OWNER_GITHUB_EMAIL__" in rendered:
            raise ValueError("ngrok config placeholders must be replaced before apply")
