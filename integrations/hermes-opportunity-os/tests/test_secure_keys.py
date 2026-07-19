import os
from pathlib import Path

from opportunity_os.secure_keys import write_env_keys


def test_write_env_keys_is_atomic_private_and_contains_only_expected_names(tmp_path: Path) -> None:
    destination = tmp_path / ".env"

    write_env_keys(destination, "value-one", "value-two")

    assert destination.read_text(encoding="utf-8") == (
        "OPENCODE_GO_API_KEY=value-one\nDEEPSEEK_API_KEY=value-two\n"
    )
    assert os.stat(destination).st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob("*.tmp"))


def test_write_env_keys_rejects_empty_or_multiline_values(tmp_path: Path) -> None:
    destination = tmp_path / ".env"

    for bad_value in ("", "line-one\nline-two", "with\rcarriage"):
        try:
            write_env_keys(destination, bad_value, "valid")
        except ValueError:
            pass
        else:
            raise AssertionError("invalid key must be rejected")


def test_write_env_keys_preserves_unrelated_profile_settings(tmp_path: Path) -> None:
    destination = tmp_path / ".env"
    destination.write_text("PROFILE_NOTE=private\nOPENCODE_GO_API_KEY=old\n", encoding="utf-8")

    write_env_keys(destination, "new-one", "new-two")

    text = destination.read_text(encoding="utf-8")
    assert "PROFILE_NOTE=private\n" in text
    assert text.count("OPENCODE_GO_API_KEY=") == 1
    assert text.count("DEEPSEEK_API_KEY=") == 1
