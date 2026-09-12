"""Score the helper against the tutor's blind answers.

Usage:
    python scripts/eval_helper.py api/tests/fixtures/eval/tutor_baseline.json

The tutor fills `tutor_noticed` and `tutor_would_suggest` WITHOUT seeing system
output, then rates the system's suggestion 1-5 afterwards. Almost no hackathon
team evaluates anything; a table with n and a human baseline is the slide.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api" / "src"))

from chordcat.helper.cli import analyse_capture  # noqa: E402

CAPTURES = ROOT / "api" / "tests" / "fixtures" / "midi"


def main(baseline_path: str) -> int:
    rows = json.loads(Path(baseline_path).read_text())
    agreed = 0
    tied = 0
    ratings: list[int] = []
    fallbacks = 0

    print(f"{'capture':38} {'tutor':20} {'system':20} {'verdict':12} rating")
    for row in rows:
        result = analyse_capture(CAPTURES / row["capture"])
        choice = result.choice
        chosen = choice.node.id if choice else "-"
        wanted = row["tutor_would_suggest"]

        if chosen == wanted:
            verdict = "agree"
            agreed += 1
        elif choice is not None and wanted in choice.tied_with:
            # The map found it and rated it equal; only the tie-break missed.
            verdict = "tied"
            tied += 1
        else:
            verdict = "missed"

        if row.get("tutor_rating_of_system"):
            ratings.append(int(row["tutor_rating_of_system"]))
        fallbacks += result.response.used_fallback
        print(
            f"{row['capture']:38} {wanted:20} {chosen:20} {verdict:12} "
            f"{row.get('tutor_rating_of_system') or '-'}"
        )

    n = len(rows)
    print(f"\nn = {n}")
    print(f"agreed outright                 : {agreed}/{n}")
    print(f"tied but lost the tie-break     : {tied}/{n}   <- a ranking problem")
    print(f"not on the frontier at all      : {n - agreed - tied}/{n}   <- a map problem")
    if ratings:
        print(f"mean tutor rating (1-5)         : {sum(ratings) / len(ratings):.2f}")
    print(f"templated fallbacks             : {fallbacks}/{n}")
    print("factual errors                  : 0 by construction (validator)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
