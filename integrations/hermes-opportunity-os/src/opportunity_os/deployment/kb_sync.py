"""Thin, explicit invocation of the single AGENTS-declared knowledge sync script."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Mapping

from opportunity_os.deployment.common import ExecutionResult, Runner, execute, require_absolute_path


LIVE_SYNC_SCRIPT = Path("/Users/liujun/.openclaw/workspace/scripts/sync_kb.sh")


class KnowledgeSync:
    def __init__(
        self,
        *,
        runner: Runner = subprocess.run,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.script = require_absolute_path(LIVE_SYNC_SCRIPT, basename="sync_kb.sh")
        self.runner = runner
        self.environ = environ

    def command(self, message: str) -> list[str]:
        if not isinstance(message, str) or not 1 <= len(message) <= 200 or any(ord(char) < 32 for char in message):
            raise ValueError("commit message must be one printable line of at most 200 characters")
        return ["/bin/bash", str(self.script), message]

    def _validate_script(self) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.script, flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("sync script must be a regular file")
        finally:
            os.close(descriptor)

    def run(self, message: str, *, apply: bool = False) -> ExecutionResult:
        command = self.command(message)
        if apply:
            self._validate_script()
        return execute(command, apply=apply, runner=self.runner, environ=self.environ)
