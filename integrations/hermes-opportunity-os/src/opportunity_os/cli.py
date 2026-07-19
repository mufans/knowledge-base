import argparse
import json
import sys
import tarfile
import webbrowser
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit

import uvicorn

from opportunity_os.automation.hermes_runner import CADENCES, CadenceRunner
from opportunity_os.automation.healthcheck import (
    HealthCheck,
    HealthMarkerError,
    LastHealthProbe,
)
from opportunity_os.dashboard.app import DashboardDependencies, create_app
from opportunity_os.dashboard.auth import CsrfGuard, SessionStore
from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.events import EventHub
from opportunity_os.dashboard.probes import CommandRunner, HermesProbe, OpenClawProbe
from opportunity_os.dashboard.read_model import DashboardReadModel
from opportunity_os.dashboard.repositories import PrivateStateReadRepository
from opportunity_os.dashboard.tasks import OpenClawTaskAdapter
from opportunity_os.domain_query import DomainQueryError, DomainQueryService, QUERY_NAMES
from opportunity_os.errors import OpportunityOSError, ValidationError
from opportunity_os.proposals import ProposalError, ProposalStore
from opportunity_os.reports import render_review
from opportunity_os.signals import SignalReader
from opportunity_os.store import PrivateStore


MAX_TYPED_INPUT_BYTES = 8_192


def _emit(payload, output_format: str = "text") -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload)


def _store(args: argparse.Namespace) -> PrivateStore:
    return PrivateStore(args.home, knowledge_root=getattr(args, "knowledge_root", None))


def _snapshot(store: PrivateStore) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = store.home / "snapshots" / f"opportunity-os-{timestamp}.tar.gz"
    destination.parent.mkdir(parents=True, exist_ok=True)
    runtime_roots = (store.home / "snapshots", store.home / "dashboard")
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(store.home.rglob("*")):
            if not path.is_file() or any(path.is_relative_to(root) for root in runtime_roots) or path.name == ".env":
                continue
            archive.add(path, arcname=str(Path("opportunity-os") / path.relative_to(store.home)), recursive=False)
    return destination


def _dashboard_config(home: str | Path) -> DashboardConfig:
    configured = DashboardConfig.from_env()
    return replace(configured, dashboard_home=Path(home).expanduser().resolve() / "dashboard")


def _dashboard_dependencies(home: str | Path, config: DashboardConfig) -> DashboardDependencies:
    marker = config.dashboard_home / "last-health.json"
    read_model = DashboardReadModel(
        PrivateStateReadRepository(home),
        probes=(
            LastHealthProbe(marker, "openclaw"),
            LastHealthProbe(marker, "hermes"),
        ),
    )
    sessions = SessionStore(config.dashboard_home)
    event_hub = EventHub(config.dashboard_home / "event-cursor")
    return DashboardDependencies(
        read_model=read_model,
        sessions=sessions,
        csrf=CsrfGuard(),
        event_hub=event_hub,
        event_journal_path=Path(home).expanduser().resolve() / "events.jsonl",
        task_adapter=OpenClawTaskAdapter(),
    )


def _require_loopback_host(host: str) -> None:
    if host not in {"127.0.0.1", "::1"}:
        raise ValidationError("dashboard serve must bind to a loopback address")


def _require_loopback_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise ValidationError("dashboard open requires a loopback HTTP URL")
    return url.rstrip("/")


def _healthcheck(args: argparse.Namespace) -> HealthCheck:
    config = _dashboard_config(args.home)
    command_runner = CommandRunner()
    return HealthCheck(
        probes=(OpenClawProbe(config, command_runner), HermesProbe(config, command_runner)),
        marker=config.dashboard_home / "last-health.json",
    )


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise DomainQueryError("stdin_duplicate_key")
        value[key] = item
    return value


