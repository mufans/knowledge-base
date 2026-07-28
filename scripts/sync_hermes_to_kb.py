#!/usr/bin/env python3
"""Compatibility entry point for the validated Hermes → compiler bridge."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKAGE_SRC = ROOT / "integrations" / "hermes-opportunity-os" / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from opportunity_os.automation.hermes_sync import HermesKnowledgeBridge  # noqa: E402


DEFAULT_HOME = Path("/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    parser.add_argument("--knowledge-root", type=Path, default=ROOT)
    parser.add_argument("--run-id")
    args = parser.parse_args()

    record = HermesKnowledgeBridge(args.home, args.knowledge_root).run(
        days=args.days,
        run_id=args.run_id,
    )
    print(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if record.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
