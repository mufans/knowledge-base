"""Declaratively reconcile jobs through OpenClaw's native Cron CLI only."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from opportunity_os.deployment.common import Runner, require_absolute_path, safe_environment


_NAME = re.compile(r"^opportunity-os-[a-z0-9][a-z0-9-]{0,62}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DURATION = re.compile(r"^[1-9][0-9]*(?:s|m|h|d)$")
_ALLOWED_JOB_KEYS = {
    "name", "description", "cron", "timezone", "message", "enabled", "session",
    "timeout_seconds", "delivery", "delivery_channel", "delivery_to", "failure_alert",
}
_ALLOWED_ALERT_KEYS = {"enabled", "after", "cooldown", "exclude_skipped", "channel", "to"}
_TARGET = re.compile(r"^[A-Za-z0-9_:@.-]{1,256}$")
_MANAGED_DESCRIPTION_PREFIX = "[managed-by:opportunity-os/v1] "


def _secure_json(path: Path) -> object:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 262_144:
            raise ValueError("manifest must be a small regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as handle:
            return json.load(handle)
    finally:
        os.close(descriptor)


def _text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or any(ord(char) < 32 and char not in "\t" for char in value):
        raise ValueError(f"invalid {label}")
    return value


@dataclass(frozen=True, slots=True)
class FailureAlert:
    enabled: bool
    after: int
    cooldown: str
    exclude_skipped: bool
    channel: str
    to: str

    @classmethod
    def parse(cls, value: object) -> "FailureAlert":
        if not isinstance(value, dict) or set(value) != _ALLOWED_ALERT_KEYS:
            raise ValueError("invalid failure_alert schema")
        after = value["after"]
        cooldown = value["cooldown"]
        if type(value["enabled"]) is not bool or type(value["exclude_skipped"]) is not bool:
            raise ValueError("invalid failure alert booleans")
        if type(after) is not int or not 1 <= after <= 20:
            raise ValueError("invalid failure alert threshold")
        if not isinstance(cooldown, str) or not _DURATION.fullmatch(cooldown):
            raise ValueError("invalid failure alert cooldown")
        channel = value["channel"]
        target = value["to"]
        if channel != "dingtalk" or not isinstance(target, str) or not _TARGET.fullmatch(target):
            raise ValueError("failure alert must target one safe DingTalk owner")
        return cls(value["enabled"], after, cooldown, value["exclude_skipped"], channel, target)


@dataclass(frozen=True, slots=True)
class CronJob:
    name: str
    description: str
    cron: str
    timezone: str
    message: str
    enabled: bool
    session: str
    timeout_seconds: int
    delivery: str
    delivery_channel: str
    delivery_to: str
    failure_alert: FailureAlert

    @classmethod
    def parse(cls, value: object) -> "CronJob":
        if not isinstance(value, dict) or set(value) != _ALLOWED_JOB_KEYS:
            raise ValueError("invalid job schema")
        name = _text(value["name"], "name", maximum=64)
        if not _NAME.fullmatch(name):
            raise ValueError("invalid managed job name")
        cron = _text(value["cron"], "cron", maximum=96)
        if len(cron.split()) not in (5, 6):
            raise ValueError("cron expression must have five or six fields")
        timezone = _text(value["timezone"], "timezone", maximum=64)
        if not re.fullmatch(r"[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)+", timezone):
            raise ValueError("invalid IANA timezone")
        if type(value["enabled"]) is not bool:
            raise ValueError("enabled must be boolean")
        session = value["session"]
        if session not in {"main", "isolated"}:
            raise ValueError("invalid session")
        timeout = value["timeout_seconds"]
        if type(timeout) is not int or not 30 <= timeout <= 7200:
            raise ValueError("invalid timeout_seconds")
        delivery = value["delivery"]
        if delivery not in {"announce", "none"}:
            raise ValueError("invalid delivery")
        delivery_channel = value["delivery_channel"]
        delivery_to = value["delivery_to"]
        if delivery_channel != "dingtalk" or not isinstance(delivery_to, str) or not _TARGET.fullmatch(delivery_to):
            raise ValueError("delivery must target one safe DingTalk owner")
        return cls(
            name=name,
            description=_managed_description(value["description"]),
            cron=cron,
            timezone=timezone,
            message=_text(value["message"], "message", maximum=4000),
            enabled=value["enabled"],
            session=session,
            timeout_seconds=timeout,
            delivery=delivery,
            delivery_channel=delivery_channel,
            delivery_to=delivery_to,
            failure_alert=FailureAlert.parse(value["failure_alert"]),
        )


def _managed_description(value: object) -> str:
    description = _text(value, "description", maximum=300)
    if not description.startswith(_MANAGED_DESCRIPTION_PREFIX):
        raise ValueError("managed job description is missing the ownership marker")
    return description


@dataclass(frozen=True, slots=True)
class CronManifest:
    jobs: tuple[CronJob, ...]

    @classmethod
    def load(cls, path: str | Path) -> "CronManifest":
        payload = _secure_json(Path(path))
        if not isinstance(payload, dict) or set(payload) != {"version", "jobs"} or payload["version"] != 1:
            raise ValueError("invalid cron manifest")
        values = payload["jobs"]
        if not isinstance(values, list) or not values:
            raise ValueError("manifest jobs must be a non-empty list")
        jobs = tuple(CronJob.parse(value) for value in values)
        names = [job.name for job in jobs]
        if len(names) != len(set(names)):
            raise ValueError("duplicate managed job name")
        return cls(jobs)


@dataclass(frozen=True, slots=True)
class CurrentJob:
    identifier: str
    name: str
    enabled: bool
    cron: str
    timezone: str
    message: str
    session: str
    description: str
    timeout_seconds: int | None
    delivery: str
    failure_after: int | None
    failure_cooldown_ms: int | None
    failure_exclude_skipped: bool | None
    agent: str
    wake_mode: str
    tools: tuple[str, ...]
    delivery_channel: str | None
    delivery_to: str | None
    failure_mode: str | None
    failure_channel: str | None
    failure_to: str | None

    @classmethod
    def parse(cls, value: object) -> "CurrentJob":
        if not isinstance(value, dict):
            raise ValueError("invalid OpenClaw job")
        schedule = value.get("schedule")
        payload = value.get("payload")
        if not isinstance(schedule, dict) or not isinstance(payload, dict):
            raise ValueError("invalid OpenClaw job DTO")
        identifier = value.get("id")
        name = value.get("name")
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier) or not isinstance(name, str):
            raise ValueError("invalid OpenClaw job identity")
        delivery = value.get("delivery")
        delivery_mode = delivery.get("mode", "none") if isinstance(delivery, dict) else "none"
        alert = value.get("failureAlert")
        if not isinstance(alert, dict):
            alert = {}
        after = alert.get("after", alert.get("threshold"))
        cooldown_ms = alert.get("cooldownMs")
        if cooldown_ms is None and isinstance(alert.get("cooldown"), str):
            cooldown_ms = _duration_ms(alert["cooldown"])
        include_skipped = alert.get("includeSkipped")
        exclude_skipped = alert.get("excludeSkipped")
        if type(exclude_skipped) is not bool and type(include_skipped) is bool:
            exclude_skipped = not include_skipped
        timeout = payload.get("timeoutSeconds", value.get("timeoutSeconds"))
        return cls(
            identifier=identifier,
            name=name,
            enabled=value.get("enabled") is True,
            cron=str(schedule.get("expr", "")),
            timezone=str(schedule.get("tz", "")),
            message=str(payload.get("message", "")),
            session=str(value.get("sessionTarget", value.get("session", "isolated"))),
            description=str(value.get("description", "")),
            timeout_seconds=timeout if type(timeout) is int else None,
            delivery=str(delivery_mode),
            failure_after=after if type(after) is int else None,
            failure_cooldown_ms=cooldown_ms if type(cooldown_ms) is int else None,
            failure_exclude_skipped=exclude_skipped if type(exclude_skipped) is bool else None,
            agent=str(value.get("agentId", "main")),
            wake_mode=str(value.get("wakeMode", "now")),
            tools=tuple(payload.get("toolsAllow", ())) if isinstance(payload.get("toolsAllow", ()), list) else (),
            delivery_channel=delivery.get("channel") if isinstance(delivery, dict) and isinstance(delivery.get("channel"), str) else None,
            delivery_to=delivery.get("to") if isinstance(delivery, dict) and isinstance(delivery.get("to"), str) else None,
            failure_mode=alert.get("mode") if isinstance(alert.get("mode"), str) else None,
            failure_channel=alert.get("channel") if isinstance(alert.get("channel"), str) else None,
            failure_to=alert.get("to") if isinstance(alert.get("to"), str) else None,
        )


@dataclass(frozen=True, slots=True)
class ReconcileAction:
    kind: str
    name: str
    identifier: str | None = None


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    actions: tuple[ReconcileAction, ...]
    applied: bool


class OpenClawCronClient:
    """Fixed-argv adapter; OpenClaw owns scheduling, retries, alerts and delivery."""

    def __init__(
        self,
        *,
        executable: str | Path,
        runner: Runner = subprocess.run,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.executable = require_absolute_path(executable, basename="openclaw")
        self.runner = runner
        self.environ = environ

    def _call(self, arguments: list[str], *, expect_json: bool = False) -> object:
        result = self.runner(
            [str(self.executable), "cron", *arguments],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=safe_environment(self.environ),
        )
        if result.returncode != 0:
            raise RuntimeError(f"OpenClaw cron command failed with exit code {result.returncode}")
        if not expect_json:
            return {}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenClaw returned invalid JSON") from error

    def list(self) -> tuple[CurrentJob, ...]:
        payload = self._call(["list", "--all", "--json"], expect_json=True)
        values = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise RuntimeError("OpenClaw job list has invalid shape")
        return tuple(CurrentJob.parse(value) for value in values)

    def add(self, job: CronJob) -> str:
        payload = self._call(["add", *self._job_flags(job), "--json"], expect_json=True)
        identifier = payload.get("id") if isinstance(payload, dict) else None
        if identifier is None and isinstance(payload, dict) and isinstance(payload.get("job"), dict):
            identifier = payload["job"].get("id")
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise RuntimeError("OpenClaw did not return a safe job id")
        return identifier

    def edit(self, identifier: str, job: CronJob) -> None:
        self._id(identifier)
        self._call(["edit", identifier, *self._job_flags(job, for_edit=True), *self._alert_flags(job.failure_alert)])

    def configure_alert(self, identifier: str, alert: FailureAlert) -> None:
        self._id(identifier)
        self._call(["edit", identifier, *self._alert_flags(alert)])

    def enable(self, identifier: str) -> None:
        self._id(identifier)
        self._call(["enable", identifier])

    def disable(self, identifier: str) -> None:
        self._id(identifier)
        self._call(["disable", identifier])

    def status(self) -> object:
        return self._call(["status", "--json"], expect_json=True)

    def run(self, identifier: str) -> object:
        self._id(identifier)
        return self._call(["run", identifier], expect_json=True)

    def runs(self, identifier: str) -> object:
        self._id(identifier)
        return self._call(["runs", "--id", identifier], expect_json=True)

    @staticmethod
    def _id(identifier: str) -> None:
        if not _ID.fullmatch(identifier):
            raise ValueError("invalid OpenClaw job id")

    @staticmethod
    def _delivery_flags(job: CronJob) -> list[str]:
        return ["--announce", "--channel", job.delivery_channel, "--to", job.delivery_to] if job.delivery == "announce" else ["--no-deliver"]

    @classmethod
    def _job_flags(cls, job: CronJob, *, for_edit: bool = False) -> list[str]:
        flags = [
            "--name", job.name,
            "--description", job.description,
            "--cron", job.cron,
            "--tz", job.timezone,
            "--session", job.session,
            "--agent", "main",
            "--wake", "now",
            "--message", job.message,
            "--tools", "exec",
            "--timeout-seconds", str(job.timeout_seconds),
            *cls._delivery_flags(job),
        ]
        if for_edit:
            flags.append("--enable" if job.enabled else "--disable")
        elif not job.enabled:
            flags.append("--disabled")
        return flags

    @staticmethod
    def _alert_flags(alert: FailureAlert) -> list[str]:
        if not alert.enabled:
            return ["--no-failure-alert"]
        flags = [
            "--failure-alert",
            "--failure-alert-after", str(alert.after),
            "--failure-alert-cooldown", alert.cooldown,
            "--failure-alert-mode", "announce",
            "--failure-alert-channel", alert.channel,
            "--failure-alert-to", alert.to,
        ]
        flags.append("--failure-alert-exclude-skipped" if alert.exclude_skipped else "--failure-alert-include-skipped")
        return flags


def _materially_equal(current: CurrentJob, desired: CronJob) -> bool:
    return (
        current.cron == desired.cron
        and current.timezone == desired.timezone
        and current.message == desired.message
        and current.session == desired.session
        and current.description == desired.description
        and current.timeout_seconds == desired.timeout_seconds
        and current.delivery == desired.delivery
        and current.failure_after == desired.failure_alert.after
        and current.failure_cooldown_ms == _duration_ms(desired.failure_alert.cooldown)
        and current.failure_exclude_skipped == desired.failure_alert.exclude_skipped
        and current.agent == "main"
        and current.wake_mode == "now"
        and current.tools == ("exec",)
        and (
            desired.delivery == "none"
            or (
                current.delivery_channel == desired.delivery_channel
                and current.delivery_to == desired.delivery_to
            )
        )
        and current.failure_mode == "announce"
        and current.failure_channel == desired.failure_alert.channel
        and current.failure_to == desired.failure_alert.to
    )


def _duration_ms(value: str) -> int | None:
    match = _DURATION.fullmatch(value)
    if match is None:
        return None
    unit = value[-1]
    multipliers = {"s": 1_000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}
    return int(value[:-1]) * multipliers[unit]


def reconcile(manifest: CronManifest, client: OpenClawCronClient, *, apply: bool = False) -> ReconcileResult:
    if apply:
        for job in manifest.jobs:
            targets = (job.delivery_to, job.failure_alert.to)
            if any(target.startswith("__") and target.endswith("__") for target in targets):
                raise ValueError("owner placeholder must be replaced before apply")
    current = client.list()
    grouped: dict[str, list[CurrentJob]] = {}
    for current_job in current:
        grouped.setdefault(current_job.name, []).append(current_job)
    desired_names = {job.name for job in manifest.jobs}
    for name, matches in grouped.items():
        is_managed = any(job.description.startswith(_MANAGED_DESCRIPTION_PREFIX) for job in matches)
        if len(matches) > 1 and (name in desired_names or is_managed):
            raise RuntimeError(f"duplicate OpenClaw job name: {name}")
    for desired_job in manifest.jobs:
        matches = grouped.get(desired_job.name, [])
        if matches and not matches[0].description.startswith(_MANAGED_DESCRIPTION_PREFIX):
            raise RuntimeError(f"unmanaged name collision: {desired_job.name}")
    by_name = {name: jobs[0] for name, jobs in grouped.items() if len(jobs) == 1}
    actions: list[ReconcileAction] = []
    for job in manifest.jobs:
        existing = by_name.get(job.name)
        if existing is None:
            actions.append(ReconcileAction("add", job.name))
        elif not _materially_equal(existing, job):
            actions.append(ReconcileAction("edit", job.name, existing.identifier))
        elif existing.enabled != job.enabled:
            actions.append(ReconcileAction("enable" if job.enabled else "disable", job.name, existing.identifier))
    for job in current:
        if (
            job.name.startswith("opportunity-os-")
            and job.description.startswith(_MANAGED_DESCRIPTION_PREFIX)
            and job.name not in desired_names
            and job.enabled
        ):
            actions.append(ReconcileAction("disable", job.name, job.identifier))

    if apply:
        desired = {job.name: job for job in manifest.jobs}
        for action in actions:
            if action.kind == "add":
                identifier = client.add(desired[action.name])
                client.configure_alert(identifier, desired[action.name].failure_alert)
            elif action.kind == "edit":
                assert action.identifier is not None
                client.edit(action.identifier, desired[action.name])
            elif action.kind == "enable":
                assert action.identifier is not None
                client.enable(action.identifier)
            elif action.kind == "disable":
                assert action.identifier is not None
                client.disable(action.identifier)
    return ReconcileResult(tuple(actions), apply)
