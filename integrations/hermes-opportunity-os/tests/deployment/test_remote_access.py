import plistlib
from pathlib import Path

import pytest

from opportunity_os.deployment.__main__ import main as deployment_main
from opportunity_os.deployment.remote_access import (
    DashboardLaunchAgent,
    NgrokLocalStatus,
    NgrokService,
    render_ngrok_config,
    render_github_policy,
    write_ngrok_config,
)


NGROK_TEMPLATE = Path(__file__).parents[2] / "deployment/ngrok/ngrok.yml.template"
ORIGIN_CREDENTIAL = "A" * 43


def _render_valid_template() -> str:
    return (
        NGROK_TEMPLATE.read_text(encoding="utf-8")
        .replace("__NGROK_AUTHTOKEN__", "test-runtime-value")
        .replace("__OWNER_GITHUB_PROVIDER_USER_ID__", "7991387")
        .replace("__DASHBOARD_ORIGIN_CREDENTIAL__", ORIGIN_CREDENTIAL)
        .replace("__NGROK_REMOTE_HOST__", "owner.ngrok-free.app")
    )


def test_github_policy_authenticates_then_denies_every_other_identity() -> None:
    rendered = render_github_policy("7991387", ORIGIN_CREDENTIAL)
    assert "provider: github" in rendered
    assert "auth_id: opportunity-os-owner-v3" in rendered
    assert "actions.ngrok.oauth.identity.provider_user_id" in rendered
    assert "7991387" in rendered
    assert "type: deny" in rendered
    assert "x-opportunity-origin" in rendered
    assert rendered.index("type: oauth") < rendered.index("type: deny") < rendered.index("type: add-headers")
    assert "client_secret" not in rendered


@pytest.mark.parametrize("identity", ["", "0", "-1", "mufans", "1' || true", "line\nbreak"])
def test_github_policy_rejects_unsafe_identity(identity: str) -> None:
    with pytest.raises(ValueError):
        render_github_policy(identity, ORIGIN_CREDENTIAL)


def test_dashboard_launch_agent_is_loopback_only_and_closes_remote_origin_gate(tmp_path: Path) -> None:
    executable = tmp_path / "opportunity-os"
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o700)
    home = tmp_path / "private-home"
    home.mkdir()
    agent = DashboardLaunchAgent(
        executable=executable,
        private_home=home,
        port=8765,
        remote_host="owner.ngrok-free.app",
        origin_credential=ORIGIN_CREDENTIAL,
    )

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
    assert payload["EnvironmentVariables"] == {
        "DASHBOARD_HOME": str(home),
        "DASHBOARD_REMOTE_HOST": "owner.ngrok-free.app",
        "DASHBOARD_ORIGIN_CREDENTIAL": ORIGIN_CREDENTIAL,
    }


@pytest.mark.parametrize(
    ("remote_host", "credential"),
    [
        ("https://owner.ngrok-free.app", ORIGIN_CREDENTIAL),
        ("owner.ngrok-free.app:443", ORIGIN_CREDENTIAL),
        ("127.0.0.1", ORIGIN_CREDENTIAL),
        ("owner.ngrok-free.app", "short"),
        ("owner.ngrok-free.app", "x" * 42 + "!"),
    ],
)
def test_dashboard_launch_agent_rejects_unsafe_remote_inputs(
    tmp_path: Path, remote_host: str, credential: str
) -> None:
    executable = tmp_path / "opportunity-os"
    home = tmp_path / "private-home"
    with pytest.raises(ValueError):
        DashboardLaunchAgent(
            executable=executable,
            private_home=home,
            remote_host=remote_host,
            origin_credential=credential,
        )


def test_dashboard_launch_agent_defaults_to_dry_run_and_installs_atomically(tmp_path: Path) -> None:
    executable = tmp_path / "opportunity-os"
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o700)
    home = tmp_path / "state"
    home.mkdir()
    destination = tmp_path / "LaunchAgents" / "com.opportunity-os.dashboard.plist"
    agent = DashboardLaunchAgent(
        executable=executable,
        private_home=home,
        remote_host="owner.ngrok-free.app",
        origin_credential=ORIGIN_CREDENTIAL,
    )

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
    agent = DashboardLaunchAgent(
        executable=executable,
        private_home=home,
        remote_host="owner.ngrok-free.app",
        origin_credential=ORIGIN_CREDENTIAL,
    )
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
    assert service.check_command() == [
        "/opt/homebrew/bin/ngrok",
        "config",
        "check",
        "--config",
        "/Users/example/.config/ngrok/ngrok.yml",
    ]
    with pytest.raises(ValueError):
        service.command("status")


