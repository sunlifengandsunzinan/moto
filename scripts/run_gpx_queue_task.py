#!/usr/bin/env python3

import argparse
import json

from app.services import gpx_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Run file-based GPX queue processing")
    parser.add_argument("--file", required=True, help="Queue file path")
    args = parser.parse_args()
    result = gpx_service.run_gpx_queue_file(args.file)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()