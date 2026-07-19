"""Explicit dry-run-first deployment CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from opportunity_os.deployment.kb_sync import KnowledgeSync
from opportunity_os.deployment.openclaw_cron import CronManifest, OpenClawCronClient, reconcile
from opportunity_os.deployment.remote_access import DashboardLaunchAgent, NgrokService, write_github_policy


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m opportunity_os.deployment")
    commands = parser.add_subparsers(dest="command", required=True)

    cron = commands.add_parser("cron-reconcile")
    cron.add_argument("--manifest", type=Path, required=True)
    cron.add_argument("--openclaw", type=Path, required=True)
    cron.add_argument("--apply", action="store_true")

    sync = commands.add_parser("kb-sync")
    sync.add_argument("--message", required=True)
    sync.add_argument("--apply", action="store_true")

    dashboard = commands.add_parser("dashboard-agent")
    dashboard.add_argument("--executable", type=Path, required=True)
    dashboard.add_argument("--private-home", type=Path, required=True)
    dashboard.add_argument("--destination", type=Path, required=True)
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.add_argument("--apply", action="store_true")

    policy = commands.add_parser("ngrok-policy")
    policy.add_argument("--owner-email", required=True)
    policy.add_argument("--destination", type=Path, required=True)
    policy.add_argument("--apply", action="store_true")

    ngrok = commands.add_parser("ngrok-service")
    ngrok.add_argument("action", choices=("install", "start", "restart", "status"))
    ngrok.add_argument("--ngrok", type=Path, required=True)
    ngrok.add_argument("--config", type=Path, required=True)
    ngrok.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "cron-reconcile":
        result = reconcile(
            CronManifest.load(args.manifest),
            OpenClawCronClient(executable=args.openclaw),
            apply=args.apply,
        )
        payload = {
            "applied": result.applied,
            "actions": [
                {"kind": action.kind, "name": action.name, "id": action.identifier}
                for action in result.actions
            ],
        }
    elif args.command == "kb-sync":
        result = KnowledgeSync().run(args.message, apply=args.apply)
        payload = {"applied": result.applied, "argv": list(result.argv), "returncode": result.returncode}
    elif args.command == "dashboard-agent":
        result = DashboardLaunchAgent(
            executable=args.executable, private_home=args.private_home, port=args.port
        ).install(args.destination, apply=args.apply)
        payload = {"applied": result.applied, "destination": str(result.destination)}
    elif args.command == "ngrok-policy":
        result = write_github_policy(args.destination, args.owner_email, apply=args.apply)
        payload = {"applied": result.applied, "destination": str(result.destination)}
    else:
        result = NgrokService(executable=args.ngrok, config=args.config).run(args.action, apply=args.apply)
        payload = {"applied": result.applied, "argv": list(result.argv), "returncode": result.returncode}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