def test_ngrok_defaults_to_dry_run_and_sanitizes_environment(tmp_path: Path) -> None:
    calls = []

    def runner(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return type("Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    config = tmp_path / "ngrok.yml"
    config.write_text(_render_valid_template(), encoding="utf-8")
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


@pytest.mark.parametrize("action", ["install", "start", "restart"])
def test_ngrok_checks_config_before_every_mutating_service_action(tmp_path: Path, action: str) -> None:
    calls = []

    def runner(argv, **kwargs):
        calls.append(list(argv))
        return type("Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    config = tmp_path / "ngrok.yml"
    config.write_text(_render_valid_template(), encoding="utf-8")
    config.chmod(0o600)
    service = NgrokService(executable="/usr/local/bin/ngrok", config=config, runner=runner, environ={})

    service.run(action, apply=True)

    assert calls[0] == ["/usr/local/bin/ngrok", "config", "check", "--config", str(config)]
    assert calls[1] == service.command(action)


def test_ngrok_rejects_commented_out_oauth_and_deny(tmp_path: Path) -> None:
    config = tmp_path / "ngrok.yml"
    config.write_text(
        "version: 3\n"
        "agent:\n"
        "  authtoken: runtime-token\n"
        "  update_channel: stable\n"
        "  update_check: true\n"
        "  web_addr: 127.0.0.1:4040\n"
        "endpoints:\n"
        "  - name: opportunity-os-dashboard\n"
        "    description: Owner-only Opportunity OS dashboard\n"
        "    url: https://owner.ngrok-free.app\n"
        "    upstream:\n"
        "      url: http://127.0.0.1:8765\n"
        "      protocol: http1\n"
        "# provider: github\n"
        "# type: oauth\n"
        "# actions.ngrok.oauth.identity.provider_user_id\n"
        "# type: deny\n",
        encoding="utf-8",
    )
    config.chmod(0o600)
    service = NgrokService(executable="/usr/local/bin/ngrok", config=config, runner=lambda *a, **k: None)

    with pytest.raises(ValueError):
        service.run("install", apply=True)


def test_ngrok_rejects_multiple_endpoints_or_duplicate_yaml_keys(tmp_path: Path) -> None:
    valid = _render_valid_template()
    multiple = tmp_path / "multiple.yml"
    multiple.write_text(valid + "\n  - name: shadow\n    upstream:\n      url: http://127.0.0.1:9999\n", encoding="utf-8")
    multiple.chmod(0o600)
    with pytest.raises(ValueError, match="exactly one endpoint"):
        NgrokService(executable="/usr/local/bin/ngrok", config=multiple)._validate_config()

    duplicate = tmp_path / "duplicate.yml"
    duplicate.write_text(valid.replace("version: 3", "version: 3\nversion: 3", 1), encoding="utf-8")
    duplicate.chmod(0o600)
    with pytest.raises(ValueError, match="duplicate YAML key"):
        NgrokService(executable="/usr/local/bin/ngrok", config=duplicate)._validate_config()


def test_ngrok_local_status_uses_only_loopback_api() -> None:
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, maximum):
            assert maximum == 262_145
            return b'{"tunnels":[{"public_url":"https://example.ngrok.app"}]}'

    def opener(request, *, timeout):
        calls.append((request.full_url, timeout))
        return Response()

    result = NgrokLocalStatus(opener=opener).read()

    assert calls == [("http://127.0.0.1:4040/api/tunnels", 3)]
    assert result.running is True
    assert result.tunnel_count == 1


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


def test_ngrok_v3_template_requires_stable_https_host_and_loopback_only() -> None:
    text = NGROK_TEMPLATE.read_text(encoding="utf-8")
    assert "version: 3" in text
    assert "authtoken: __NGROK_AUTHTOKEN__" in text
    assert "name: opportunity-os-dashboard" in text
    assert "url: https://__NGROK_REMOTE_HOST__" in text
    assert "url: http://127.0.0.1:8765" in text
    assert "provider: github" in text
    assert "__OWNER_GITHUB_PROVIDER_USER_ID__" in text
    assert "type: deny" in text
    assert "type: add-headers" in text
    assert "x-opportunity-origin: __DASHBOARD_ORIGIN_CREDENTIAL__" in text
    assert text.index("type: oauth") < text.index("type: deny") < text.index("type: add-headers")
    assert "client_secret" not in text


def test_ngrok_document_allows_only_oauth_owner_deny_then_one_origin_header() -> None:
    NgrokService._validate_config_document(_render_valid_template())
    for mutation in (
        _render_valid_template().replace("type: add-headers", "type: oauth", 1),
        _render_valid_template().replace("x-opportunity-origin:", "x-shadow-header:", 1),
        _render_valid_template().replace(
            f"x-opportunity-origin: {ORIGIN_CREDENTIAL}",
            f"x-opportunity-origin: {ORIGIN_CREDENTIAL}\n                x-extra: forbidden",
            1,
        ),
        _render_valid_template().replace(ORIGIN_CREDENTIAL, "__DASHBOARD_ORIGIN_CREDENTIAL__", 1),
    ):
        with pytest.raises(ValueError):
            NgrokService._validate_config_document(mutation)


def test_structured_ngrok_renderer_quotes_values_and_never_leaves_placeholders() -> None:
    rendered = render_ngrok_config(
        authtoken="token:with#yaml-characters",
        owner_github_id="7991387",
        origin_credential=ORIGIN_CREDENTIAL,
        remote_host="owner.ngrok-free.app",
        port=8765,
    )
    assert "__NGROK_" not in rendered
    assert "__OWNER_" not in rendered
    assert "__DASHBOARD_" not in rendered
    NgrokService._validate_config_document(rendered)


def test_ngrok_config_writer_reads_private_regular_files_and_writes_0600(tmp_path: Path) -> None:
    token = tmp_path / "token"
    owner = tmp_path / "owner-github-id"
    credential = tmp_path / "origin"
    destination = tmp_path / "runtime" / "ngrok.yml"
    for path, value in (
        (token, "runtime-token"),
        (owner, "7991387"),
        (credential, ORIGIN_CREDENTIAL),
    ):
        path.write_text(value + "\n", encoding="utf-8")
        path.chmod(0o600)

    result = write_ngrok_config(
        destination,
        authtoken_file=token,
        owner_github_id_file=owner,
        origin_credential_file=credential,
        remote_host="owner.ngrok-free.app",
        apply=True,
    )

    assert result.applied is True
    assert destination.stat().st_mode & 0o777 == 0o600
    NgrokService(executable="/usr/local/bin/ngrok", config=destination)._validate_config()


def test_ngrok_config_writer_rejects_symlink_or_group_readable_secret(tmp_path: Path) -> None:
    token = tmp_path / "token"
    owner = tmp_path / "owner-github-id"
    credential = tmp_path / "origin"
    for path, value in ((token, "token"), (owner, "7991387"), (credential, ORIGIN_CREDENTIAL)):
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
    symlink = tmp_path / "token-link"
    symlink.symlink_to(token)
    with pytest.raises((OSError, ValueError)):
        write_ngrok_config(
            tmp_path / "ngrok.yml",
            authtoken_file=symlink,
            owner_github_id_file=owner,
            origin_credential_file=credential,
            remote_host="owner.ngrok-free.app",
            apply=True,
        )
    owner.chmod(0o640)
    with pytest.raises(ValueError, match="permissions"):
        write_ngrok_config(
            tmp_path / "ngrok.yml",
            authtoken_file=token,
            owner_github_id_file=owner,
            origin_credential_file=credential,
            remote_host="owner.ngrok-free.app",
            apply=True,
        )


def test_deployment_cli_reads_origin_credential_from_file_without_argv_or_output(
    tmp_path: Path, capsys
) -> None:
    credential_file = tmp_path / "origin"
    credential_file.write_text(ORIGIN_CREDENTIAL, encoding="utf-8")
    credential_file.chmod(0o600)
    destination = tmp_path / "LaunchAgents" / "com.opportunity-os.dashboard.plist"

    result = deployment_main([
        "dashboard-agent",
        "--executable", str(tmp_path / "opportunity-os"),
        "--private-home", str(tmp_path / "private"),
        "--destination", str(destination),
        "--remote-host", "owner.ngrok-free.app",
        "--origin-credential-file", str(credential_file),
    ])

    output = capsys.readouterr().out
    assert result == 0
    assert ORIGIN_CREDENTIAL not in output
    assert "origin-credential" not in output
