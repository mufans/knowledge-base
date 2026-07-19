"""Safe dashboard launchd asset and official ngrok service adapter."""

from __future__ import annotations

import ipaddress
import json
import os
import plistlib
import re
import stat
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import yaml

from opportunity_os.deployment.common import ExecutionResult, Runner, execute, require_absolute_path


_GITHUB_PROVIDER_USER_ID = re.compile(r"^[1-9][0-9]{0,19}$")
_OWNER_EXPRESSION = re.compile(
    r"^actions\.ngrok\.oauth\.identity\.provider_user_id != '([1-9][0-9]{0,19})'$"
)
_SERVICE_ACTIONS = frozenset({"install", "start", "restart"})
_ORIGIN_CREDENTIAL = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
_REMOTE_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
_MAX_CONFIG_BYTES = 262_144
_MAX_SECRET_BYTES = 4096


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ValueError("invalid unhashable YAML key") from error
        if duplicate:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _validate_github_provider_user_id(identity: str) -> None:
    if not isinstance(identity, str) or _GITHUB_PROVIDER_USER_ID.fullmatch(identity) is None:
        raise ValueError("GitHub OAuth identity must be one numeric provider user id")


def _validate_origin_credential(value: str) -> None:
    if not isinstance(value, str) or _ORIGIN_CREDENTIAL.fullmatch(value) is None:
        raise ValueError("origin credential must be 43-128 URL-safe random characters")


def _validate_remote_host(value: str) -> None:
    if not isinstance(value, str) or value != value.casefold() or _REMOTE_HOST.fullmatch(value) is None:
        raise ValueError("remote host must be one lowercase DNS hostname")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return
    raise ValueError("remote host must not be an IP address")


def _traffic_policy(identity: str, origin_credential: str) -> dict[str, object]:
    _validate_github_provider_user_id(identity)
    _validate_origin_credential(origin_credential)
    return {
        "on_http_request": [
            {
                "actions": [{
                    "type": "oauth",
                    "config": {
                        "provider": "github",
                        "auth_id": "opportunity-os-owner-v3",
                        "idle_session_timeout": "15m",
                        "max_session_duration": "8h",
                    },
                }]
            },
            {
                "expressions": [f"actions.ngrok.oauth.identity.provider_user_id != '{identity}'"],
                "actions": [{"type": "deny", "config": {"status_code": 403}}],
            },
            {
                "actions": [{
                    "type": "add-headers",
                    "config": {"headers": {"x-opportunity-origin": origin_credential}},
                }]
            },
        ]
    }


def render_github_policy(identity: str, origin_credential: str) -> str:
    return yaml.safe_dump(_traffic_policy(identity, origin_credential), sort_keys=False)


def write_github_policy(
    destination: str | Path,
    identity: str,
    origin_credential: str,
    *,
    apply: bool = False,
) -> InstallResult:
    target = require_absolute_path(destination)
    if target.suffix not in {".yml", ".yaml"}:
        raise ValueError("traffic policy destination must be YAML")
    rendered = render_github_policy(identity, origin_credential).encode("utf-8")
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


@dataclass(frozen=True, slots=True)
class NgrokStatus:
    running: bool
    tunnel_count: int


class NgrokLocalStatus:
    """Read only the loopback ngrok agent API; this is not a service mutation."""

    URL = "http://127.0.0.1:4040/api/tunnels"

    def __init__(self, *, opener: Callable[..., object] = urllib.request.urlopen) -> None:
        self.opener = opener

    def read(self) -> NgrokStatus:
        request = urllib.request.Request(self.URL, headers={"Accept": "application/json"}, method="GET")
        try:
            with self.opener(request, timeout=3) as response:  # type: ignore[attr-defined]
                raw = response.read(_MAX_CONFIG_BYTES + 1)
        except Exception as error:
            raise RuntimeError("ngrok loopback status API is unavailable") from error
        if not isinstance(raw, bytes) or len(raw) > _MAX_CONFIG_BYTES:
            raise RuntimeError("ngrok loopback status response is invalid")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("ngrok loopback status response is invalid") from error
        tunnels = payload.get("tunnels") if isinstance(payload, dict) else None
        if not isinstance(tunnels, list) or not all(isinstance(item, dict) for item in tunnels):
            raise RuntimeError("ngrok loopback status response is invalid")
        return NgrokStatus(running=True, tunnel_count=len(tunnels))


