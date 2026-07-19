import plistlib
from pathlib import Path

import pytest

from opportunity_os.deployment.remote_access import (
    DashboardLaunchAgent,
    NgrokService,
    render_github_policy,
)


NGROK_TEMPLATE = Path(__file__).parents[2] / "deployment/ngrok/ngrok.yml.template"


def test_github_policy_authenticates_then_denies_every_other_identity() -> None:
    rendered = render_github_policy("owner@example.com")
    assert "provider: github" in rendered
    assert "actions.ngrok.oauth.identity.email" in rendered
    assert "owner@example.com" in rendered
    assert "type: deny" in rendered
    assert rendered.index("type: oauth") < rendered.index("type: deny")
    assert "client_secret" not in rendered


@pytest.mark.parametrize("identity", ["", "a' || true", "two@example.com,three@example.com", "line\nbreak"])
def test_github_policy_rejects_unsafe_identity(identity: str) -> None:
    with pytest.raises(ValueError):
        render_github_policy(identity)


def test_dashboard_launch_agent_is_loopback_only_and_has_no_secrets(tmp_path: Path) -> None:
    executable = tmp_path / "opportunity-os"
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o700)
    home = tmp_path / "private-home"
    home.mkdir()
    agent = DashboardLaunchAgent(executable=executable, private_home=home, port=8765)

    payload = plistlib.loads(agent.render())

    assert payload["ProgramArguments"] == [
        str(executable),
        "dashboard",
        "serve",
        "--home",
        str(home),
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]
    assert payload["RunAtLoad"] is True
    assert "EnvironmentVariables" not in payload
    assert b"token" not in agent.render().lower()


def test_dashboard_launch_agent_defaults_to_dry_run_and_installs_atomically(tmp_path: Path) -> None:
    executable = tmp_path / "opportunity-os"
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o700)
    home = tmp_path / "state"
    home.mkdir()
    destination = tmp_path / "LaunchAgents" / "com.opportunity-os.dashboard.plist"
    agent = DashboardLaunchAgent(executable=executable, private_home=home)

    assert agent.install(destination).applied is False
    assert not destination.exists()
    result = agent.install(destination, apply=True)
    assert result.applied is True
    assert destination.read_bytes() == agent.render()
    assert destination.stat().st_mode & 0o777 == 0o600


def test_dashboard_launch_agent_rejects_nonstandard_destination(tmp_path: Path) -> None:
    executable = tmp_path / "opportunity-os"
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o700)
    home = tmp_path / "state"
    home.mkdir()
    agent = DashboardLaunchAgent(executable=executable, private_home=home)
    with pytest.raises(ValueError):
        agent.install(tmp_path / "wrong.plist", apply=True)


def test_ngrok_uses_official_service_commands_only() -> None:
    service = NgrokService(executable=Path("/opt/homebrew/bin/ngrok"), config=Path("/Users/example/.config/ngrok/ngrok.yml"))
    assert service.command("install") == [
        "/opt/homebrew/bin/ngrok",
        "service",
        "install",
        "--config",
        "/Users/example/.config/ngrok/ngrok.yml",
    ]
    assert service.command("start") == ["/opt/homebrew/bin/ngrok", "service", "start"]
    assert service.command("restart") == ["/opt/homebrew/bin/ngrok", "service", "restart"]
    assert service.command("status") == ["/opt/homebrew/bin/ngrok", "service", "status"]
    assert service.check_command() == [
        "/opt/homebrew/bin/ngrok",
        "config",
        "check",
        "--config",
        "/Users/example/.config/ngrok/ngrok.yml",
    ]
    with pytest.raises(ValueError):
        service.command("stop")


def test_ngrok_defaults_to_dry_run_and_sanitizes_environment(tmp_path: Path) -> None:
    calls = []

    def runner(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return type("Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    config = tmp_path / "ngrok.yml"
    config.write_text(
        "version: 3\nagent:\n  authtoken: test-runtime-value\nendpoints:\n  - name: opportunity-os-dashboard\n    url: https://\n    upstream:\n      url: http://127.0.0.1:8765\n    traffic_policy:\n      on_http_request:\n        - actions:\n            - type: oauth\n              config:\n                provider: github\n        - expressions:\n            - \"!(actions.ngrok.oauth.identity.email in ['owner@example.com'])\"\n          actions:\n            - type: deny\n",
        encoding="utf-8",
    )
    config.chmod(0o600)
    service = NgrokService(
        executable=Path("/usr/local/bin/ngrok"),
        config=config,
        runner=runner,
        environ={"HOME": "/Users/example", "PATH": "/usr/bin", "NGROK_AUTHTOKEN": "secret"},
    )
    assert service.run("install").applied is False
    assert calls == []
    assert service.run("install", apply=True).applied is True
    assert [call[0][1:3] for call in calls] == [["config", "check"], ["service", "install"]]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["env"] == {"HOME": "/Users/example", "PATH": "/usr/bin"}


def test_ngrok_apply_rejects_non_loopback_or_unauthenticated_config(tmp_path: Path) -> None:
    config = tmp_path / "ngrok.yml"
    config.write_text("version: '3'\nupstream:\n  url: http://0.0.0.0:8765\n", encoding="utf-8")
    config.chmod(0o600)
    service = NgrokService(executable=Path("/usr/local/bin/ngrok"), config=config, runner=lambda *a, **k: None)
    with pytest.raises(ValueError):
        service.run("install", apply=True)


def test_repository_has_no_custom_ngrok_launch_agent() -> None:
    deployment = Path(__file__).parents[2] / "deployment"
    text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in deployment.rglob("*") if path.is_file())
    assert "com.ngrok" not in text
    assert "ngrok.plist" not in text


def test_ngrok_v3_template_is_complete_random_https_and_loopback_only() -> None:
    text = NGROK_TEMPLATE.read_text(encoding="utf-8")
    assert "version: 3" in text
    assert "authtoken: __NGROK_AUTHTOKEN__" in text
    assert "name: opportunity-os-dashboard" in text
    assert "url: https://" in text
    assert "url: http://127.0.0.1:8765" in text
    assert "provider: github" in text
    assert "__OWNER_GITHUB_EMAIL__" in text
    assert "type: deny" in text
    assert "client_secret" not in text
