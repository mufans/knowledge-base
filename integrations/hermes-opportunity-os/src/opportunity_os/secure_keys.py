import argparse
import getpass
import os
import tempfile
from pathlib import Path
from typing import Sequence


KEY_NAMES = ("OPENCODE_GO_API_KEY", "DEEPSEEK_API_KEY")


def _validate_secret(value: str) -> None:
    if not value or "\n" in value or "\r" in value:
        raise ValueError("API Key 不能为空或包含换行")


def write_env_keys(path: str | Path, opencode_go_key: str, deepseek_key: str) -> None:
    _validate_secret(opencode_go_key)
    _validate_secret(deepseek_key)
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    preserved: list[str] = []
    if destination.exists():
        for line in destination.read_text(encoding="utf-8").splitlines():
            if not any(line.startswith(f"{name}=") for name in KEY_NAMES):
                preserved.append(line)
    lines = [*preserved, f"{KEY_NAMES[0]}={opencode_go_key}", f"{KEY_NAMES[1]}={deepseek_key}"]
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Securely enter Hermes provider keys with terminal echo disabled.")
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args(argv)
    opencode_go_key = getpass.getpass("OpenCode Go API Key: ")
    deepseek_key = getpass.getpass("DeepSeek API Key: ")
    write_env_keys(args.env_file, opencode_go_key, deepseek_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