class DashboardLaunchAgent:
    LABEL = "com.opportunity-os.dashboard"

    def __init__(
        self,
        *,
        executable: str | Path,
        private_home: str | Path,
        remote_host: str,
        origin_credential: str,
        port: int = 8765,
    ) -> None:
        self.executable = require_absolute_path(executable, basename="opportunity-os")
        self.private_home = require_absolute_path(private_home)
        _validate_remote_host(remote_host)
        _validate_origin_credential(origin_credential)
        self.remote_host = remote_host
        self.origin_credential = origin_credential
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
            "EnvironmentVariables": {
                "DASHBOARD_HOME": str(self.private_home),
                "DASHBOARD_REMOTE_HOST": self.remote_host,
                "DASHBOARD_ORIGIN_CREDENTIAL": self.origin_credential,
            },
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


def _read_private_value(source: str | Path, *, label: str) -> str:
    path = require_absolute_path(source)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= _MAX_SECRET_BYTES:
            raise ValueError(f"{label} file must be one small regular file")
        if info.st_mode & 0o077:
            raise ValueError(f"{label} file permissions must be 0600 or stricter")
        raw = os.read(descriptor, _MAX_SECRET_BYTES + 1)
    finally:
        os.close(descriptor)
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} file must be UTF-8") from error
    value = value.removesuffix("\n")
    if not value or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{label} file must contain exactly one value")
    return value


def read_origin_credential(source: str | Path) -> str:
    value = _read_private_value(source, label="origin credential")
    _validate_origin_credential(value)
    return value


def read_github_provider_user_id(source: str | Path) -> str:
    value = _read_private_value(source, label="owner GitHub provider user id")
    _validate_github_provider_user_id(value)
    return value


def render_ngrok_config(
    *,
    authtoken: str,
    owner_github_id: str,
    origin_credential: str,
    remote_host: str,
    port: int = 8765,
) -> str:
    if (
        not isinstance(authtoken, str)
        or not authtoken
        or len(authtoken) > _MAX_SECRET_BYTES
        or not authtoken.isprintable()
        or any(character in authtoken for character in "\r\n\x00")
    ):
        raise ValueError("ngrok authtoken is invalid")
    _validate_github_provider_user_id(owner_github_id)
    _validate_origin_credential(origin_credential)
    _validate_remote_host(remote_host)
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("dashboard port must be between 1024 and 65535")
    document = {
        "version": 3,
        "agent": {
            "authtoken": authtoken,
            "update_channel": "stable",
            "update_check": True,
            "web_addr": "127.0.0.1:4040",
        },
        "endpoints": [{
            "name": "opportunity-os-dashboard",
            "description": "Owner-only Opportunity OS dashboard",
            "url": f"https://{remote_host}",
            "upstream": {"url": f"http://127.0.0.1:{port}", "protocol": "http1"},
            "traffic_policy": _traffic_policy(owner_github_id, origin_credential),
        }],
    }
    rendered = yaml.safe_dump(document, sort_keys=False)
    NgrokService._validate_config_document(rendered)
    return rendered


