from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.route_templates_config import ROUTE_TEMPLATES_JSON_PATH, validate_route_templates_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate route_templates.json before writing it back to the app.")
    parser.add_argument("--file", default=str(ROUTE_TEMPLATES_JSON_PATH), help="Path to a route templates JSON file")
    args = parser.parse_args()

    route_file = Path(args.file).resolve()
    try:
        routes = validate_route_templates_file(route_file)
    except Exception as error:
        print(f"INVALID: {route_file}", file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 1

    print(f"OK: {len(routes)} routes validated from {route_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())