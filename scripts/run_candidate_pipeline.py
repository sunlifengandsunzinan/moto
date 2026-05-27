from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.adapt_openclaw_candidates import INPUT_PATH as OPENCLAW_INPUT_PATH
from scripts.adapt_openclaw_candidates import main as adapt_openclaw_main
from scripts.normalize_candidate_spots import main as normalize_main


def main() -> None:
    steps: list[str] = []

    if OPENCLAW_INPUT_PATH.exists():
        adapt_openclaw_main()
        steps.append("adapted openclaw export")
    else:
        steps.append("skipped openclaw adapter (no input file)")

    normalize_main()
    steps.append("normalized raw candidates")

    print("pipeline completed: " + " -> ".join(steps))


if __name__ == "__main__":
    main()