def write_ngrok_config(
    destination: str | Path,
    *,
    authtoken_file: str | Path,
    owner_github_id_file: str | Path,
    origin_credential_file: str | Path,
    remote_host: str,
    port: int = 8765,
    apply: bool = False,
) -> InstallResult:
    target = require_absolute_path(destination)
    if target.suffix not in {".yml", ".yaml"}:
        raise ValueError("ngrok config destination must be YAML")
    rendered = render_ngrok_config(
        authtoken=_read_private_value(authtoken_file, label="ngrok authtoken"),
        owner_github_id=read_github_provider_user_id(owner_github_id_file),
        origin_credential=read_origin_credential(origin_credential_file),
        remote_host=remote_host,
        port=port,
    ).encode("utf-8")
    if not apply:
        return InstallResult(target, False)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise ValueError("ngrok config parent must be a non-symlink directory")
    if target.exists() and not stat.S_ISREG(target.lstat().st_mode):
        raise ValueError("ngrok config destination must be a regular file")
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
        if apply and action in {"install", "start", "restart"}:
            execute(self.check_command(), apply=True, runner=self.runner, environ=self.environ)
        return execute(self.command(action), apply=apply, runner=self.runner, environ=self.environ)

    def _validate_config(self) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.config, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_CONFIG_BYTES:
                raise ValueError("ngrok config must be a small regular file")
            if info.st_mode & 0o077:
                raise ValueError("ngrok config permissions must be 0600 or stricter")
            with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as handle:
                rendered = handle.read()
        finally:
            os.close(descriptor)
        self._validate_config_document(rendered)

    @staticmethod
    def _validate_config_document(rendered: str) -> None:
        try:
            document = yaml.load(rendered, Loader=_UniqueKeySafeLoader)
        except ValueError:
            raise
        except yaml.YAMLError as error:
            raise ValueError("invalid ngrok YAML") from error
        if not isinstance(document, dict) or set(document) != {"version", "agent", "endpoints"}:
            raise ValueError("ngrok config must contain only version, agent and endpoints")
        if document["version"] != 3:
            raise ValueError("ngrok config version must be 3")
        agent = document["agent"]
        expected_agent_keys = {"authtoken", "update_channel", "update_check", "web_addr"}
        if not isinstance(agent, dict) or set(agent) != expected_agent_keys:
            raise ValueError("invalid ngrok agent config")
        token = agent.get("authtoken")
        if not isinstance(token, str) or not token or token == "__NGROK_AUTHTOKEN__":
            raise ValueError("ngrok authtoken placeholder must be replaced")
        if agent.get("update_channel") != "stable" or agent.get("update_check") is not True:
            raise ValueError("ngrok agent must use stable update settings")
        if agent.get("web_addr") != "127.0.0.1:4040":
            raise ValueError("ngrok local API must bind to loopback")
        endpoints = document["endpoints"]
        if not isinstance(endpoints, list) or len(endpoints) != 1:
            raise ValueError("ngrok config must define exactly one endpoint")
        endpoint = endpoints[0]
        expected_endpoint_keys = {"name", "description", "url", "upstream", "traffic_policy"}
        if not isinstance(endpoint, dict) or set(endpoint) != expected_endpoint_keys:
            raise ValueError("invalid ngrok dashboard endpoint")
        endpoint_url = endpoint.get("url")
        if (
            endpoint.get("name") != "opportunity-os-dashboard"
            or endpoint.get("description") != "Owner-only Opportunity OS dashboard"
            or not isinstance(endpoint_url, str)
            or not endpoint_url.startswith("https://")
        ):
            raise ValueError("invalid ngrok dashboard endpoint identity")
        _validate_remote_host(endpoint_url.removeprefix("https://"))
        upstream = endpoint.get("upstream")
        if not isinstance(upstream, dict) or set(upstream) != {"url", "protocol"}:
            raise ValueError("invalid ngrok dashboard upstream")
        upstream_url = upstream.get("url")
        if not isinstance(upstream_url, str) or re.fullmatch(r"http://127\.0\.0\.1:[0-9]{4,5}", upstream_url) is None:
            raise ValueError("ngrok upstream must target the loopback dashboard")
        port = int(upstream_url.rsplit(":", 1)[1])
        if not 1024 <= port <= 65535 or upstream.get("protocol") != "http1":
            raise ValueError("invalid ngrok dashboard upstream")
        policy = endpoint.get("traffic_policy")
        if not isinstance(policy, dict) or set(policy) != {"on_http_request"}:
            raise ValueError("ngrok config must enforce GitHub OAuth")
        rules = policy["on_http_request"]
        if not isinstance(rules, list) or len(rules) != 3:
            raise ValueError("ngrok config must enforce OAuth, owner authorization and origin header")
        oauth_rule, deny_rule, header_rule = rules
        if not isinstance(oauth_rule, dict) or set(oauth_rule) != {"actions"}:
            raise ValueError("ngrok config must enforce GitHub OAuth first")
        oauth_actions = oauth_rule["actions"]
        if not isinstance(oauth_actions, list) or len(oauth_actions) != 1:
            raise ValueError("ngrok config must enforce GitHub OAuth first")
        oauth = oauth_actions[0]
        if not isinstance(oauth, dict) or set(oauth) != {"type", "config"} or oauth.get("type") != "oauth":
            raise ValueError("ngrok config must enforce GitHub OAuth first")
        oauth_config = oauth.get("config")
        expected_oauth_keys = {"provider", "auth_id", "idle_session_timeout", "max_session_duration"}
        if (
            not isinstance(oauth_config, dict)
            or set(oauth_config) != expected_oauth_keys
            or oauth_config != {
                "provider": "github",
                "auth_id": "opportunity-os-owner-v3",
                "idle_session_timeout": "15m",
                "max_session_duration": "8h",
            }
        ):
            raise ValueError("ngrok config must enforce GitHub OAuth first")
        if not isinstance(deny_rule, dict) or set(deny_rule) != {"expressions", "actions"}:
            raise ValueError("ngrok config must deny every non-owner identity")
        expressions = deny_rule["expressions"]
        deny_actions = deny_rule["actions"]
        if not isinstance(expressions, list) or len(expressions) != 1 or not isinstance(expressions[0], str):
            raise ValueError("ngrok config must deny every non-owner identity")
        match = _OWNER_EXPRESSION.fullmatch(expressions[0])
        if match is None or _GITHUB_PROVIDER_USER_ID.fullmatch(match.group(1)) is None or match.group(1) == "__OWNER_GITHUB_PROVIDER_USER_ID__":
            raise ValueError("ngrok config must deny every non-owner identity")
        if not isinstance(deny_actions, list) or len(deny_actions) != 1:
            raise ValueError("ngrok config must deny every non-owner identity")
        deny = deny_actions[0]
        if (
            not isinstance(deny, dict)
            or set(deny) != {"type", "config"}
            or deny.get("type") != "deny"
            or deny.get("config") != {"status_code": 403}
        ):
            raise ValueError("ngrok config must deny every non-owner identity")
        if not isinstance(header_rule, dict) or set(header_rule) != {"actions"}:
            raise ValueError("ngrok config must add only the dashboard origin header third")
        header_actions = header_rule["actions"]
        if not isinstance(header_actions, list) or len(header_actions) != 1:
            raise ValueError("ngrok config must add only the dashboard origin header third")
        header_action = header_actions[0]
        if (
            not isinstance(header_action, dict)
            or set(header_action) != {"type", "config"}
            or header_action.get("type") != "add-headers"
        ):
            raise ValueError("ngrok config must add only the dashboard origin header third")
        header_config = header_action.get("config")
        if not isinstance(header_config, dict) or set(header_config) != {"headers"}:
            raise ValueError("ngrok config must add only the dashboard origin header third")
        headers = header_config["headers"]
        if not isinstance(headers, dict) or set(headers) != {"x-opportunity-origin"}:
            raise ValueError("ngrok config must add only the dashboard origin header third")
        credential = headers["x-opportunity-origin"]
        if not isinstance(credential, str) or credential == "__DASHBOARD_ORIGIN_CREDENTIAL__":
            raise ValueError("dashboard origin credential placeholder must be replaced")
        _validate_origin_credential(credential)