def _read_typed_input(keys: frozenset[str]) -> dict[str, object]:
    rendered = sys.stdin.read(MAX_TYPED_INPUT_BYTES + 1)
    try:
        encoded = rendered.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise DomainQueryError("stdin_invalid_unicode") from error
    if len(encoded) > MAX_TYPED_INPUT_BYTES:
        raise DomainQueryError("stdin_too_large")
    try:
        payload = json.loads(rendered, object_pairs_hook=_no_duplicates)
    except (json.JSONDecodeError, TypeError) as error:
        raise DomainQueryError("stdin_invalid_json") from error
    if not isinstance(payload, dict) or frozenset(payload) != keys:
        raise DomainQueryError("stdin_schema_invalid")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opportunity-os")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--home", required=True)
    init.add_argument("--knowledge-root", required=True)
    init.add_argument("--format", choices=("text", "json"), default="text")

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--home", required=True)
    doctor.add_argument("--knowledge-root", required=True)
    doctor.add_argument("--format", choices=("text", "json"), default="text")

    signals = subparsers.add_parser("signals")
    signals.add_argument("--knowledge-root", required=True)
    signals.add_argument("--days", type=int, default=14)
    signals.add_argument("--limit", type=int, default=80)
    signals.add_argument("--offset", type=int, default=0)
    signals.add_argument("--query")
    signals.add_argument("--today")
    signals.add_argument("--format", choices=("text", "json"), default="json")

    status = subparsers.add_parser("status", help="Return aggregate-only private-state metadata.")
    status.add_argument("--home", required=True)
    status.add_argument("--format", choices=("text", "json"), default="text")

    render = subparsers.add_parser("render-review")
    render.add_argument("review_id", nargs="?")
    render.add_argument("--home", required=True)
    render.add_argument("--latest", action="store_true")

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--home", required=True)
    snapshot.add_argument("--format", choices=("text", "json"), default="text")

    dashboard = subparsers.add_parser("dashboard")
    dashboard_commands = dashboard.add_subparsers(dest="dashboard_command", required=True)

    serve = dashboard_commands.add_parser("serve")
    serve.add_argument("--home", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    open_dashboard = dashboard_commands.add_parser("open")
    open_dashboard.add_argument("--home", required=True)
    open_dashboard.add_argument("--url", default="http://127.0.0.1:8765")

    health = subparsers.add_parser("healthcheck")
    health.add_argument("--home", required=True)
    health.add_argument("--format", choices=("text", "json"), default="json")

    domain = subparsers.add_parser("domain")
    domain_commands = domain.add_subparsers(dest="domain_command", required=True)
    domain_query = domain_commands.add_parser("query")
    domain_query.add_argument("--home", required=True)
    domain_query.add_argument("--stdin-json", action="store_true", required=True)
    domain_proposal = domain_commands.add_parser("propose")
    domain_proposal.add_argument("--home", required=True)
    domain_proposal.add_argument("--stdin-json", action="store_true", required=True)

    automation = subparsers.add_parser("automation")
    automation_commands = automation.add_subparsers(dest="automation_command", required=True)
    automation_run = automation_commands.add_parser("run")
    automation_run.add_argument("--home", required=True)
    automation_run.add_argument("--cadence", required=True, choices=tuple(sorted(CADENCES)))
    automation_run.add_argument("--period-key", required=True)
    automation_run.add_argument("--format", choices=("text", "json"), default="json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            store = _store(args)
            store.initialize()
            _emit({"home": str(store.home), "initialized": True}, args.format)
        elif args.command == "doctor":
            store = _store(args)
            reader = SignalReader(args.knowledge_root)
            report = {
                "ok": store.portfolio_path.is_file() and reader.inbox.is_dir(),
                "knowledge_read_only_source": reader.inbox.is_dir(),
                "private_home_outside_knowledge": not store.home.is_relative_to(reader.knowledge_root),
            }
            _emit(report, args.format)
            return 0 if report["ok"] else 1
        elif args.command == "signals":
            reader = SignalReader(args.knowledge_root)
            result = reader.list_signals(
                days=args.days, limit=args.limit, offset=args.offset, query=args.query, today=args.today
            )
            _emit([item.to_dict() for item in result], args.format)
        elif args.command == "status":
            _emit(_store(args).system_status(), args.format)
        elif args.command == "render-review":
            print(render_review(_store(args), args.review_id, latest=args.latest))
        elif args.command == "snapshot":
            path = _snapshot(_store(args))
            _emit({"snapshot": str(path)}, args.format)
        elif args.command == "dashboard" and args.dashboard_command == "serve":
            _require_loopback_host(args.host)
            config = _dashboard_config(args.home)
            app = create_app(config, _dashboard_dependencies(args.home, config))
            uvicorn.run(app, host=args.host, port=args.port)
        elif args.command == "dashboard" and args.dashboard_command == "open":
            url = _require_loopback_url(args.url)
            config = _dashboard_config(args.home)
            token = SessionStore(config.dashboard_home).create_bootstrap()
            webbrowser.open(f"{url}/#bootstrap={token}")
            _emit({"opened": True, "url": url}, "json")
        elif args.command == "healthcheck":
            result = _healthcheck(args).run()
            _emit(result, args.format)
            return 0 if result["ok"] else 1
        elif args.command == "domain" and args.domain_command == "query":
            payload = _read_typed_input(frozenset({"query"}))
            query = payload["query"]
            if not isinstance(query, str) or query not in QUERY_NAMES:
                raise DomainQueryError("unsupported_query")
            result = DomainQueryService(args.home).query(query)
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        elif args.command == "domain" and args.domain_command == "propose":
            payload = _read_typed_input(frozenset({"kind", "text"}))
            kind = payload["kind"]
            if not isinstance(kind, str):
                raise ProposalError("proposal_kind_invalid")
            result = ProposalStore(Path(args.home) / "proposals" / "pending.json").add(
                kind, payload["text"]  # type: ignore[arg-type]
            )
            _emit({"id": result["id"], "kind": result["kind"], "state": "pending"}, "json")
        elif args.command == "automation" and args.automation_command == "run":
            record = CadenceRunner(args.home).run(args.cadence, args.period_key)
            _emit(record.to_dict(), args.format)
            return 0 if record.status in {"success", "skipped_duplicate"} else 1
        return 0
    except (
        OpportunityOSError,
        DomainQueryError,
        ProposalError,
        HealthMarkerError,
    ) as error:
        _emit({"ok": False, "error": str(error)}, "json")
        return 2
    except OSError:
        _emit({"ok": False, "error": "runtime_io_failure"}, "json")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
