import argparse
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from opportunity_os.errors import OpportunityOSError
from opportunity_os.reports import render_review
from opportunity_os.signals import SignalReader
from opportunity_os.store import PrivateStore


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
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(store.home.rglob("*")):
            if not path.is_file() or path.is_relative_to(store.home / "snapshots") or path.name == ".env":
                continue
            archive.add(path, arcname=str(Path("opportunity-os") / path.relative_to(store.home)), recursive=False)
    return destination


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
        return 0
    except OpportunityOSError as error:
        _emit({"ok": False, "error": str(error)}, "json")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
